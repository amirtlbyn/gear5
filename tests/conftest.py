import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "config", "waybar", "scripts")
THEMES = os.path.join(ROOT, "config", "hypr", "themes")
sys.path.insert(0, SCRIPTS)


@pytest.fixture(autouse=True)
def bar_signals(tmp_path_factory, monkeypatch):
    """theme.write_all and Settings make the bar's GIF frames and nudge the bar player.
    Keep every test away from the real cache folder and the real service: the
    frames go to a temporary folder, and the nudges land in the returned list."""
    import theme_gif

    sent = []
    monkeypatch.setattr(theme_gif, "CACHE", str(tmp_path_factory.mktemp("cache")))
    monkeypatch.setattr(theme_gif, "nudge_player", lambda: sent.append("USR1"))
    return sent
