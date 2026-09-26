"""
LIVE test of the Settings app: it really switches the theme (to zoro and back to
luffy-gear5), copies and removes a wallpaper for zoro, and turns animations off and
on. Run it on your desktop, not in CI:

    GTK_A11Y=none dbus-run-session -- python3 tests/live_settings.py

Needs ~/Pictures/1325389.png (any image works: change the path below).
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.expanduser("~/.config/waybar/scripts"))
sys.argv = ["settings.py", "theme"]
import palette
import settings
import settings_store as store
from gi.repository import GLib

app = settings.Settings()
steps = []


def check(msg, cond):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)


def s1():
    app.win.set_visible(False)
    app.pick_theme("zoro")
    return False


def s2():
    check("theme switched to zoro", palette.current() == "zoro")
    check(
        "settings window recolored",
        "#86c97f" in open(os.path.expanduser("~/.config/waybar/colors/current.css")).read(),
    )
    # wallpaper: give zoro a copy of an image, then remove it
    app.set_wallpaper("zoro", os.path.expanduser("~/Pictures/1325389.png"))
    return False


def s3():
    check("zoro wallpaper copied", palette.wallpaper("zoro") is not None)
    out = subprocess.run(["pgrep", "-a", "swaybg"], capture_output=True, text=True).stdout
    check("swaybg shows zoro wallpaper", "zoro.png" in out)
    app.set_wallpaper("zoro", None)
    return False


def s4():
    check("zoro wallpaper removed", palette.wallpaper("zoro") is None)
    app.save(animations=False)
    check("animations off saved", store.load()["animations"] is False)
    return False


def s5():
    out = subprocess.run(
        ["hyprctl", "-j", "getoption", "animations:enabled"], capture_output=True, text=True
    ).stdout
    check("Hyprland animations now off: " + out.strip(), '"bool": false' in out)
    app.save(kb_layout="us,xx")
    check("bad layout shows an error: " + app.error.get_label(), app.error.get_visible())
    app.save(animations=True)
    app.pick_theme("luffy-gear5")
    return False


def s6():
    out = subprocess.run(
        ["hyprctl", "-j", "getoption", "animations:enabled"], capture_output=True, text=True
    ).stdout
    check("animations back on", '"bool": true' in out)
    check("theme back to luffy-gear5", palette.current() == "luffy-gear5")
    app.quit()
    return False


t = 1500
for f, delay in ((s1, 1500), (s2, 7000), (s3, 6000), (s4, 6000), (s5, 5000), (s6, 7000)):
    GLib.timeout_add(t, f)
    t += delay
app.run(sys.argv)
