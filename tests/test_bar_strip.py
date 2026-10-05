"""The strip behind the bar's pills is a switch in Settings (roadmap 2.4): on by
default, and turning it off makes the strip transparent without a Hyprland reload."""

import ast
import os
import re
import shutil
import textwrap

import pytest
import settings_store as store
import theme
from conftest import ROOT, SCRIPTS, THEMES

STYLE = os.path.join(ROOT, "config", "waybar", "bar", "style.css")


def define_colors(css):
    return dict(re.findall(r"@define-color\s+(\w+)\s+([^;]+);", css))


def test_the_setting_is_on_by_default_saved_and_checked(tmp_path):
    """STRIP-1: given nothing saved, then bar_strip is on; when it is saved off,
    then load reads it back; when a value that is not on or off is saved, then
    the store refuses it, and a hand-edited one falls back to on."""
    assert store.load(str(tmp_path))["bar_strip"] is True
    xkb = tmp_path / "xkb"
    xkb.mkdir()
    for name in ("us", "ir"):
        (xkb / name).write_text("")
    store.save(dict(store.DEFAULTS, bar_strip=False), str(tmp_path), str(xkb))
    assert store.load(str(tmp_path))["bar_strip"] is False
    with pytest.raises(ValueError):
        store.save(dict(store.DEFAULTS, bar_strip="off"), str(tmp_path), str(xkb))
    (tmp_path / "hypr" / "user-settings.json").write_text('{"bar_strip": "off"}')
    assert store.load(str(tmp_path))["bar_strip"] is True


@pytest.mark.parametrize("theme_id", ["summer-night", "nami"])
def test_the_strip_colors_follow_the_setting(monkeypatch, theme_id):
    """STRIP-2: given the bar colors are generated, when bar_strip is on, then
    bar_strip is the theme's fg and bar_strip_edge its bar_edge; when it is off,
    then both are fully transparent."""
    t = theme.palette.theme(theme_id, THEMES)
    monkeypatch.setattr(
        theme.store, "load", lambda: dict(store.DEFAULTS, bar_strip=True)
    )
    on = define_colors(theme.waybar_css(t))
    assert on["bar_strip"] == t["colors"]["fg"]
    assert on["bar_strip_edge"] == t["colors"]["bar_edge"]
    monkeypatch.setattr(
        theme.store, "load", lambda: dict(store.DEFAULTS, bar_strip=False)
    )
    off = define_colors(theme.waybar_css(t))
    assert off["bar_strip"] == "alpha(@fg, 0)"
    assert off["bar_strip_edge"] == "alpha(@bar_edge, 0)"


def test_the_bar_paints_the_strip_colors_and_keeps_its_edge():
    """STRIP-3: given the bar style, when it renders, then window#waybar paints
    its background with @bar_strip and its 5px bottom edge with @bar_strip_edge."""
    with open(STYLE, encoding="utf-8") as f:
        rule = re.search(r"^window#waybar \{([^}]*)\}", f.read(), re.MULTILINE).group(1)
    assert "background-color: @bar_strip;" in rule
    assert "border-bottom-color: @bar_strip_edge;" in rule
    assert "border-bottom-width: 5px;" in rule


def test_theme_py_bar_writes_only_the_bar_colors(tmp_path, monkeypatch):
    """STRIP-4: given an installed config, when `theme.py bar` runs, then it
    rewrites the bar colors file and the bar style (same text), and writes no
    Hyprland theme file."""
    shutil.copytree(THEMES, tmp_path / "hypr" / "themes")
    (tmp_path / "hypr" / "themes" / "current").write_text("nami\n")
    style = tmp_path / "waybar" / "bar" / "style.css"
    style.parent.mkdir(parents=True)
    style.write_text("window#waybar {}\n")
    monkeypatch.setattr(
        theme.store, "load", lambda: dict(store.DEFAULTS, bar_strip=False)
    )
    theme.write_bar(str(tmp_path))
    colors = define_colors((tmp_path / "waybar" / "colors" / "current.css").read_text())
    assert colors["bar_strip"] == "alpha(@fg, 0)"
    assert colors["fg"] == theme.palette.theme("nami", THEMES)["colors"]["fg"]
    assert style.read_text() == "window#waybar {}\n"
    assert not (tmp_path / "hypr" / "themes" / "current.lua").exists()
    assert not (tmp_path / "hypr" / "hyprlock-colors.conf").exists()


def settings_method(name):
    """One method of settings.py's Settings class, as a plain function (the
    module itself needs a display to import)."""
    with open(os.path.join(SCRIPTS, "settings.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Settings"
    )
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return textwrap.dedent(ast.unparse(fn))


class FakeSwitchPage:
    def __init__(self):
        self.rows = []

    def page_box(self, *_):
        return self

    def append(self, row):
        self.rows.append(row)

    def switch_row(self, title, desc, s, key):
        return key


def test_the_look_page_switch_saves_and_repaints_the_bar(tmp_path, monkeypatch):
    """STRIP-5: given the Look & behavior page, then it has a switch for
    bar_strip; when the person turns it, then Settings saves bar_strip and runs
    `theme.py bar`, and another switch does not run it."""
    spawned, saved = [], []
    fake_store = type(
        "Store",
        (),
        {
            "load": staticmethod(lambda: dict(store.DEFAULTS)),
            "save": staticmethod(saved.append),
            "paths": staticmethod(
                lambda: (str(tmp_path / "a.json"), str(tmp_path / "a.lua"))
            ),
        },
    )
    (tmp_path / "a.lua").write_text("")
    ns = {
        "store": fake_store,
        "spawn": spawned.append,
        "THEME_PY": "theme.py",
        "os": os,
    }
    # the repo's own settings.py source, not outside input
    exec(settings_method("look_page"), ns)  # noqa: S102
    exec(settings_method("save"), ns)  # noqa: S102

    page = FakeSwitchPage()
    ns["look_page"](page)
    assert "bar_strip" in page.rows

    error = type(
        "Label", (), {"set_label": lambda *_: None, "set_visible": lambda *_: None}
    )()
    host = type("Host", (), {"error": error})()
    ns["save"](host, bar_strip=False)
    assert saved[-1]["bar_strip"] is False
    assert spawned == [["theme.py", "bar"]]
    ns["save"](host, gaps=False)
    assert spawned == [["theme.py", "bar"]]
