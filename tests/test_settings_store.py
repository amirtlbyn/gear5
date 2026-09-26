import json

import pytest
import settings_store as store


@pytest.fixture
def xkb(tmp_path):
    d = tmp_path / "xkb"
    d.mkdir()
    for name in ("us", "ir", "de"):
        (d / name).write_text("")
    return str(d)


def test_defaults_when_nothing_saved(tmp_path):
    assert store.load(str(tmp_path)) == store.DEFAULTS


def test_save_writes_json_and_lua_that_load_reads_back(tmp_path, xkb):
    s = store.save(dict(store.DEFAULTS, kb_layout=" US, de ", gaps=False), str(tmp_path), xkb)
    assert s["kb_layout"] == "us,de"
    assert store.load(str(tmp_path)) == s
    lua = (tmp_path / "hypr" / "user-settings.lua").read_text()
    assert 'kb_layout = "us,de"' in lua
    assert "gaps_in = 0, gaps_out = 0" in lua and "rounding = 0" in lua
    assert "tap_to_click = true" in lua and "enabled = true" in lua


def test_unknown_layout_is_refused_and_nothing_written(tmp_path, xkb):
    for bad in ("us,xx", "", "us;rm -rf", 'us",x="', "a,b,c,d,e"):
        with pytest.raises(ValueError):
            store.save(dict(store.DEFAULTS, kb_layout=bad), str(tmp_path), xkb)
    assert not (tmp_path / "hypr" / "user-settings.lua").exists()


def test_switch_must_be_on_or_off(tmp_path, xkb):
    with pytest.raises(ValueError):
        store.save(dict(store.DEFAULTS, gaps="no"), str(tmp_path), xkb)


def test_broken_or_foreign_saved_values_fall_back_to_defaults(tmp_path):
    (tmp_path / "hypr").mkdir()
    (tmp_path / "hypr" / "user-settings.json").write_text(
        json.dumps({"gaps": "yes", "animations": False, "x": 1})
    )
    s = store.load(str(tmp_path))
    assert s["gaps"] is True and s["animations"] is False and "x" not in s
    (tmp_path / "hypr" / "user-settings.json").write_text("{ broken")
    assert store.load(str(tmp_path)) == store.DEFAULTS
