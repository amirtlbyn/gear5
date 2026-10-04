"""The Shortcuts page of Settings (spec KEYS, session 2). settings.py needs a display to
import, so these tests run its methods as plain functions on a small stand-in page: the
store is the real one on a temporary folder, `hyprctl binds` is a given list, and the
window, surface and labels are fakes."""

import types

import lua_binds
import pytest
import settings_store as store
import shortcuts
from test_bar_strip import settings_method
from test_theme_page import module_constant

METHODS = (
    "shortcut_rows",
    "shortcut_stop",
    "on_shortcut_key",
    "shortcut_record",
    "shortcut_set",
    "shortcut_reset_all",
)
ESCAPE, KEY_Q = 65307, 113
SUPER = 64


class FakeLabel:
    def __init__(self):
        self.text, self.visible = "", False

    def set_label(self, text):
        self.text = text

    def get_label(self):
        return self.text

    def set_visible(self, visible):
        self.visible = visible

    def get_visible(self):
        return self.visible


class FakeSurface:
    def __init__(self):
        self.calls = []

    def restore_system_shortcuts(self):
        self.calls.append("restore")


class FakeWindow:
    def __init__(self):
        self.surface, self.removed = FakeSurface(), []

    def get_surface(self):
        return self.surface

    def remove_controller(self, ctl):
        self.removed.append(ctl)

    def get_display(self):
        self.groups = []

        def translate_key(keycode, state, group):  # the plain key is the keycode here
            self.groups.append(group)
            return True, keycode, 0, 0, 0

        return types.SimpleNamespace(translate_key=translate_key)


class Page:
    """Settings, reduced to what the shortcut methods use."""

    def __init__(self, tmp_path, live=()):
        config = str(tmp_path)
        ns = dict(
            store=types.SimpleNamespace(load=lambda: store.load(config), save=lambda s: store.save(s, config, "/none")),
            shortcuts=types.SimpleNamespace(
                catalog=lambda: shortcuts.catalog(lua_binds.HYPRLAND_LUA),
                keys_text=shortcuts.keys_text,
                conflict=shortcuts.conflict,
                live_binds=lambda: list(live),
            ),
            Gdk=types.SimpleNamespace(KEY_Escape=ESCAPE, keyval_name=lambda keyval: chr(keyval)),
            MOD_MASKS=(("SUPER", SUPER), ("CTRL", 4), ("ALT", 8), ("SHIFT", 1)),
            MODIFIER_KEYS=set(),
        )
        for name in METHODS:
            exec(settings_method(name), ns)  # noqa: S102 - the repo's own settings.py source
            setattr(self, name, types.MethodType(ns[name], self))
        self.win, self.error, self.rebuilt = FakeWindow(), FakeLabel(), []
        self.shortcut_errors = {name: FakeLabel() for name, *_rest in self.shortcut_rows()}
        self.config, self.recording = config, None

    def save(self, **changes):
        store.save(dict(store.load(self.config), **changes), self.config, "/none")

    def rebuild(self, key):
        self.rebuilt.append(key)

    def saved(self):
        return store.load(self.config)["shortcuts"]

    def lua(self):
        with open(store.paths(self.config)[1]) as f:
            return f.read()


def test_keys1_the_page_lists_every_shortcut_in_its_group_with_the_keys_now(tmp_path):
    """KEYS-1: Given a saved SUPER + W for windows.close and Off for apps.files, when the
    page lists the shortcuts, then every shortcut of hyprland.lua is there in a group that
    has a heading, with the saved keys, "" for Off, and the default keys for the rest; and
    the page is in the page list right after Keyboard."""
    page = Page(tmp_path)
    page.save(shortcuts={"windows.close": "SUPER + W", "apps.files": ""})

    rows = {name: (group, keys) for name, _label, group, keys, _default in page.shortcut_rows()}
    catalog = shortcuts.catalog(lua_binds.HYPRLAND_LUA)
    pages = [key for key, _icon, _name in module_constant("PAGES")]
    headings = module_constant("SHORTCUT_GROUPS")

    assert set(rows) == {name for name, *_rest in catalog}
    assert {group for group, _keys in rows.values()} <= set(headings)
    assert rows["windows.close"] == ("windows", "SUPER + W")
    assert rows["apps.files"] == ("apps", "")
    assert rows["windows.fullscreen"][1] == "SUPER + F"
    assert pages[pages.index("keyboard") + 1] == "shortcuts"


def test_keys3_taken_keys_and_a_plain_letter_are_refused_with_the_reason(tmp_path):
    """KEYS-3: Given keys of another shortcut, keys of a desk bind Hyprland has, and a
    plain letter, when each is recorded for windows.close, then the row shows why (naming
    the other shortcut for the first) and nothing is saved."""
    live = [{"modmask": SUPER, "key": "1", "description": ""}]
    page = Page(tmp_path, live)
    error = page.shortcut_errors["windows.close"]

    page.shortcut_record("windows.close", ["SUPER"], "e")
    taken = error.text
    page.shortcut_record("windows.close", ["SUPER"], "1")
    desk = error.text
    page.shortcut_record("windows.close", [], "a")
    plain = error.text

    assert taken == "SUPER + E: already used by “File manager”"
    assert desk == "SUPER + 1: already used by another desktop key (SUPER + 1)"
    assert plain == "A: needs SUPER, ALT, CTRL or SHIFT"
    assert error.visible
    assert page.saved() == {}
    assert page.rebuilt == []


@pytest.mark.skipif(lua_binds.LUAJIT is None, reason="luajit is not installed")
def test_keys4_off_saves_nothing_for_the_keys_and_the_lua_binds_none(tmp_path):
    """KEYS-4: Given the user turns apps.files off, when the choice is saved, then the
    saved keys are "", the row has no keys (the page shows Off) and the written Lua
    binds nothing for that shortcut."""
    page = Page(tmp_path)

    page.shortcut_set("apps.files", "")

    binds = lua_binds.run(user_settings=page.lua())
    row = next(r for r in page.shortcut_rows() if r[0] == "apps.files")
    assert page.saved() == {"apps.files": ""}
    assert shortcuts.keys_label(row[3]) == "Off"
    assert not [b for b in binds if b["description"].startswith("apps.files|")]
    assert "SUPER + E" not in lua_binds.by_keys(binds)
    assert page.rebuilt == ["shortcuts"]


def test_keys5_reset_takes_one_saved_change_away_and_reset_all_takes_every_one(tmp_path):
    """KEYS-5: Given three saved changes, when one is reset, then only that entry is
    gone; when Reset all is picked, then the saved map is empty and the page is drawn
    again each time."""
    page = Page(tmp_path)
    page.save(shortcuts={"windows.close": "SUPER + W", "apps.files": "", "system.lock": "SUPER + X"})

    page.shortcut_set("windows.close", None)
    after_one = page.saved()
    page.shortcut_reset_all()

    assert after_one == {"apps.files": "", "system.lock": "SUPER + X"}
    assert page.saved() == {}
    assert page.rebuilt == ["shortcuts", "shortcuts"]


def test_keys7_escape_while_recording_stops_and_changes_nothing(tmp_path):
    """KEYS-7: Given a recording of windows.close, when Escape is pressed with no
    modifier, then the recording ends, the system shortcuts are restored, the controller
    is removed, the button has its old text and nothing is saved."""
    page = Page(tmp_path)
    button, ctl = FakeLabel(), object()
    button.set_label("Press the new keys… (Esc cancels)")
    page.recording = ("windows.close", button, "SUPER + Q", ctl)

    handled = page.on_shortcut_key(ctl, ESCAPE, ESCAPE, 0)

    assert handled
    assert page.recording is None
    assert page.win.surface.calls == ["restore"]
    assert page.win.removed == [ctl]
    assert button.text == "SUPER + Q"
    assert page.saved() == {}
    assert page.rebuilt == []


def test_a_shifted_symbol_records_its_plain_key_on_the_first_layout(tmp_path):
    """SUPER+SHIFT+1 arrives as "exclam"; the recorded keys use the plain "1", looked up
    on the first layout (group 0), so a Persian layout gives no Arabic key names."""
    page = Page(tmp_path)
    button = FakeLabel()
    page.recording = ("windows.close", button, "SUPER + Q", "ctl")

    page.on_shortcut_key(None, ord("!"), ord("1"), SUPER | 1)

    assert page.saved() == {"windows.close": "SUPER + SHIFT + 1"}
    assert page.win.groups == [0]
    assert page.win.surface.calls == ["restore"] and page.win.removed == ["ctl"]
