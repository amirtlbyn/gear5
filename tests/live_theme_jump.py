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
    """One sample, or None when a hyprctl read failed. A theme switch is a busy
    moment on Hyprland's socket, and one dropped answer must stop the sampler
    with a failure, not leave a hole the check reads as "nothing moved"."""

    def query(what):
        try:
            out = subprocess.run(["hyprctl", "-j", what], capture_output=True, text=True, timeout=3).stdout
            return json.loads(out or "[]")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None

    screens = query("monitors")
    windows = query("clients")
    if screens is None or windows is None:
        return None
    return (tuple((m["name"], m["x"], m["y"]) for m in screens),
            tuple((c["address"], *c["at"]) for c in windows))


def main():
    start = palette.current()
    other = sys.argv[1] if len(sys.argv) > 1 else next(t for t, _n, _c in palette.available() if t != start)
    seen, dead, stop = [], [], threading.Event()
    sampled_at = [0.0]

    def sample():
        while not stop.is_set():
            p = positions()
            if p is None:
                dead.append(True)
            else:
                seen.append(p)
            sampled_at[0] = time.monotonic()
            time.sleep(0.04)

    sampler = threading.Thread(target=sample)
    sampler.start()
    time.sleep(1)
    for theme in (other, start):
        subprocess.run([os.path.join(SCRIPTS, "theme.py"), "apply", theme], capture_output=True, timeout=30)
        time.sleep(3.5)
    switched_at = time.monotonic()
    stop.set()
    sampler.join()

    print(f"{len(seen)} samples, theme {start} -> {other} -> {palette.current()}")
    if dead or sampled_at[0] < switched_at or len(seen) < 2:
        # the sampling has holes or stopped before the switches ended: "nothing
        # moved" would say nothing, so this run proves nothing
        where = "before the last switch ended" if sampled_at[0] < switched_at else "while it ran"
        print(f"FAIL the sampler stopped {where}: {len(dead)} failed reads, {len(seen)} samples")
        return 1
    moved = [p for p in seen if p != seen[0]]
    if moved:
        print(f"FAIL {len(moved)} samples differ from the first, e.g. {moved[0]}")
        return 1
    print("ok   nothing moved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
