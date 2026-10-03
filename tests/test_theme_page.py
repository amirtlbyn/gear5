"""The Theme page's GIF controls and the page list (spec GIFT). settings.py needs a
display to import, so these tests run its source: the module constants are read from
the file, and the methods are run as plain functions with small fakes."""

import ast
import json
import os
import types

import theme_gif
from conftest import ROOT, SCRIPTS
from test_bar_strip import settings_method
from test_gif import make_gif


def module_constant(name):
    with open(os.path.join(SCRIPTS, "settings.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == name)
    return ast.literal_eval(node.value)


def test_there_is_no_stickers_or_lock_screen_page_and_their_names_open_theme():
    """GIFT-1: given the Settings page list, when it is read, then it has no stickers
    page and no lockscreen page; and given an old command asking for either, then the
    page it opens is theme."""
    keys = [key for key, _icon, _name in module_constant("PAGES")]
    old = module_constant("OLD_PAGES")

    assert "stickers" not in keys and "lockscreen" not in keys
    assert old["stickers"] == "theme" and old["lockscreen"] == "theme"


def test_a_picked_gif_is_copied_in_a_bad_one_is_refused_and_a_removed_one_goes(tmp_path, monkeypatch):
    """GIFT-6: given the theme in use, when a GIF is picked, then themes/<id>.gif is
    that GIF, the bar's frames are made at once and the lock file is rewritten; the card
    of the theme in use then flips through the frame files on one timer, another theme's
    card stays on its first picture, and no timer runs once the page is left; when a
    file that is not a GIF is picked, then the page shows the refusal and the old GIF
    stays; when the GIF is removed, then the file and the frames go."""
    config = tmp_path / "config"
    themes = config / "hypr" / "themes"
    themes.mkdir(parents=True)
    (themes / "current").write_text("summer-night\n")
    monkeypatch.setattr(theme_gif, "CONFIG", str(config))
    good, bad = tmp_path / "good.gif", tmp_path / "bad.gif"
    good.write_bytes(make_gif(10, 10))
    bad.write_bytes(b"not a gif at all")
    ran, rebuilt = [], []
    ns = dict(
        theme_gif=theme_gif,
        THEME_PY="theme.py",
        subprocess=types.SimpleNamespace(run=lambda cmd, **_kw: ran.append(cmd)),
        in_background=lambda work, done: done(_outcome(work)),
    )
    exec(settings_method("set_theme_gif"), ns)  # noqa: S102 - the repo's own settings.py source
    page = types.SimpleNamespace(busy=False, rebuild=rebuilt.append, gif_flip_stop=lambda: None)
    frames = os.path.join(theme_gif.gif_dir(), "current")

    ns["set_theme_gif"](page, "summer-night", str(good))
    assert (themes / "summer-night.gif").read_bytes() == good.read_bytes()
    assert os.path.isdir(frames)
    assert ran == [["theme.py", "lock"]] and rebuilt == ["theme"]

    timers = {}
    flip = dict(
        json=json,
        os=os,
        theme_gif=types.SimpleNamespace(gif_dir=theme_gif.gif_dir, gif=lambda t: str(themes / f"{t}.gif")),
        first_frame=lambda path: ("first frame of", path),
        palette=types.SimpleNamespace(current=lambda: "summer-night"),
        GLib=types.SimpleNamespace(
            timeout_add=lambda ms, fn: timers.setdefault(max(timers, default=0) + 1, (ms, fn)) and max(timers),
            source_remove=lambda tid: timers.pop(tid),
        ),
    )
    exec(settings_method("gif_flip_start"), flip)  # noqa: S102 - the repo's own settings.py source
    exec(settings_method("gif_flip_stop"), flip)  # noqa: S102 - the repo's own settings.py source
    in_use, other = FakePicture(), FakePicture()
    card = types.SimpleNamespace(
        page="theme",
        win=types.SimpleNamespace(get_visible=lambda: True),
        gif_pictures={"summer-night": in_use, "zoro": other},
        gif_timer=None,
        gif_playing=None,
        gif_flip_stop=lambda restore=True: flip["gif_flip_stop"](card, restore),
    )
    flip["gif_flip_start"](card)
    assert [os.path.basename(f) for f in in_use.files] == ["000.png"] and other.files == []
    ((fired, (_ms, tick)),) = timers.items()
    del timers[fired]  # GLib drops a timer whose callback returns False
    tick()
    assert [os.path.basename(f) for f in in_use.files] == ["000.png", "001.png"] and len(timers) == 1
    flip["gif_flip_stop"](card)
    assert timers == {} and in_use.files[-1] == ("first frame of", str(themes / "summer-night.gif"))
    assert other.files == []

    ns["set_theme_gif"](page, "summer-night", str(bad))
    assert "Pick a GIF file" in page.gif_error
    assert (themes / "summer-night.gif").read_bytes() == good.read_bytes()

    ns["set_theme_gif"](page, "summer-night", None)
    assert not (themes / "summer-night.gif").exists()
    assert not os.path.exists(frames)


class FakePicture:
    def __init__(self):
        self.files = []

    def set_filename(self, path):
        self.files.append(path)

    def set_paintable(self, paintable):
        self.files.append(paintable)


def _outcome(work):
    try:
        return work()
    except Exception as e:  # noqa: BLE001 - what in_background hands to done()
        return e


def test_the_gif_section_has_its_three_controls_and_the_bar_gif_opens_theme():
    """GIFT-9: given the Theme page's GIF section, when it is built, then it has the
    switches gif_bar and gif_switch and the Bar GIF plays dropdown; and the bar's GIF
    on-click opens the Theme page."""
    titles, switches, dropdowns = [], [], []

    class Dropdown:
        @staticmethod
        def new_from_strings(names):
            dropdowns.append(names)
            return types.SimpleNamespace(
                set_valign=lambda _a: None, set_selected=lambda _i: None, connect=lambda *_a: None
            )

    class Row:
        def append(self, _widget):
            pass

    class Page:
        def append(self, row):
            pass

        def switch_row(self, title, _desc, _s, key):
            titles.append(title)
            switches.append(key)

        def row(self, title, _desc):
            titles.append(title)
            return Row(), None

    ns = dict(
        Gtk=types.SimpleNamespace(DropDown=Dropdown, Align=types.SimpleNamespace(CENTER=0)),
        store=types.SimpleNamespace(load=lambda: dict(bar_gif="ac")),
        BAR_GIF_NAMES=module_constant("BAR_GIF_NAMES"),
    )
    exec(settings_method("gif_section"), ns)  # noqa: S102 - the repo's own settings.py source
    ns["gif_section"](Page(), Page())

    assert titles == ["GIF on the bar", "Bar GIF plays", "GIF on theme switch"]
    assert switches == ["gif_bar", "gif_switch"] and len(dropdowns) == 1
    with open(os.path.join(ROOT, "config", "waybar", "bar", "modules.jsonc")) as f:
        modules = f.read()
    assert '"on-click": "~/.config/waybar/scripts/settings.py theme"' in modules.split('"image#character"')[1].split("}")[0]
