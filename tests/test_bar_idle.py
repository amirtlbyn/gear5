"""The away-timer pill is a small glyph on the left side of the bar (roadmap 2.3):
it stays in every mode, so one click changes the mode, but it shows only the mode
glyph, and the minutes are on hover. The tests run the real `idle.sh status`
against a state file in a temporary home."""

import json
import os
import re
import subprocess

import pytest
from conftest import ROOT

IDLE = os.path.join(ROOT, "config", "hypr", "scripts", "idle.sh")
BAR = os.path.join(ROOT, "config", "waybar", "bar")
GLYPHS = {"sleep": "󰒲", "lock": "󰌾", "awake": "󰅶"}


def status(tmp_path, mode, minutes=5):
    state = tmp_path / ".config" / "hypr" / "idle-state"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(f"{mode} {minutes}\n")
    out = subprocess.run(
        ["bash", IDLE, "status"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
        env={**os.environ, "HOME": str(tmp_path)},
    ).stdout
    lines = out.splitlines()
    assert len(lines) == 1, out
    return json.loads(lines[0])


@pytest.mark.parametrize("mode", ["sleep", "lock", "awake"])
def test_the_pill_is_the_mode_glyph_only(tmp_path, mode):
    """AWAKE-1: given the mode is sleep, lock or awake, when the bar asks for the
    status, then the text is only that mode's glyph (no minutes, no word), and
    the class is the mode name."""
    out = status(tmp_path, mode, 90)
    assert out["text"] == GLYPHS[mode]
    assert out["class"] == mode


@pytest.mark.parametrize(
    "mode, minutes, shown", [("sleep", 5, "5m"), ("lock", 90, "1h"), ("awake", 5, None)]
)
def test_the_minutes_are_on_hover_and_the_output_is_json(
    tmp_path, mode, minutes, shown
):
    """AWAKE-2: given the sleep or lock mode, when the bar asks for the status,
    then the tooltip names the minutes. In every mode, the output is one valid
    JSON object."""
    out = status(tmp_path, mode, minutes)
    assert out["tooltip"]
    if shown:
        assert shown in out["tooltip"]


def test_the_pill_is_on_the_left_after_the_clock():
    """AWAKE-3: given the bar config, when the bar is built, then custom/idle is
    in modules-left after the clock, and not in modules-right."""
    with open(os.path.join(BAR, "config"), encoding="utf-8") as f:
        config = f.read()
    left = json.loads(
        "[" + re.search(r'"modules-left": \[([^\]]*)\]', config).group(1) + "]"
    )
    right = re.search(r'"modules-right": \[([^\]]*)\]', config).group(1)
    assert "custom/idle" in left
    assert left.index("custom/idle") > left.index("custom/clock")
    assert "custom/idle" not in right


def test_glyph_pills_are_as_wide_as_the_network_pill():
    """AWAKE-4 (changed by the developer on 2026-09-29: the same size as the
    network pill, not narrower): given the bar style, when the glyph-only pills
    render, then the volume, battery and away-timer pills (in every mode) have
    the same total side padding as the network pill, so all are the same width."""
    with open(os.path.join(BAR, "style.css"), encoding="utf-8") as f:
        css = f.read()

    def side_padding(selector):
        rule = re.search(
            rf"^{re.escape(selector)}\s*\{{([^}}]*)\}}", css, re.MULTILINE
        ).group(1)
        return sum(
            int(re.search(rf"padding-{side}: (\d+)px", rule).group(1))
            for side in ("left", "right")
        )

    network = side_padding("#network")
    for selector in ("#pulseaudio", "#battery", "#custom-idle", "#custom-idle.lock"):
        assert side_padding(selector) == network, selector
