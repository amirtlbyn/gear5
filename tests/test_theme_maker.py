"""theme_maker.py: derive four picks into a full readable theme, and save, rename
and delete a made theme."""

import json
import os
import shutil

import palette
import pytest
import theme_maker
from conftest import THEMES
from test_contrast import contrast


def _themes_copy(tmp_path):
    d = tmp_path / "themes"
    shutil.copytree(THEMES, d)
    return str(d)


def test_derive_builds_every_role_and_meets_every_pair_dark_and_light():
    """GEAR-12: given four picked colors — dark, light, a mid-grey background, and an
    accent equal to the background — when derive() builds the theme, then every
    color role a built-in theme has exists, and every pair in theme_maker.PAIRS
    meets its minimum contrast."""
    roles = set(palette.read("summer-night", THEMES)["colors"])
    cases = {
        "dark": ("#2d353b", "#d3c6aa", "#a7c080", "#7fbbb3"),
        "light": ("#faf6ee", "#2b2b2b", "#2f7d32", "#1f6fb2"),
        "mid-grey background, light text": ("#808080", "#f5f5f5", "#3a7d3a", "#3060a0"),
        "mid-grey background, dark text": ("#808080", "#101010", "#3a7d3a", "#3060a0"),
        "accent equal to background": ("#2d353b", "#d3c6aa", "#2d353b", "#7fbbb3"),
    }
    bad = []
    for label, (bg, fg, accent, accent2) in cases.items():
        colors = theme_maker.derive(bg, fg, accent, accent2)
        assert set(colors) == roles, label
        for text, background, minimum in theme_maker.PAIRS:
            ratio = contrast(colors[text], colors[background])
            if ratio < minimum:
                bad.append(f"{label}: {text} on {background} = {ratio:.2f} (needs {minimum})")
    assert not bad, "\n".join(bad)
    # derived from the picks, not replaced: picks that already read well stay as picked,
    # and no accent collapses to black or white
    for label in ("dark", "light"):
        bg, fg, accent, accent2 = cases[label]
        colors = theme_maker.derive(bg, fg, accent, accent2)
        assert (colors["bg0"], colors["fg"], colors["green"]) == (bg, fg, accent), label
        for role in ("blue", "red", "yellow", "aqua", "purple", "grey"):
            assert colors[role] not in ("#000000", "#ffffff"), f"{label}: {role}"


def test_check_name_refuses_blank_long_or_duplicate_names(tmp_path):
    """GEAR-14: given an empty, blank, 41-character, or already-used name (in any
    case), when check_name() checks it, then it refuses and says why; a good name
    is accepted."""
    themes = _themes_copy(tmp_path)
    for name in ("", "   ", "x" * 41, "summer night", "SUMMER NIGHT"):
        assert theme_maker.check_name(name, themes) is not None
    assert theme_maker.check_name("Nika", themes) is None
    # a theme being edited or renamed may keep its own name
    assert theme_maker.check_name("Summer night", themes, exclude_id="summer-night") is None


def test_save_writes_a_custom_theme_that_appears_and_never_overwrites(tmp_path):
    """GEAR-15: given a derived theme, when save() writes it, then the file has the
    developer's name and "custom": true and the theme appears in
    palette.available(); saving under the same name again gets a different id,
    without touching the first file. INV-1: save() refuses to replace a built-in
    theme's file."""
    themes = _themes_copy(tmp_path)
    colors = theme_maker.derive("#2d353b", "#d3c6aa", "#a7c080", "#7fbbb3")

    theme_id = theme_maker.save("Nika", colors, themes=themes)
    with open(os.path.join(themes, theme_id + ".json")) as f:
        data = json.load(f)
    assert data["name"] == "Nika"
    assert data["custom"] is True
    assert any(i == theme_id and n == "Nika" for i, n, _c in palette.available(themes))

    second_id = theme_maker.save("Nika", colors, themes=themes)
    assert second_id != theme_id
    assert os.path.isfile(os.path.join(themes, theme_id + ".json"))
    assert os.path.isfile(os.path.join(themes, second_id + ".json"))

    with pytest.raises(ValueError):
        theme_maker.save("Not Luffy", colors, theme_id="luffy", themes=themes)
    with open(os.path.join(themes, "luffy.json")) as f:
        assert json.load(f)["name"] == "Luffy"


def test_rename_and_delete_a_custom_theme_switch_to_summer_night_when_in_use(tmp_path):
    """GEAR-16: given a custom theme, when rename() runs, then its file keeps its id
    and colors but gets the new name; when delete() removes the theme in use, then
    it calls the injected apply callback with Summer night before the file is
    gone; deleting a custom theme that is not in use does not call apply.
    INV-1: rename() and delete() refuse a built-in theme."""
    themes = _themes_copy(tmp_path)
    colors = theme_maker.derive("#2d353b", "#d3c6aa", "#a7c080", "#7fbbb3")
    theme_id = theme_maker.save("Nika", colors, themes=themes)

    theme_maker.rename(theme_id, "Gear 5", themes=themes)
    with open(os.path.join(themes, theme_id + ".json")) as f:
        data = json.load(f)
    assert data["name"] == "Gear 5"
    assert data["colors"] == colors
    assert data["custom"] is True

    with open(os.path.join(themes, "current"), "w") as f:
        f.write(theme_id + "\n")
    applied = []
    theme_maker.delete(theme_id, themes=themes, apply=applied.append)
    assert applied == [palette.DEFAULT]
    assert not os.path.isfile(os.path.join(themes, theme_id + ".json"))

    other_id = theme_maker.save("Zoro", colors, themes=themes)
    not_applied = []
    theme_maker.delete(other_id, themes=themes, apply=not_applied.append)
    assert not_applied == []
    assert not os.path.isfile(os.path.join(themes, other_id + ".json"))

    with pytest.raises(ValueError):
        theme_maker.rename("luffy", "Not Luffy", themes=themes)
    with pytest.raises(ValueError):
        theme_maker.delete("luffy", themes=themes)
    assert os.path.isfile(os.path.join(themes, "luffy.json"))
