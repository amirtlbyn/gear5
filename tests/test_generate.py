"""Summer night must look exactly as before the theme engine: same colors everywhere."""

import ast
import re
import shutil
import subprocess

import palette
import theme
from conftest import ROOT, THEMES

BEFORE = "50457f0"  # the commit before the theme engine


def old_file(path):
    return subprocess.run(
        ["git", "show", f"{BEFORE}:{path}"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def define_colors(css):
    return dict(re.findall(r"@define-color\s+(\w+)\s+([^;]+);", css))


def test_bar_colors_unchanged():
    new = define_colors(theme.waybar_css(palette.theme("summer-night", THEMES)))
    old = define_colors(old_file("config/waybar/colors/everforest.css"))
    assert {k: new[k] for k in old} == old


def test_bar_hardcoded_edges_unchanged():
    new = define_colors(theme.waybar_css(palette.theme("summer-night", THEMES)))
    for name, color in dict(
        bar_edge="#7d6a40",
        edge_deep="#161a1d",
        blue_edge="#366660",
        green_edge="#556a35",
        red_edge="#951c1f",
        red_hover="#f08b8d",
    ).items():
        assert new[name] == color


def old_popup_palette(script):
    src = old_file(f"config/waybar/scripts/{script}")
    m = re.search(r'"everforest":\s*dict\((.*?)\)(?=,\s*\n\s*"everforest-light")', src, re.S)
    call = ast.parse("dict(" + m.group(1) + ")", mode="eval").body
    return {kw.arg: kw.value.value for kw in call.keywords}


def test_every_popup_gets_its_old_colors():
    deep = {"wifi-menu.py", "power-popup.py", "calendar-popup.py"}
    for script in (
        "calculator.py",
        "clipboard.py",
        "control-center.py",
        "emoji-picker.py",
        "launcher.py",
        "power-popup.py",
        "volume-popup.py",
        "wifi-menu.py",
        "worldclock.py",
        "calendar-popup.py",
    ):
        old = old_popup_palette(script)
        new = palette.load("summer-night", THEMES, **({"edge": "edge_deep"} if script in deep else {}))
        assert {k: new[k] for k in old} == old, script


def test_hyprland_values_unchanged(tmp_path):
    lua = theme.hypr_lua(palette.theme("summer-night", THEMES), None)
    old = old_file("config/hypr/themes/summer-night.lua")
    for key in ("fg", "bg5", "shadow", "shadow_inactive"):
        was = re.search(rf'\b{key}\s*=\s*"([^"]+)"', old).group(1)
        assert f'{key} = "{was}"' in lua, key
    assert 'gtk = "Adwaita:dark"' in lua


def test_write_all_writes_every_generated_file(tmp_path):
    shutil.copytree(THEMES, tmp_path / "hypr" / "themes")
    (tmp_path / "hypr" / "wallpapers").mkdir()
    (tmp_path / "hypr" / "wallpapers" / "summer-night.png").write_bytes(b"x")
    t = theme.write_all("summer-night", str(tmp_path))
    assert t["id"] == "summer-night"
    assert (tmp_path / "hypr" / "themes" / "current").read_text() == "summer-night\n"
    assert "summer-night.png" in (tmp_path / "hypr" / "themes" / "current.lua").read_text()
    lock = (tmp_path / "hypr" / "hyprlock-colors.conf").read_text()
    assert "$fg = rgb(d3c6aa)" in lock and "summer-night.png" in lock
    assert "@define-color bg0 #2d353b;" in (tmp_path / "waybar" / "colors" / "current.css").read_text()


def test_missing_wallpaper_gives_empty_path(tmp_path):
    shutil.copytree(THEMES, tmp_path / "hypr" / "themes")
    theme.write_all("summer-night", str(tmp_path))
    assert 'wallpaper = ""' in (tmp_path / "hypr" / "themes" / "current.lua").read_text()
    assert "$wallpaper = \n" in (tmp_path / "hypr" / "hyprlock-colors.conf").read_text()


def test_unknown_theme_writes_summer_night(tmp_path):
    shutil.copytree(THEMES, tmp_path / "hypr" / "themes")
    assert theme.write_all("nope", str(tmp_path))["id"] == "summer-night"


def test_reload_skips_hyprctl_reload_when_autoreload_is_on_or_unknown(monkeypatch):
    for answer in ('{"option": "misc:disable_autoreload", "bool": false}', "", "not json"):
        calls = []
        monkeypatch.setattr(
            theme, "run", lambda argv, a=answer: calls.append(argv) or (a if "getoption" in argv else "")
        )
        theme.reload()
        assert ["hyprctl", "reload"] not in calls, answer
        assert ["swaync-client", "--reload-css"] in calls


def test_reload_reloads_when_autoreload_is_off(monkeypatch):
    calls = []
    monkeypatch.setattr(
        theme, "run", lambda argv: calls.append(argv) or ('{"bool": true}' if "getoption" in argv else "")
    )
    theme.reload()
    assert ["hyprctl", "reload"] in calls
