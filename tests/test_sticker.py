"""The pop-up sticker's start at a theme switch (roadmap 6.2). See
config/waybar/scripts/theme.py (start_sticker, main). The pop-up itself is checked by
tests/smoke_sticker.sh."""

import subprocess

import pytest
import settings_store as store
import theme


@pytest.fixture
def apply_zoro(monkeypatch):
    """theme.py apply zoro with the file writing and the reload stubbed out; the
    fixture returns a function that runs it with the given sticker_switch."""
    monkeypatch.setattr(theme, "write_all", lambda theme_id: None)
    monkeypatch.setattr(theme, "reload", lambda: None)

    def run(switch):
        monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS, sticker_switch=switch))
        return theme.main(["theme.py", "apply", "zoro"])

    return run


def test_apply_starts_the_sticker_detached_only_while_its_switch_is_on(apply_zoro, monkeypatch):
    """CHAR-6: given a theme switch, when the sticker switch is on then one detached
    sticker starts for the new theme, and when it is off none starts; and when the
    start fails, the switch still succeeds."""
    starts = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: starts.append((argv, kw)))

    assert apply_zoro(True) == 0
    assert len(starts) == 1
    assert starts[0][0][-1] == "zoro"
    assert starts[0][0][0].endswith("sticker.py")
    assert starts[0][1]["start_new_session"] is True

    starts.clear()
    assert apply_zoro(False) == 0
    assert starts == []

    def cannot_start(argv, **kw):
        raise OSError("no such file")

    monkeypatch.setattr(subprocess, "Popen", cannot_start)
    assert apply_zoro(True) == 0
