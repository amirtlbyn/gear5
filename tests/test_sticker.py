"""The GIF pop-up's start at a theme switch (roadmap 6.2, spec GIFT). See
config/waybar/scripts/theme.py (start_sticker, main). The pop-up itself is checked by
tests/smoke_sticker.sh."""

import subprocess

import pytest
import settings_store as store
import theme


@pytest.fixture
def apply_zoro(monkeypatch):
    """theme.py apply zoro with the file writing and the reload stubbed out; the
    fixture returns a function that runs it with the given gif_switch and with or
    without a GIF for the theme."""
    monkeypatch.setattr(theme, "write_all", lambda theme_id: None)
    monkeypatch.setattr(theme, "reload", lambda: None)

    def run(switch, has_gif=True):
        monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS, gif_switch=switch))
        monkeypatch.setattr(theme.theme_gif, "gif", lambda theme_id, themes: "zoro.gif" if has_gif else None)
        return theme.main(["theme.py", "apply", "zoro"])

    return run


def test_apply_starts_the_popup_detached_only_with_its_switch_on_and_a_gif(apply_zoro, monkeypatch):
    """GIFT-8: given a theme switch, when the GIF switch is on and the theme has a GIF
    then one detached pop-up starts for the new theme; when the switch is off, or the
    theme has no GIF, then none starts; and when the start fails, the switch still
    succeeds."""
    starts = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: starts.append((argv, kw)))

    assert apply_zoro(True) == 0
    assert len(starts) == 1
    assert starts[0][0][-1] == "zoro"
    assert starts[0][0][0].endswith("sticker.py")
    assert starts[0][1]["start_new_session"] is True

    starts.clear()
    assert apply_zoro(False) == 0
    assert apply_zoro(True, has_gif=False) == 0
    assert starts == []

    def cannot_start(argv, **kw):
        raise OSError("no such file")

    monkeypatch.setattr(subprocess, "Popen", cannot_start)
    assert apply_zoro(True) == 0
