"""The bar shows the time only (roadmap 2.2): no zone tag on any zone, the dates
(Gregorian and Jalali) on hover and in the calendar popup, no date pill, and
every pill's content in the vertical middle of its pill."""

import os
import re

from conftest import ROOT

BAR = os.path.join(ROOT, "config", "waybar", "bar")


def read(path):
    return open(path, encoding="utf-8").read()


def test_the_clock_shows_the_time_alone():
    """CLK-1: given the bar clock, whichever zone is active, then the text it
    emits is the time with no zone tag and no date — the tag-adding line and
    its helper are gone from clock.sh."""
    sh = read(os.path.join(ROOT, "config", "waybar", "scripts", "clock.sh"))
    emit = sh.split("emit()", 1)[1]
    assert re.search(r'text="[^"]*\(TZ=\$zone date \+%H:%M\)"', emit)
    assert "short " not in emit and "$(short" not in sh


def test_the_clock_tooltip_carries_both_dates_above_the_zones():
    """CLK-2: given the bar clock, when it is hovered, then the tooltip starts
    with dates.py's full Gregorian and Jalali dates and lists the pinned zones
    below them."""
    emit = read(os.path.join(ROOT, "config", "waybar", "scripts", "clock.sh")).split("emit()", 1)[1]
    assert 'dates.py" | jq -r .tooltip' in emit
    zones_at = emit.find("while read -r z")
    dates_at = emit.find("dates.py")
    assert 0 < dates_at < zones_at


def test_no_date_pill_and_one_popup_opens_from_the_clock():
    """CLK-3/CWPM-3: given the bar's module lists, then no date module is
    placed, and given the clock module, when it is clicked with either
    button, then the same merged clock popup (calendar + timezones) opens."""
    config = read(os.path.join(BAR, "config"))
    for side in ("modules-left", "modules-center", "modules-right"):
        placed = re.search(rf'"{side}": \[([^\]]*)\]', config).group(1)
        assert "dates" not in placed and "persian-date" not in placed, side
    modules = read(os.path.join(BAR, "modules.jsonc"))
    clock = modules.split('"custom/clock": {', 1)[1].split("},", 1)[0]
    assert clock.count("popup.sh worldclock") == 2
    assert "calendar-popup" not in clock


def test_pill_content_sits_in_the_vertical_middle():
    """CLK-4: given the shared pill rule and the network pill, when the bar
    renders, then the pill row keeps its original 7/12 margins (the developer
    chose them back)."""
    css = read(os.path.join(BAR, "style.css"))
    rule = css.split("#custom-launcher,", 1)[1].split("}", 1)[0]
    assert "margin-top: 7px" in rule and "margin-bottom: 12px" in rule


def test_wifi_pill_padding_centers_the_glyph():
    """CPFU-1: given the network pill, when the bar renders, then it sets its
    own unequal left and right padding (the glyph's ink sits off-center in its
    cell, so equal padding measurably left it off-center)."""
    css = read(os.path.join(BAR, "style.css"))
    rule = css.split("#network {", 1)[1].split("}", 1)[0]
    left = int(re.search(r"padding-left:\s*(\d+)px", rule).group(1))
    right = int(re.search(r"padding-right:\s*(\d+)px", rule).group(1))
    assert left != right
