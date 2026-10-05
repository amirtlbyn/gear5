"""Roadmap 6.4, spec BDIM: the screen dims after N idle minutes on battery. The
choice is on Settings' Battery page, idle.sh writes it into hypridle's config, and
`idle.sh dim` / `idle.sh undim` change the brightness. The idle.sh tests run the
real script with a fake brightnessctl, a fake power_supply folder, and a fake
hypridle and pkill, so the real screen and the running hypridle are never touched."""

import json
import os
import subprocess
import time

import panel
import pytest
import settings_store as store
from conftest import ROOT, SCRIPTS

IDLE = os.path.join(ROOT, "config", "hypr", "scripts", "idle.sh")
page = panel.load("battery-page")


@pytest.fixture
def sandbox(tmp_path):
    """HOME with the real scripts, a PATH with fakes, and helpers to set the power
    source, the brightness (of 1000) and the settings."""
    home, bindir, power = tmp_path / "home", tmp_path / "bin", tmp_path / "power"
    (home / ".config" / "hypr").mkdir(parents=True)
    (home / ".config" / "waybar").mkdir()
    os.symlink(SCRIPTS, home / ".config" / "waybar" / "scripts")
    bindir.mkdir()
    level = tmp_path / "brightness"
    fakes = {
        # FAKE_SLOW_GET makes a dim slow, so an undim can start in the middle of it
        "brightnessctl": (f'f={level}\ncase "$1" in get) sleep "${{FAKE_SLOW_GET:-0}}"; cat $f;;'
                          ' max) echo 1000;; -q) echo "$3" > $f;; esac\n'),
        "hypridle": "exit 0\n",
        "pkill": "exit 0\n",
    }
    for name, body in fakes.items():
        (bindir / name).write_text("#!/usr/bin/env bash\n" + body)
        (bindir / name).chmod(0o755)
    (power / "ADP0").mkdir(parents=True)
    (power / "ADP0" / "type").write_text("Mains\n")
    env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
               XDG_RUNTIME_DIR=str(tmp_path), IDLE_POWER_ROOT=str(power),
               PATH=f"{bindir}:{os.environ['PATH']}")

    class Box:
        conf = home / ".config" / "hypr" / "hypridle.conf"

        @staticmethod
        def run(*args):
            subprocess.run([IDLE, *args], env=env, check=True, timeout=20)

        @staticmethod
        def start(*args, **extra):
            return subprocess.Popen([IDLE, *args], env=dict(env, **extra))

        @staticmethod
        def charger(online):
            (power / "ADP0" / "online").write_text("1\n" if online else "0\n")

        @staticmethod
        def brightness(value=None):
            if value is not None:
                level.write_text(f"{value}\n")
            return int(level.read_text())

        @staticmethod
        def dimmed():
            return tmp_path / "idle-dimmed"

        @staticmethod
        def settings(**kw):
            (home / ".config" / "hypr" / "user-settings.json").write_text(json.dumps(kw))

    return Box


def test_the_battery_page_offers_saves_and_applies_the_dim_time(tmp_path, monkeypatch):
    """BDIM-1: given the Battery page, then "Dim when idle" offers Off, 1, 2, 5 and
    10 minutes; when one is picked, then it is saved and idle.sh apply runs at once.
    A hand-edited value the page never offers reads as Off."""
    assert page.DIM_NAMES == ["Off", "1 min", "2 min", "5 min", "10 min"]
    real_load, real_save = store.load, store.save
    monkeypatch.setattr(store, "load", lambda: real_load(config=str(tmp_path)))
    monkeypatch.setattr(store, "save", lambda s: real_save(s, config=str(tmp_path)))
    started = []
    monkeypatch.setattr(page.subprocess, "Popen", lambda argv, **_kw: started.append(argv))

    class Drop:
        def get_selected(self):
            return 3  # "5 min"

    page.BatteryLimitsPanel.on_dim(None, Drop(), None)
    assert store.load()["battery_dim"] == 5
    assert started == [[page.IDLE, "apply"]]

    (tmp_path / "hypr" / "user-settings.json").write_text(json.dumps({"battery_dim": 7}))
    assert store.load()["battery_dim"] == 0


def test_the_idle_config_has_the_battery_dim_only_when_chosen(sandbox):
    """BDIM-2: given a dim time of 2 minutes, then hypridle's config dims on battery
    after 120 s; given Off, then it has no battery dim and the rest of the config is
    the same (INV-1). Given "Stay awake", then no config is written at all."""
    sandbox.settings(battery_dim=2)
    sandbox.run("apply")
    with_dim = sandbox.conf.read_text()
    assert "timeout = 120\n    on-timeout = ~/.config/hypr/scripts/idle.sh dim 30 battery" in with_dim

    sandbox.settings(battery_dim=0)
    sandbox.run("apply")
    without = sandbox.conf.read_text()
    assert "dim 30 battery" not in without
    block = with_dim[with_dim.index("\n# Settings > Battery > Dim when idle"):]
    block = block[: block.index("}\n") + 2]
    assert with_dim.replace(block, "") == without

    sandbox.conf.unlink()
    sandbox.settings(battery_dim=2)
    sandbox.run("set", "awake")
    assert not sandbox.conf.exists()


def test_the_battery_dim_acts_on_battery_only_and_never_brightens(sandbox):
    """BDIM-3: given AC power, when the battery dim fires, then the brightness stays.
    Given battery power, then it goes to 30 %, and a screen already below 30 % stays
    as it is."""
    sandbox.charger(online=True)
    sandbox.brightness(800)
    sandbox.run("dim", "30", "battery")
    assert sandbox.brightness() == 800

    sandbox.charger(online=False)
    sandbox.run("dim", "30", "battery")
    assert sandbox.brightness() == 300
    sandbox.run("undim")

    sandbox.brightness(200)
    sandbox.run("dim", "30", "battery")
    assert sandbox.brightness() == 200


def test_activity_brings_back_the_brightness_from_before_the_first_dim(sandbox):
    """BDIM-4: given the battery dim and then the dim before the lock, when the user
    is active again, then the brightness is the one from before both dims. A second
    undim changes nothing. An undim that starts while a dim still runs waits for it,
    then restores, and leaves no saved level behind."""
    sandbox.charger(online=False)
    sandbox.brightness(800)
    sandbox.run("dim", "30", "battery")
    sandbox.run("dim", "10")
    assert sandbox.brightness() == 100
    sandbox.run("undim")
    assert sandbox.brightness() == 800
    sandbox.brightness(650)
    sandbox.run("undim")
    assert sandbox.brightness() == 650

    slow = sandbox.start("dim", "30", "battery", FAKE_SLOW_GET="0.5")
    time.sleep(0.2)
    sandbox.run("undim")
    assert slow.wait(timeout=10) == 0
    assert sandbox.brightness() == 650
    assert not (sandbox.dimmed()).exists()
