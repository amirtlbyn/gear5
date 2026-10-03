#!/usr/bin/env python3
"""The bar config Waybar really runs: bar/config, plus a compact bar (workspaces
only) on every vertical screen, found by asking Hyprland which screens are rotated.

  bar_config.py            write $XDG_RUNTIME_DIR/waybar-config.json, print its path
  bar_config.py --refresh  same, and restart the bar if the set of vertical screens
                           changed (called after a screen is rotated)
"""
import copy
import json
import os
import re
import subprocess
import sys

SRC = os.path.expanduser("~/.config/waybar/bar/config")
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "gear5")
RUN = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
OUT = os.path.join(RUN, "waybar-config.json")


def vertical_outputs():
    """Names of the screens turned 90 or 270 degrees (transform 1, 3, 5, 7)."""
    try:
        out = subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True, text=True, timeout=3).stdout
        return sorted(m["name"] for m in json.loads(out) if (m.get("transform") or 0) % 2)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return []


def build():
    with open(SRC) as f:
        text = re.sub(r"^\s*//.*$", "", f.read(), flags=re.M)
    bars = json.loads(text)
    for bar in bars:  # Waybar's image module does not expand "~": the GIF player's picture link (gif_player.py)
        bar["image#character"] = {"path": os.path.join(CACHE, "bar.png")}
    vertical = vertical_outputs()
    if not vertical:
        return bars
    normal = bars[0]
    normal["output"] = ["!" + n for n in vertical] + ["*"]   # Waybar reads the exclusions first
    compact = copy.deepcopy(normal)
    compact["output"] = vertical
    compact.update({"width": 400, "margin-left": 0, "margin-right": 0,
                    "modules-left": [], "modules-right": [], "modules-center": ["group/desks"]})
    return bars + [compact]


def write():
    text = json.dumps(build(), indent=2)
    try:
        with open(OUT) as f:
            changed = f.read() != text
    except OSError:
        changed = True
    if changed:
        with open(OUT, "w") as f:
            f.write(text)
    return changed


if __name__ == "__main__":
    changed = write()
    if "--refresh" in sys.argv:
        if changed:
            subprocess.Popen([os.path.expanduser("~/.config/hypr/scripts/bar.sh")],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        print(OUT)
