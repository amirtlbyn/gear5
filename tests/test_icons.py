"""The glyphs next to titles mean what the words say: the audit behind the ICON
spec found four that did not (Extend, Duplicate, Balanced, the battery card's
embedded title)."""

import os

from conftest import ROOT

SCRIPTS = os.path.join(ROOT, "config", "waybar", "scripts")


def read(name):
    return open(os.path.join(SCRIPTS, name), encoding="utf-8").read()


def test_displays_quick_modes_carry_matching_glyphs():
    """ICON-1: given the Displays quick-mode buttons, when they render, then
    Extend carries arrow-expand-horizontal and Duplicate carries
    flip-horizontal — not the save-move and comma-box glyphs the audit found."""
    text = read("displays.py")
    line = next(l for l in text.splitlines() if l.startswith("I_LAPTOP"))
    assert '"\\U000f084e"' in line and '"\\U000f10e7"' in line, line
    assert '"\\U000f0e27"' not in text and '"\\U000f0e2b"' not in text


def test_balanced_carries_the_scale_glyph_everywhere():
    """ICON-2: given the shared PROFILES constant (the Power & sleep POWER MODE
    row and the quick settings battery card segment), when the chips render,
    then Balanced carries scale-balance, not the folder-plus glyph."""
    text = read("power_mode.py")
    line = next(l for l in text.splitlines() if '"balanced"' in l)
    assert "\\U000f05d1" in line and "\\U000f0b9d" not in text, line


def test_the_battery_cards_embedded_title_uses_the_battery_glyph():
    """ICON-3: given the quick settings battery card's embedded title, when it
    renders, then the word Battery carries the battery glyph, not power."""
    text = read("control-center.py")
    assert '"\\U000f0079  Battery"' in text and "I_POWER}  Battery" not in text
