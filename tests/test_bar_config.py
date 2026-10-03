"""Vertical screens get a compact bar with only the workspaces."""
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "config", "waybar", "scripts", "bar_config.py")
spec = importlib.util.spec_from_file_location("bar_config", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_a_vertical_screen_gets_only_the_workspaces(monkeypatch):
    """given one rotated screen, when the config is built, then the normal bar
    leaves that screen out and a second bar there shows only the desks;
    given no rotated screen, then the config is bar/config unchanged."""
    monkeypatch.setattr(mod, "SRC", os.path.join(ROOT, "config", "waybar", "bar", "config"))
    monkeypatch.setattr(mod, "vertical_outputs", lambda: [])
    assert len(mod.build()) == 1

    monkeypatch.setattr(mod, "vertical_outputs", lambda: ["DP-1"])
    normal, compact = mod.build()
    assert normal["output"] == ["!DP-1", "*"]
    assert compact["output"] == ["DP-1"]
    assert compact["modules-center"] == ["group/desks"]
    assert compact["modules-left"] == compact["modules-right"] == []
    json.dumps([normal, compact])
