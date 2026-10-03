"""The bar shows state, and numbers only when they matter (roadmap 2.1): Wi-Fi,
volume and battery are icon-only in the normal state, the number is on hover,
and the battery number stays when the level is below 30 % or the battery is charging. The tests pin the
Waybar configuration text, the repo's pattern for config contracts."""

import os
import re

from conftest import ROOT

MODULES = os.path.join(ROOT, "config", "waybar", "bar", "modules.jsonc")


def block(name):
    text = open(MODULES, encoding="utf-8").read()
    part = text.split(f'"{name}": {{', 1)[1]
    depth, out = 1, []
    for line in part.splitlines(keepends=True):
        depth += line.count("{") - line.count("}")
        if depth == 0:
            break
        out.append(line)
    return "".join(out)


def value_of(block_text, key):
    m = re.search(rf'"{key}": "([^"]*)"', block_text)
    return m.group(1) if m else None


def test_wifi_is_an_icon_with_the_number_on_hover():
    """BAR-1: given the network module, while Wi-Fi is connected, then the format
    shows no signal percentage, and the hover tooltip keeps the network name and
    the signal percentage."""
    net = block("network")
    assert value_of(net, "format-wifi") is not None
    assert "{signalStrength}%" not in (value_of(net, "format-wifi") or "")
    assert "{signalStrength}%" not in (value_of(net, "format-ethernet") or "")
    tooltip = value_of(net, "tooltip-format-wifi") or ""
    assert "{essid}" in tooltip and "{signalStrength}%" in tooltip


def test_volume_is_an_icon_muted_stays_a_word():
    """BAR-2: given the pulseaudio module, while sound plays, then the format
    shows no volume percentage, while muted keeps the word muted, and the hover
    tooltip shows the volume percentage."""
    pa = block("pulseaudio")
    assert value_of(pa, "format") == "{icon}"
    assert "{volume}%" not in (value_of(pa, "format-bluetooth") or "")
    assert "muted" in (value_of(pa, "format-muted") or "")
    assert "muted" in (value_of(pa, "format-bluetooth-muted") or "")
    assert "{volume}%" in (value_of(pa, "tooltip-format") or "")


def test_battery_number_only_when_it_matters():
    """BAR-3: given the battery module, while the battery is at 30 % or above and
    not charging, then the normal, plugged and full formats show no percentage,
    the warning, critical and charging formats keep it, and the hover tooltip
    shows it."""
    bat = block("battery")
    for key in ("format", "format-plugged", "format-full"):
        assert value_of(bat, key) is not None, key
        assert "{capacity}%" not in (value_of(bat, key) or ""), key
    for key in ("format-warning", "format-critical", "format-charging"):
        assert "{capacity}%" in (value_of(bat, key) or ""), key
    assert "{capacity}%" in (value_of(bat, "tooltip-format") or "")
