"""The screen layout survives a config reload: displays.py writes it as Lua, and
hyprland.lua loads it after its own monitor lines (a theme switch reloads)."""

import os

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
    hyprland.lua loads after its monitor lines, and writes it again only when it
    changes; hyprland.lua reads it with loadfile, so the write does not reload."""
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

    lua = open(os.path.join(ROOT, "config", "hypr", "hyprland.lua")).read()
    monitors_end = lua.index("---------------- Environment ----------------")
    load_at = lua.index('"/hypr/displays-current.lua")')
    assert lua.rindex("hl.monitor(", 0, monitors_end) < load_at < monitors_end
    assert "loadfile(" in lua[load_at - 200 : load_at] and 'require("displays-current")' not in lua
