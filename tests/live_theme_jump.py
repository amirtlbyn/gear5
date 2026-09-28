"""
LIVE test (PH0-2): a theme switch must not move any screen or window. It switches
to another theme and back while it samples `hyprctl monitors` and `hyprctl clients`
every 40 ms, then fails when any position changed. Run it on your desktop, not in CI:

    python3 tests/live_theme_jump.py [OTHER_THEME]

Before the fix, the laptop screen moved to the static hyprland.lua position for
about 80 ms and every window moved with it, then both came back.
"""

import json
import os
import subprocess
import sys
import threading
import time

SCRIPTS = os.path.expanduser("~/.config/waybar/scripts")
sys.path.insert(0, SCRIPTS)
import palette  # noqa: E402


def positions():
    def query(what):
        return json.loads(subprocess.run(["hyprctl", "-j", what], capture_output=True, text=True).stdout)

    screens = tuple((m["name"], m["x"], m["y"]) for m in query("monitors"))
    windows = tuple((c["address"], *c["at"]) for c in query("clients"))
    return screens, windows


def main():
    start = palette.current()
    other = sys.argv[1] if len(sys.argv) > 1 else next(t for t, _n, _c in palette.available() if t != start)
    seen, stop = [], threading.Event()

    def sample():
        while not stop.is_set():
            seen.append(positions())
            time.sleep(0.04)

    sampler = threading.Thread(target=sample)
    sampler.start()
    time.sleep(1)
    for theme in (other, start):
        subprocess.run([os.path.join(SCRIPTS, "theme.py"), "apply", theme], capture_output=True, timeout=30)
        time.sleep(3.5)
    stop.set()
    sampler.join()

    moved = [p for p in seen if p != seen[0]]
    print(f"{len(seen)} samples, theme {start} -> {other} -> {palette.current()}")
    if moved:
        print(f"FAIL {len(moved)} samples differ from the first, e.g. {moved[0]}")
        return 1
    print("ok   nothing moved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
