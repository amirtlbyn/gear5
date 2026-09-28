"""The desktop's two fonts: the swap in every popup's CSS, and what theme.py
writes for the bar, swaync, hyprlock and kitty."""

import os
import shutil

import fonts
import palette
import settings_store as store
import theme
from conftest import THEMES


def chosen(monkeypatch, en, fa):
    monkeypatch.setattr(
        store, "load", lambda config=store.CONFIG: dict(store.DEFAULTS, font_en=en, font_fa=fa)
    )


def test_swap_substitutes_only_the_two_default_names(monkeypatch):
    """FONT-2, INV-1: given a popup's CSS, when fonts are chosen, then only the
    two default family names change; with the defaults saved, nothing does; a
    name the CSS doesn't mention is left alone."""
    css = (
        '.popup { font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif; }\n'
        '.fa { font-family: "Vazirmatn", "JetBrainsMono Nerd Font", sans-serif; }\n'
        '.mono { font-family: "JetBrainsMono Nerd Font", monospace; }\n'
    )
    chosen(monkeypatch, "FiraCode Nerd Font", "Vazir")
    out = fonts.swap(css)
    assert '"FiraCode Nerd Font", "Vazir", sans-serif' in out
    assert '"Vazir", "FiraCode Nerd Font", sans-serif' in out
    assert '"FiraCode Nerd Font", monospace' in out
    assert "JetBrainsMono" not in out and '"Vazirmatn"' not in out
    chosen(monkeypatch, store.DEFAULTS["font_en"], store.DEFAULTS["font_fa"])
    assert fonts.swap(css) == css
    assert fonts.pango("JetBrainsMono Nerd Font Bold 9") == "JetBrainsMono Nerd Font Bold 9"
    chosen(monkeypatch, "FiraCode Nerd Font", "Vazir")
    assert fonts.pango("JetBrainsMono Nerd Font Bold 9") == "FiraCode Nerd Font Bold 9"


def installed(tmp_path, monkeypatch, en=None, fa=None):
    """A config tree like the real one; returns its paths."""
    cfg = tmp_path / "config"
    (cfg / "hypr" / "themes").mkdir(parents=True)
    for f in os.listdir(THEMES):
        shutil.copy(os.path.join(THEMES, f), cfg / "hypr" / "themes" / f)
    if en or fa:
        monkeypatch.setattr(
            store, "load", lambda config=store.CONFIG: dict(store.DEFAULTS, font_en=en, font_fa=fa)
        )
    return str(cfg)


def test_write_all_puts_the_chosen_fonts_in_every_generated_file(tmp_path, monkeypatch):
    """With fonts chosen, the generated colors file the bar and swaync import
    carries the font rule, and hyprlock's colors carry the $font."""
    cfg = installed(tmp_path, monkeypatch, en="FiraCode Nerd Font", fa="Vazir")
    theme.write_all("summer-night", config=cfg)
    css = open(os.path.join(cfg, "waybar", "colors", "current.css")).read()
    assert "@define-color fg #d3c6aa;" in css
    assert '* { font-family: "FiraCode Nerd Font", "Vazir", FontAwesome, sans-serif; }' in css
    hypr = open(os.path.join(cfg, "hypr", "hyprlock-colors.conf")).read()
    assert "$font = FiraCode Nerd Font Bold" in hypr


def test_write_all_with_default_fonts_writes_the_default_look(tmp_path, monkeypatch):
    """With nothing chosen, the rule names today's fonts and nothing else
    changes (INV-3). The real machine's own choice is patched out: this test
    is about the defaults, not about ~/.config."""
    chosen(monkeypatch, store.DEFAULTS["font_en"], store.DEFAULTS["font_fa"])
    cfg = installed(tmp_path, monkeypatch)
    theme.write_all("summer-night", config=cfg)
    css = open(os.path.join(cfg, "waybar", "colors", "current.css")).read()
    assert '* { font-family: "JetBrainsMono Nerd Font", "Vazirmatn", FontAwesome, sans-serif; }' in css
    assert (
        "$font = JetBrainsMono Nerd Font Bold"
        in open(os.path.join(cfg, "hypr", "hyprlock-colors.conf")).read()
    )


def test_write_all_themes_kitty_and_points_its_include_at_the_generated_file(tmp_path, monkeypatch):
    """FONT-3: given an installed kitty, when the theme is applied, then
    colors/current.conf carries the theme's colors and the two fonts, and
    kitty.conf's include names it; without an include line kitty is left alone;
    without kitty nothing is written."""
    cfg = installed(tmp_path, monkeypatch, en="FiraCode Nerd Font", fa="Vazir")
    os.makedirs(os.path.join(cfg, "kitty", "colors"))
    open(os.path.join(cfg, "kitty", "kitty.conf"), "w").write(
        "include colors/everforest.conf\n\nfont_size 12.0\n"
    )
    theme.write_all("summer-night", config=cfg)
    conf = open(os.path.join(cfg, "kitty", "colors", "current.conf")).read()
    colors = palette.load("summer-night")
    assert "font_family      FiraCode Nerd Font" in conf
    assert "Vazir" in conf.splitlines()[2]  # the Persian symbol_map
    for kitty_name, role in theme.KITTY:
        line = next(l for l in conf.splitlines() if l.startswith(kitty_name))
        assert line.split()[-1].lower() == colors[role].lower(), kitty_name
    assert len(theme.KITTY) == 22  # 6 extra + the 16 ANSI colors
    assert "include colors/current.conf\n" in open(os.path.join(cfg, "kitty", "kitty.conf")).read()

    # kitty watches the files it loaded by inode: the writes must keep it, or
    # running kitty windows would never see the new colors (live reload)
    conf_ino = os.stat(os.path.join(cfg, "kitty", "colors", "current.conf")).st_ino
    calls = []
    monkeypatch.setattr(theme, "run", lambda *a, **k: (calls.append(a), (0, "", ""))[1])
    theme.write_all("zoro", config=cfg)
    assert os.stat(os.path.join(cfg, "kitty", "colors", "current.conf")).st_ino == conf_ino
    assert any("-USR1" in " ".join(a[0]) for a in calls), "running kitties were not asked to reload"

    # a kitty.conf the user built themselves: no include line, nothing touched
    open(os.path.join(cfg, "kitty", "kitty.conf"), "w").write("font_size 11.0\n")
    theme.write_all("zoro", config=cfg)
    assert open(os.path.join(cfg, "kitty", "kitty.conf")).read() == "font_size 11.0\n"
    zoro = palette.load("zoro")
    line = next(
        l for l in open(os.path.join(cfg, "kitty", "colors", "current.conf")) if l.startswith("background")
    )
    assert line.split()[-1] == zoro["bg0"]


def test_write_all_skips_kitty_when_it_is_not_installed(tmp_path, monkeypatch):
    """No kitty directory -> no kitty files, no reload signal, everything else
    written."""
    cfg = installed(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(theme, "run", lambda *a, **k: (calls.append(a), (0, "", ""))[1])
    theme.write_all("summer-night", config=cfg)
    assert not os.path.exists(os.path.join(cfg, "kitty"))
    assert not any("-USR1" in " ".join(a[0]) for a in calls)
    assert os.path.exists(os.path.join(cfg, "waybar", "colors", "current.css"))
