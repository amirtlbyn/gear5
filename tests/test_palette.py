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


def test_single_wallpaper_shows_for_every_theme(tmp_path):
    """GEAR-1: one wallpaper file is used, no matter which theme is current."""
    d = themes_copy(tmp_path)
    wallpapers = tmp_path / "wallpapers"
    wallpapers.mkdir()
    (wallpapers / "wallpaper.png").write_bytes(b"x")
    (tmp_path / "themes" / "x.json").write_text(json.dumps({"name": "X", "colors": {}}))
    (tmp_path / "themes" / "current").write_text("summer-night\n")
    first = palette.wallpaper(str(wallpapers), d)
    (tmp_path / "themes" / "current").write_text("x\n")
    second = palette.wallpaper(str(wallpapers), d)
    assert first == second == str(wallpapers / "wallpaper.png")


def test_old_per_theme_picture_becomes_the_single_wallpaper_once(tmp_path):
    """GEAR-2: with no single wallpaper, the current theme's old per-theme picture
    is copied in as the single wallpaper, and the old file is not removed."""
    d = themes_copy(tmp_path)
    wallpapers = tmp_path / "wallpapers"
    wallpapers.mkdir()
    (wallpapers / "summer-night.jpg").write_bytes(b"old-picture")
    path = palette.wallpaper(str(wallpapers), d)
    assert path == str(wallpapers / "wallpaper.jpg")
    assert (wallpapers / "wallpaper.jpg").read_bytes() == b"old-picture"
    assert (wallpapers / "summer-night.jpg").exists()  # the old file stays


def test_no_wallpaper_gives_none(tmp_path):
    """GEAR-3: with no single wallpaper and no old per-theme picture, wallpaper()
    is None, so the desktop falls back to the current theme's bg0 color."""
    d = themes_copy(tmp_path)
    wallpapers = tmp_path / "wallpapers"
    assert palette.wallpaper(str(wallpapers), d) is None


def test_set_wallpaper_choose_and_remove_change_the_one_wallpaper(tmp_path):
    """GEAR-4: Choose copies a picture in that then shows for every theme; Remove
    clears it again."""
    d = themes_copy(tmp_path)
    wallpapers = tmp_path / "wallpapers"
    source = tmp_path / "chosen.png"
    source.write_bytes(b"chosen")
    palette.set_wallpaper(str(source), str(wallpapers))
    (tmp_path / "themes" / "x.json").write_text(json.dumps({"name": "X", "colors": {}}))
    (tmp_path / "themes" / "current").write_text("summer-night\n")
    first = palette.wallpaper(str(wallpapers), d)
    (tmp_path / "themes" / "current").write_text("x\n")
    second = palette.wallpaper(str(wallpapers), d)
    assert first == second == str(wallpapers / "wallpaper.png")
    assert (wallpapers / "wallpaper.png").read_bytes() == b"chosen"

    palette.set_wallpaper(None, str(wallpapers))
    assert palette.wallpaper(str(wallpapers), d) is None
    # Remove stays removed, even when the current theme still has an old picture
    (wallpapers / "x.jpg").write_bytes(b"old")
    assert palette.wallpaper(str(wallpapers), d) is None
