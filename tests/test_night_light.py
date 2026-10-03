"""The night light (roadmap 6.3, spec NIGHT): Settings > Displays saves the mode,
warmth and times; night_light.py turns them into a wlsunset command, and the
night-light user service runs it. See config/waybar/scripts/night_light.py."""

import os
import re
from pathlib import Path

import night_light
import pytest
import settings_store as store
from conftest import ROOT
from test_bar_strip import settings_method

TEHRAN = (35.667, 51.433)


def night(**changes):
    return dict(store.DEFAULTS, **changes)


def test_sunset_mode_follows_the_home_place_or_falls_back_to_the_schedule():
    """NIGHT-1: given Follow sunset at 3500 K, when the home place is known, then
    wlsunset gets its latitude and longitude; when no place is known (UTC), then
    it gets the schedule's times instead."""
    s = night(night_mode="sunset", night_temp=3500)

    assert night_light.command(s, TEHRAN) == ["wlsunset", "-t", "3500", "-l", "35.667", "-L", "51.433"]
    assert night_light.command(s, None) == ["wlsunset", "-t", "3500", "-s", "20:00", "-S", "07:00"]


def test_schedule_mode_warms_from_the_start_to_the_end_time():
    """NIGHT-2: given Schedule from 21:30 to 06:00, then wlsunset's sunset is
    21:30 and its sunrise 06:00, whatever the home place is."""
    s = night(night_mode="schedule", night_start="21:30", night_end="06:00", night_temp=3000)

    assert night_light.command(s, TEHRAN) == ["wlsunset", "-t", "3000", "-s", "21:30", "-S", "06:00"]


def test_off_runs_nothing(monkeypatch):
    """NIGHT-3: given Off, then there is no wlsunset command, and the service
    waits instead of running one (stopping wlsunset gives normal colors)."""
    assert night_light.command(night(night_mode="off"), TEHRAN) is None

    waited, ran = [], []
    monkeypatch.setattr(night_light.store, "load", lambda: night(night_mode="off"))
    monkeypatch.setattr(night_light, "home_place", lambda: TEHRAN)
    monkeypatch.setattr(night_light.signal, "pause", lambda: waited.append(True))
    monkeypatch.setattr(night_light.os, "execvp", lambda *a: ran.append(a))
    assert night_light.main(["night_light.py", "--serve"]) == 0
    assert waited == [True] and ran == []


def test_a_night_light_change_restarts_the_service_without_a_reload(tmp_path):
    """NIGHT-4: given Settings, when a night light setting is saved, then the
    night-light service is restarted and Hyprland is not reloaded; another
    setting does not restart it."""
    spawned, saved = [], []
    (tmp_path / "a.lua").write_text("")  # not a first run: no reload for that reason
    fake_store = type("Store", (), {
        "load": staticmethod(lambda: dict(store.DEFAULTS)),
        "save": staticmethod(saved.append),
        "paths": staticmethod(lambda: (str(tmp_path / "a.json"), str(tmp_path / "a.lua"))),
    })
    ns = {"store": fake_store, "spawn": spawned.append, "THEME_PY": "theme.py", "os": os}
    exec(settings_method("save"), ns)  # noqa: S102 - the repo's own settings.py source
    error = type("Label", (), {"set_label": lambda *_: None, "set_visible": lambda *_: None})()
    host = type("Host", (), {"error": error})()

    ns["save"](host, night_mode="schedule")
    ns["save"](host, night_temp=3200)
    ns["save"](host, gaps=False)

    restart = ["systemctl", "--user", "restart", "night-light.service"]
    assert spawned == [restart, restart]
    assert saved[0]["night_mode"] == "schedule" and saved[1]["night_temp"] == 3200
    assert not [a for a in spawned if a[0] == "hyprctl"]


def test_the_service_starts_with_the_session_and_the_installer_enables_it():
    """NIGHT-5: given the repository, then night-light.service runs
    night_light.py --serve, belongs to the Hyprland session, and install.sh
    copies and enables it."""
    unit = (Path(ROOT) / "config" / "systemd" / "user" / "night-light.service").read_text()
    install = (Path(ROOT) / "install.sh").read_text()

    assert "ExecStart=%h/.config/waybar/scripts/night_light.py --serve" in unit
    assert "PartOf=hyprland-session.target" in unit
    assert "WantedBy=hyprland-session.target" in unit
    assert "systemctl --user enable --now night-light.service" in install
    assert re.search(r"^install_night_light$", install, re.M)


def test_the_settings_have_defaults_and_bad_values_fall_back_or_are_refused(tmp_path):
    """NIGHT-6: given nothing saved, then the night light is Off at 4000 K from
    20:00 to 07:00; when a hand-edited file holds 25:99 or 9000 K, then load
    uses the defaults; when Settings saves such a value, then it is refused."""
    xkb = tmp_path / "xkb"
    xkb.mkdir()
    for layout in ("us", "ir"):
        (xkb / layout).write_text("")
    s = store.load(str(tmp_path))
    assert (s["night_mode"], s["night_temp"], s["night_start"], s["night_end"]) == ("off", 4000, "20:00", "07:00")

    (tmp_path / "hypr").mkdir()
    (tmp_path / "hypr" / "user-settings.json").write_text(
        '{"night_mode": "dusk", "night_temp": 9000, "night_start": "25:99", "night_end": "06:30"}'
    )
    s = store.load(str(tmp_path))
    assert (s["night_mode"], s["night_temp"], s["night_start"], s["night_end"]) == ("off", 4000, "20:00", "06:30")

    for bad in (dict(night_start="25:99"), dict(night_temp=9000), dict(night_mode="dusk")):
        with pytest.raises(ValueError):
            store.save(night(**bad), str(tmp_path), str(xkb))
