#!/usr/bin/env python3
"""
The night light (Settings > Displays): warmer screen colors at night, through
wlsunset. The night-light user service runs it; Settings restarts the service
when a night light setting changes, and stopping wlsunset gives the screens
their normal colors back (spec NIGHT).

  night_light.py --serve      run wlsunset for the saved settings, or wait while Off
"""
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import settings_store as store  # noqa: E402
import weather_lib  # noqa: E402


def local_zone():
    """The system timezone, e.g. "Asia/Tehran" (as worldclock.local_zone reads it)."""
    try:
        return os.path.realpath("/etc/localtime").split("/zoneinfo/", 1)[1]
    except IndexError:
        return "UTC"


def home_place():
    """(lat, lon) of the calendar's home city (the one picked, else the system
    timezone's city), or None when no place is known, e.g. UTC."""
    return weather_lib.place(weather_lib.get_home(local_zone())["key"])


def command(s, place):
    """The wlsunset command for these settings, or None while Off. Sunset mode
    with no known place uses the schedule's times (NIGHT-1..3)."""
    if s["night_mode"] == "off":
        return None
    argv = ["wlsunset", "-t", str(s["night_temp"])]
    if s["night_mode"] == "sunset" and place is not None:
        lat, lon = place
        return argv + ["-l", str(lat), "-L", str(lon)]
    return argv + ["-s", s["night_start"], "-S", s["night_end"]]


def main(argv):
    if len(argv) > 1 and argv[1] == "--serve":
        wlsunset = command(store.load(), home_place())
        if wlsunset is None:
            signal.pause()  # Off: the service stays up, so Settings can restart it into a mode
            return 0
        os.execvp(wlsunset[0], wlsunset)
    print((__doc__ or "").strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
