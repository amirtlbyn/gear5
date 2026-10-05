"""Notifications (swaync) in the theme's colors: an accent strip per urgency, and
one app's notifications grouped and themed in the notification center (roadmap
4.3, spec NOTIF). The tests pin config/swaync/style.css and config.json."""

import json
import os
import re

from conftest import ROOT

SWAYNC = os.path.join(ROOT, "config", "swaync")


def style():
    with open(os.path.join(SWAYNC, "style.css"), encoding="utf-8") as f:
        return re.sub(r"/\*.*?\*/", "", f.read(), flags=re.DOTALL)


def rule(css, selector):
    """The declarations of the first rule whose selector list holds selector."""
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if selector in [s.strip() for s in selectors.split(",")]:
            return body
    raise AssertionError(f"no rule for {selector}")


def test_every_urgency_has_a_strip_in_a_theme_color():
    """NOTIF-1: given a notification, then its card has a 4 px strip on the left:
    the theme's green for normal, grey for low, red for critical; and no color
    in the file is a fixed value (a theme switch recolors all of them)."""
    css = style()
    for urgency, color in (
        ("normal", "@green"),
        ("low", "@grey"),
        ("critical", "@red"),
    ):
        assert f"box-shadow: inset 4px 0 0 {color};" in rule(
            css, f".notification.{urgency}"
        ), urgency
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)
    assert '@import url("../waybar/colors/current.css");' in css


def test_one_apps_notifications_are_grouped_and_themed():
    """NOTIF-2: given the notification center, then grouping is on, the group has
    no focus background, its header is in fg, its buttons are raised bg1 buttons,
    and its close-all button is red."""
    with open(os.path.join(SWAYNC, "config.json"), encoding="utf-8") as f:
        assert json.load(f)["notification-grouping"] is True
    css = style()
    assert "background: transparent;" in rule(css, ".notification-group:focus")
    assert "color: @fg;" in rule(css, ".notification-group .notification-group-header")
    assert "color: @fg;" in rule(css, ".notification-group .notification-group-icon")
    button = rule(css, ".notification-group .notification-group-buttons button")
    assert (
        "background: @bg1;" in button
        and "border-bottom: 3px solid @edge_deep;" in button
    )
    close = rule(
        css, ".notification-group .notification-group-close-button .close-button"
    )
    assert "background: @red;" in close
