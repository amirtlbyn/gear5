"""The power popup opens under the away-timer pill, which spec AWAKE moved to the
left side of the bar (spec POWERPOS). See config/waybar/scripts/power-popup.py."""

import ast
import os

import panel
from conftest import SCRIPTS

mod = panel.load("power-popup")


def test_a_click_on_the_bar_opens_it_under_the_mouse():
    """POWERPOS-1: given the mouse is on the bar, when the popup opens, then it
    is centered under the mouse and kept inside the screen; show_popup places
    it before it presents the window."""
    assert mod.left_margin((310, 30, 1920), 360) == 310 - 180
    assert mod.left_margin((20, 30, 1920), 360) == 0
    assert mod.left_margin((1900, 30, 1920), 360) == 1920 - 360
    assert (
        mod.left_margin((310, 70, 1080), 360) == 130
    )  # a vertical screen, bar's lower edge

    with open(os.path.join(SCRIPTS, "power-popup.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    show = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "show_popup"
    )
    calls = [
        n.func.attr
        for n in ast.walk(show)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]
    assert calls.index("place") < calls.index("present")


def test_the_keyboard_shortcut_opens_it_on_the_left():
    """POWERPOS-2: given the mouse is not on the bar (SUPER+B) or its position is
    unknown, when the popup opens, then it is on the left where the bar starts,
    and the build no longer pins it to the right."""
    assert mod.left_margin((1500, 600, 1920), 360) == mod.BAR_LEFT == 120
    assert mod.left_margin(None, 360) == 120
    with open(os.path.join(SCRIPTS, "power-popup.py"), encoding="utf-8") as f:
        src = f.read()
    assert "set_margin_end(420)" not in src
    assert "popup.set_halign(Gtk.Align.END)" not in src
