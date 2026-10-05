"""Battery charge limits: reading the battery, the charge rule, validation and
the battery-limits service loop — all against a fake sysfs, never the real one."""

import json
import os
import time

import battery
import pytest
import settings_store as store


@pytest.fixture
def xkb(tmp_path):
    d = tmp_path / "xkb"
    d.mkdir()
    for name in ("us", "ir"):
        (d / name).write_text("")
    return str(d)


def fake_sysfs(tmp_path, capacity, status="Charging", charge_types="Fast [Standard] Long_Life"):
    """A sysfs root with one battery (BAT0): status, capacity and charge_types."""
    bat = tmp_path / "sysfs" / "BAT0"
    bat.mkdir(parents=True)
    (bat / "status").write_text(status)
    (bat / "capacity").write_text(str(capacity))
    (bat / "charge_types").write_text(charge_types)
    return str(tmp_path / "sysfs")


def fake_config(tmp_path, xkb, stop, start, speed):
    config = tmp_path / "config"
    store.save(
        dict(store.DEFAULTS, battery_stop=stop, battery_start=start, battery_speed=speed), str(config), xkb
    )
    return str(config)


def test_read_reports_status_health_cycles_and_power_from_the_battery(tmp_path):
    """BATPICK-1: given a battery's sysfs files, when the Battery page reads
    them, then it gets the charge level, the state, health (full ÷ design
    capacity) and the cycle count and power draw."""
    sysfs = fake_sysfs(tmp_path, capacity=85, status="Charging")
    bat = tmp_path / "sysfs" / "BAT0"
    (bat / "energy_full").write_text("50000000")
    (bat / "energy_full_design").write_text("57000000")
    (bat / "cycle_count").write_text("272")
    (bat / "power_now").write_text("15000000")

    state = battery.read(sysfs)

    assert state["status"] == "Charging"
    assert state["capacity"] == 85
    assert state["health_pct"] == 88
    assert state["cycle_count"] == 272
    assert state["power_watts"] == 15.0


def test_rule_chooses_long_life_the_speed_or_keeps_the_current_type():
    """BATPICK-3: given a stop, a start, a speed and the current charge type,
    when the charge rule runs, then it picks Long_Life whenever stop is 80 or
    the level is at or above stop, the chosen speed whenever stop is 100 or the
    level is at or below start, and otherwise keeps the current type."""
    for capacity, stop, start, speed, current, expected in (
        (85, 80, 40, "Fast", "Standard", "Long_Life"),  # stop is the 80% hold: always Long_Life
        (60, 80, 40, "Fast", "Long_Life", "Long_Life"),  # same, regardless of the level
        (95, 100, 95, "Fast", "Standard", "Fast"),  # stop is 100 (no limit): always the speed
        (50, 100, 95, "Standard", "Long_Life", "Standard"),
        (90, 90, 80, "Fast", "Standard", "Long_Life"),  # at or above stop
        (80, 90, 80, "Fast", "Standard", "Fast"),  # at or below start
        (85, 90, 80, "Fast", "Standard", "Standard"),  # in between: keep the current type
        (85, 90, 80, "Fast", "Long_Life", "Long_Life"),  # in between, the other current type
    ):
        got = battery.rule(capacity, stop, start, speed, current)
        assert got == expected, (capacity, stop, start, speed, current)


def test_valid_accepts_the_allowed_range_and_refuses_everything_else():
    """BATPICK-6: given stop, start and speed, when they are validated, then
    stop 80-100, start 40..stop-5 and speed Fast/Standard are accepted (and
    normalized to ints), and anything outside that range raises ValueError."""
    assert battery.valid(90, 80, "Fast") == (90, 80, "Fast")
    assert battery.valid("90", "80", "Standard") == (90, 80, "Standard")
    for stop, start, speed in (
        (79, 40, "Fast"),  # stop below 80
        (101, 40, "Fast"),  # stop above 100
        (90, 39, "Fast"),  # start below 40
        (90, 86, "Fast"),  # start above stop - 5
        (90, 80, "Turbo"),  # not a real speed
        ("x", 80, "Fast"),  # not a whole number
    ):
        with pytest.raises(ValueError):
            battery.valid(stop, start, speed)


def test_writable_reflects_whether_charge_types_can_be_written(tmp_path):
    """BATPICK-5: given the battery's charge_types file, when this process can
    write it, then writable() is True; when it can't (the udev rule has not
    run), it is False — the signal the Battery page uses to turn its limit
    controls off and show the one command that fixes it."""
    sysfs = fake_sysfs(tmp_path, capacity=50)
    charge_types_path = tmp_path / "sysfs" / "BAT0" / "charge_types"

    charge_types_path.chmod(0o444)
    assert battery.writable(sysfs) is False

    charge_types_path.chmod(0o644)
    assert battery.writable(sysfs) is True


def test_service_applies_the_rule_at_start_writes_only_on_change_and_never_raises(tmp_path, xkb):
    """BATPICK-4: given the battery-limits service, when it starts, then it
    applies the charge rule once immediately, writing charge_types only when it
    differs from the current value; when user-settings.json's mtime changes,
    the next check applies the new rule; and a battery that can't be read never
    stops the loop."""
    sysfs = fake_sysfs(tmp_path, capacity=85, charge_types="Fast [Standard] Long_Life")
    config = fake_config(tmp_path, xkb, stop=80, start=40, speed="Fast")
    charge_types_path = tmp_path / "sysfs" / "BAT0" / "charge_types"

    battery.serve(sysfs=sysfs, config=config, iterations=1, sleep=lambda s: None)
    assert charge_types_path.read_text() == "Long_Life"

    # the kernel now reports Long_Life selected: nothing left to write
    charge_types_path.write_text("Fast Standard [Long_Life]")
    assert battery.apply("Long_Life", sysfs) is False

    fake_config(tmp_path, xkb, stop=100, start=95, speed="Fast")  # a settings change
    battery.serve(sysfs=sysfs, config=config, iterations=1, sleep=lambda s: None)
    assert charge_types_path.read_text() == "Fast"

    unreadable = str(tmp_path / "no-such-sysfs")
    battery.serve(sysfs=unreadable, config=config, iterations=2, sleep=lambda s: None)  # must not raise


@pytest.mark.parametrize(
    "charge_types",
    [None, "Trickle Fast Standard Adaptive [Custom]"],  # no charge modes at all; a Dell's names
)
def test_a_battery_without_the_ideapad_charge_modes_is_read_only(tmp_path, xkb, charge_types):
    """INV-1 on other hardware: the page still reads the battery, says limits are
    not supported, and neither the page nor the service ever writes charge_types."""
    sysfs = fake_sysfs(tmp_path, capacity=90, charge_types=charge_types or "")
    path = tmp_path / "sysfs" / "BAT0" / "charge_types"
    if charge_types is None:
        path.unlink()
    config = fake_config(tmp_path, xkb, stop=80, start=40, speed="Fast")

    state = battery.read(sysfs)
    assert state["capacity"] == 90 and state["supported"] is False
    assert battery.writable(sysfs) is False
    battery.tick(sysfs, config)
    assert (path.read_text() if path.exists() else None) == charge_types


def test_the_service_applies_a_settings_change_on_the_next_check(tmp_path, xkb):
    """The service's mtime check: a save between two checks is applied on the next
    check, well before the 30 s timer."""
    sysfs = fake_sysfs(tmp_path, capacity=85, charge_types="[Fast] Standard Long_Life")
    config = fake_config(tmp_path, xkb, stop=100, start=95, speed="Fast")
    path = tmp_path / "sysfs" / "BAT0" / "charge_types"
    json_path = store.paths(config)[0]
    sleeps = []

    def sleep(_s):
        sleeps.append(1)
        if len(sleeps) == 1:  # the developer picks Desk after the first check
            fake_config(tmp_path, xkb, stop=80, start=75, speed="Fast")
            os.utime(json_path, (time.time() + 5, time.time() + 5))

    battery.serve(sysfs=sysfs, config=config, iterations=2, sleep=sleep)
    assert path.read_text() == "Long_Life"


def test_the_service_falls_back_to_full_on_a_bad_saved_file(tmp_path, xkb):
    """INV-1: a hand-edited file (start above stop - 5) means Full: the battery
    charges again even when Long_Life is selected."""
    sysfs = fake_sysfs(tmp_path, capacity=70, charge_types="Fast Standard [Long_Life]")
    config = fake_config(tmp_path, xkb, stop=90, start=80, speed="Fast")
    json_path = store.paths(config)[0]
    with open(json_path, "w") as f:
        json.dump(dict(battery_stop=90, battery_start=95, battery_speed="Fast"), f)

    battery.tick(sysfs, config)
    assert (tmp_path / "sysfs" / "BAT0" / "charge_types").read_text() == "Fast"


def test_a_bad_battery_value_does_not_block_saving_other_settings(tmp_path, xkb):
    """A hand-edited battery value is replaced by the defaults on load, so the
    other pages (gaps, keyboard, fonts) can still save."""
    config = fake_config(tmp_path, xkb, stop=90, start=80, speed="Fast")
    with open(store.paths(config)[0], "w") as f:
        json.dump(dict(battery_stop=90, battery_start=95, battery_speed="Turbo"), f)

    s = store.load(config)
    assert (s["battery_stop"], s["battery_start"], s["battery_speed"]) == (100, 95, "Fast")
    store.save(dict(s, gaps=False), config, xkb)


def test_a_battery_only_save_leaves_the_lua_file_alone(tmp_path, xkb):
    """A slider drag saves at every step: the Lua file, whose write makes Hyprland
    reload, is written only when its text changes."""
    config = fake_config(tmp_path, xkb, stop=100, start=95, speed="Fast")
    lua_path = store.paths(config)[1]
    os.utime(lua_path, (1, 1))

    store.save(dict(store.load(config), battery_stop=90, battery_start=80), config, xkb)
    assert os.path.getmtime(lua_path) == 1
    assert store.load(config)["battery_stop"] == 90


def test_the_udev_rule_runs_two_programs_and_no_shell():
    """PH0-5: the rule changes the group and mode of BAT*/charge_types with two
    direct RUN programs, no shell, and matches only the battery (INV-2 of BATPICK)."""
    path = os.path.join(os.path.dirname(__file__), "..", "config", "udev", "90-summer-battery.rules")
    rule = " ".join(line for line in open(path).read().splitlines() if not line.startswith("#"))
    assert "/bin/sh" not in rule and "sh -c" not in rule
    assert 'SUBSYSTEM=="power_supply", KERNEL=="BAT*"' in rule
    assert 'RUN+="/usr/bin/chgrp wheel /sys%p/charge_types"' in rule
    assert 'RUN+="/usr/bin/chmod g+w /sys%p/charge_types"' in rule
    assert rule.count("RUN+=") == 2
