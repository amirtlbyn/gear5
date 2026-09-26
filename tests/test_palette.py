import json
import os
import shutil

import palette
from conftest import THEMES


def themes_copy(tmp_path):
    d = tmp_path / "themes"
    shutil.copytree(THEMES, d)
    return str(d)


def test_known_theme_loads_its_colors():
    assert palette.load("summer-night", THEMES)["bg0"] == "#2d353b"


def test_unknown_or_broken_theme_falls_back_to_summer_night(tmp_path):
    d = themes_copy(tmp_path)
    (tmp_path / "themes" / "broken.json").write_text("{ not json")
    night = palette.load("summer-night", d)
    for theme_id in ("nope", "broken", "../etc/passwd", "", "it's", "Summer-Night", None):
        assert palette.theme(theme_id, d)["colors"] == night


def test_theme_only_overrides_what_it_lists(tmp_path):
    d = themes_copy(tmp_path)
    (tmp_path / "themes" / "pinkish.json").write_text(
        json.dumps({"name": "P", "colors": {"green": "#ff00aa"}})
    )
    colors = palette.load("pinkish", d)
    assert colors["green"] == "#ff00aa"
    assert colors["bg0"] == "#2d353b"


def test_alias_swaps_in_another_color():
    assert palette.load("summer-night", THEMES, edge="edge_deep")["edge"] == "#161a1d"


def test_current_reads_the_saved_id_and_ignores_a_bad_one(tmp_path):
    d = themes_copy(tmp_path)
    assert palette.current(d) == "summer-night"  # nothing saved yet
    (tmp_path / "themes" / "current").write_text("gone\n")
    assert palette.current(d) == "summer-night"
    (tmp_path / "themes" / "x.json").write_text(json.dumps({"name": "X", "colors": {}}))
    (tmp_path / "themes" / "current").write_text("x\n")
    assert palette.current(d) == "x"
    assert palette.load(None, d) == palette.load("x", d)


def test_wallpaper_found_by_theme_id_or_none(tmp_path):
    assert palette.wallpaper("summer-night", str(tmp_path)) is None
    (tmp_path / "summer-night.jpg").write_bytes(b"x")
    assert palette.wallpaper("summer-night", str(tmp_path)) == os.path.join(str(tmp_path), "summer-night.jpg")
