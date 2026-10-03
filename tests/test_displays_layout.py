"""The screen layout survives a config reload: displays.py writes it as Lua, and
hyprland.lua loads it after its own monitor lines (a theme switch reloads)."""

import json
import os
import subprocess

import panel
from conftest import ROOT

mod = panel.load("displays")

LAPTOP = {
    "name": "eDP-1",
    "description": "AU Optronics B153UAN03.0",
    "make": "AU Optronics",
    "model": "B153",
    "width": 1920,
    "height": 1200,
    "refreshRate": 60.0,
    "x": 0,
    "y": 0,
    "scale": 1.0,
    "transform": 0,
    "availableModes": ["1920x1200@60.00Hz"],
    "disabled": False,
}


def test_the_applied_layout_is_written_for_the_next_reload(tmp_path, monkeypatch):
    """PH0-1: given the laptop screen alone and no saved layout, when --auto finds
    nothing to change, then it changes nothing on screen but writes the layout
    hyprland.lua loads after its monitor lines. Given a layout that differs from
    the screens, when apply() applies it, then the file and the hyprctl call both
    carry that layout. The file is written again only when its text changes.
    hyprland.lua reads it with loadfile, so the write does not reload."""
    layout = tmp_path / "displays-current.lua"
    evals = []
    monkeypatch.setattr(mod, "LAYOUT_LUA", str(layout))
    monkeypatch.setattr(mod, "read_screens", lambda: [mod.Screen(dict(LAPTOP))])
    monkeypatch.setattr(mod, "load_profiles", lambda: {})
    monkeypatch.setattr(mod, "lid_closed", lambda: False)
    monkeypatch.setattr(mod.subprocess, "run", lambda argv, **_kw: evals.append(argv))

    mod.auto()
    assert evals == []  # already right: nothing is applied
    text = layout.read_text()
    assert 'position = "0x0"' in text and "desc:AU Optronics B153UAN03.0" in text

    os.utime(layout, (1, 1))
    mod.auto()
    assert os.path.getmtime(layout) == 1  # same text: not written again

    # the other PH0-1 trigger: a real change goes through apply(), and the file
    # and the hyprctl call both carry the new position
    moved = mod.Screen(dict(LAPTOP))
    moved.x, moved.y = 3000, 360
    mod.apply([moved])
    assert len(evals) == 1 and 'position = "3000x360"' in evals[0][2]
    assert 'position = "3000x360"' in layout.read_text()

    lua = open(os.path.join(ROOT, "config", "hypr", "hyprland.lua")).read()
    monitors_end = lua.index("---------------- Environment ----------------")
    load_at = lua.index('"/hypr/displays-current.lua")')
    assert lua.rindex("hl.monitor(", 0, monitors_end) < load_at < monitors_end
    assert "loadfile(" in lua[load_at - 200 : load_at] and 'require("displays-current")' not in lua


def test_a_screen_that_is_on_says_so_in_its_rule(monkeypatch):
    """LPCB-1: given the laptop panel turned off earlier, when displays.py writes or
    evaluates the rule that turns it on, then the rule says `disabled = false`.
    Hyprland merges the rules for one screen, so without it the panel stays off."""
    monkeypatch.setattr(mod, "lid_closed", lambda: False)
    rules = mod.lua_rules([mod.Screen(dict(LAPTOP))])
    assert "disabled = false" in rules and 'position = "0x0"' in rules

    off = mod.Screen(dict(LAPTOP, disabled=True))
    assert "disabled = true" in mod.lua_rules([off])


def test_opening_the_lid_writes_the_layout_again_before_the_reload(tmp_path):
    """LPCB-2: given the lid flag and a layout written with the lid closed, when the
    lid opens, then lid.sh removes the flag, runs `displays.py --auto`, and only
    then reloads Hyprland."""
    calls = tmp_path / "calls"
    scripts = tmp_path / "home" / ".config" / "waybar" / "scripts"
    scripts.mkdir(parents=True)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    flag = tmp_path / "hypr-lid-closed"
    flag.write_text("eDP-1\n")
    # each fake records its call and whether the flag was still there
    record = f'echo "$(basename "$0") $* flag=$([[ -f {flag} ]] && echo yes || echo no)" >> {calls}\n'
    for fake in (scripts / "displays.py", bindir / "hyprctl"):
        fake.write_text("#!/usr/bin/env bash\n" + record)
        fake.chmod(0o755)

    env = dict(os.environ, HOME=str(tmp_path / "home"), XDG_RUNTIME_DIR=str(tmp_path),
               PATH=f"{bindir}:{os.environ['PATH']}")
    lid = os.path.join(ROOT, "config", "hypr", "scripts", "lid.sh")
    subprocess.run([lid, "open"], env=env, check=True)

    assert not flag.exists()
    assert calls.read_text().splitlines() == ["displays.py --auto --lid-opened flag=no", "hyprctl reload flag=no"]


def test_a_layout_kept_with_the_lid_closed_does_not_save_the_panel_off(tmp_path, monkeypatch):
    """LPCB-3: given the lid closed (the panel off because of it), when the user keeps
    a layout, then the profile keeps the panel's earlier saved value, and "on" when
    this set of screens was never saved."""
    profiles = tmp_path / "displays.json"
    monkeypatch.setattr(mod, "PROFILES", str(profiles))
    monkeypatch.setattr(mod, "lid_closed", lambda: True)
    external = dict(LAPTOP, name="HDMI-A-1", description="Samsung S27", x=1920)
    screens = [mod.Screen(dict(LAPTOP, disabled=True)), mod.Screen(dict(external))]
    key = mod.profile_key(screens)

    mod.save_profile(screens)
    assert mod.load_profiles()[key]["AU Optronics B153UAN03.0"]["enabled"] is True
    assert mod.load_profiles()[key]["Samsung S27"]["enabled"] is True

    # the user turned the panel off with the lid open: a save with the lid closed keeps that
    profiles.write_text(json.dumps({key: {"AU Optronics B153UAN03.0": {"enabled": False}}}))
    mod.save_profile(screens)
    assert mod.load_profiles()[key]["AU Optronics B153UAN03.0"]["enabled"] is False

    # a hand-edited entry that is not a dict counts as never saved
    profiles.write_text(json.dumps({key: {"AU Optronics B153UAN03.0": None}}))
    mod.save_profile(screens)
    assert mod.load_profiles()[key]["AU Optronics B153UAN03.0"]["enabled"] is True


def test_opening_the_lid_turns_the_panel_on_over_a_saved_off(tmp_path, monkeypatch):
    """LPCB-4: given a saved layout for these screens with the laptop panel off, when
    the lid opens, then --auto turns the panel on beside the external screen and
    saves "on" for that layout. A plain --auto (a screen plugged in) keeps the saved off."""
    profiles = tmp_path / "displays.json"
    evals = []
    monkeypatch.setattr(mod, "PROFILES", str(profiles))
    monkeypatch.setattr(mod, "LAYOUT_LUA", str(tmp_path / "displays-current.lua"))
    monkeypatch.setattr(mod, "lid_closed", lambda: False)
    monkeypatch.setattr(mod.subprocess, "run", lambda argv, **_kw: evals.append(argv))
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *_a, **_kw: None)
    external = dict(LAPTOP, name="HDMI-A-1", description="Samsung S27")
    monkeypatch.setattr(mod, "read_screens",
                        lambda: [mod.Screen(dict(LAPTOP, disabled=True)), mod.Screen(dict(external))])
    key = mod.profile_key(mod.read_screens())
    off = dict(enabled=False, mode="1920x1200@60.00", x=0, y=0, scale=1.0, transform=0, mirror=None)
    on = dict(off, enabled=True)
    profiles.write_text(json.dumps({key: {"AU Optronics B153UAN03.0": off, "Samsung S27": on}}))

    mod.auto()
    assert evals == []  # the saved off already holds

    mod.auto(lid_opened=True)
    assert len(evals) == 1
    assert 'output = "desc:AU Optronics B153UAN03.0", disabled = false' in evals[0][2]
    assert 'position = "1920x0"' in evals[0][2]
    assert mod.load_profiles()[key]["AU Optronics B153UAN03.0"]["enabled"] is True
