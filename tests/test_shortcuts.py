"""Named shortcuts in hyprland.lua (spec KEYS, session 1): each editable bind goes through
shortcut(name, label, keys, action), and the keys a person chose in Settings reach it
through user-settings.lua. The tests run the real hyprland.lua under luajit with a stub
`hl` that records each bind (tests/lua_binds.py)."""

import json
import os

import lua_binds
import pytest
import settings_store as store
import shortcuts
from conftest import ROOT

pytestmark = pytest.mark.skipif(lua_binds.LUAJIT is None, reason="luajit is not installed")

BEFORE = os.path.join(ROOT, "tests", "data", "binds-before.json")


@pytest.fixture
def xkb(tmp_path):
    d = tmp_path / "xkb"
    d.mkdir()
    for name in ("us", "ir"):
        (d / name).write_text("")
    return str(d)


def saved_lua(tmp_path, xkb, shortcuts_map):
    """The user-settings.lua that Settings writes for these shortcut choices."""
    store.save(dict(store.DEFAULTS, shortcuts=shortcuts_map), str(tmp_path), xkb)
    return (tmp_path / "hypr" / "user-settings.lua").read_text()


def test_catalog_reads_every_shortcut_line_of_hyprland_lua():
    """Every shortcut( call of hyprland.lua is read by catalog(), with its group and default keys."""
    with open(lua_binds.HYPRLAND_LUA) as f:
        calls = f.read().count("\nshortcut(")
    found = shortcuts.catalog(lua_binds.HYPRLAND_LUA)
    assert len(found) == calls
    assert ("windows.close", "Close window", "windows", "SUPER + Q") in found


def test_inv1_with_no_saved_keys_every_bind_is_as_before():
    """INV-1: Given no saved shortcut changes, when hyprland.lua runs, then every bind
    has the same keys, action, options and submap as before the conversion."""
    binds = lua_binds.run(user_settings=None)
    with open(BEFORE) as f:
        before = json.load(f)
    without_description = [dict(b, description="") for b in binds]
    assert without_description == before


def test_keys2_saved_keys_replace_the_old_keys(tmp_path, xkb):
    """KEYS-2: Given SUPER + W saved for windows.close, when hyprland.lua runs, then
    SUPER + W closes the window and SUPER + Q binds nothing."""
    lua = saved_lua(tmp_path, xkb, {"windows.close": "SUPER + W"})

    binds = lua_binds.by_keys(lua_binds.run(user_settings=lua))

    assert binds["SUPER + W"]["action"] == "hl.dsp.window.close()"
    assert "SUPER + Q" not in binds


def test_inv2_a_saved_change_touches_the_keys_only(tmp_path, xkb):
    """INV-2: Given SUPER + W saved for windows.resize, when hyprland.lua runs, then the
    action, options, description and submap of that bind stay and no other bind changes."""
    lua = saved_lua(tmp_path, xkb, {"windows.resize": "SUPER + W"})
    before = lua_binds.by_keys(lua_binds.run(user_settings=None))

    after = lua_binds.by_keys(lua_binds.run(user_settings=lua))

    assert after.pop("SUPER + W") == dict(before.pop("SUPER + R"), keys="SUPER + W")
    assert after == before


def test_keys6_bad_or_missing_saved_keys_leave_the_defaults(tmp_path):
    """KEYS-6: Given a saved map with an unknown name, a number and keys Hyprland
    rejects next to one good entry, when hyprland.lua runs, then the bad ones keep their
    default keys and the good one applies; a missing file or one with no return changes
    nothing; and load() drops the bad entries of the JSON."""
    mixed = (
        'return { shortcuts = { ["nothing.here"] = "SUPER + Z", ["apps.files"] = 5,'
        ' ["windows.close"] = "NOT KEYS", ["windows.fullscreen"] = "SUPER + W" } }'
    )

    binds = lua_binds.by_keys(lua_binds.run(user_settings=mixed, reject=("NOT KEYS",)))
    no_return = lua_binds.run(user_settings='hl.config({})')
    no_file = lua_binds.run(user_settings=None)
    (tmp_path / "hypr").mkdir()
    (tmp_path / "hypr" / "user-settings.json").write_text(
        '{"shortcuts": {"windows.close": "SUPER + W", "Bad Name": "SUPER + Z", "apps.files": 5}}'
    )

    assert binds["SUPER + W"]["action"] == "hl.dsp.window.fullscreen()"
    assert binds["SUPER + Q"]["action"] == "hl.dsp.window.close()"
    assert binds["SUPER + E"]["action"] == "hl.dsp.exec_cmd(nemo)"
    assert "SUPER + Z" not in binds
    assert no_return == no_file
    assert store.load(str(tmp_path))["shortcuts"] == {"windows.close": "SUPER + W"}


def test_inv3_a_saved_change_follows_its_name_when_the_default_keys_change(tmp_path, xkb):
    """INV-3: Given SUPER + W saved for windows.close and a hyprland.lua whose default
    keys for it are SUPER + X, when it runs, then SUPER + W closes the window."""
    with open(lua_binds.HYPRLAND_LUA) as f:
        moved = f.read().replace('mainMod .. " + Q", hl.dsp.window.close()', 'mainMod .. " + X", hl.dsp.window.close()')
    copy = tmp_path / "hyprland.lua"
    copy.write_text(moved)
    lua = saved_lua(tmp_path, xkb, {"windows.close": "SUPER + W"})

    binds = lua_binds.by_keys(lua_binds.run(user_settings=lua, lua_file=str(copy)))

    assert binds["SUPER + W"]["action"] == "hl.dsp.window.close()"
    assert "SUPER + X" not in binds
