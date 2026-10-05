"""The system power profile (Saver / Balanced / Speed), read and set over the
system bus. The quick settings battery card and Settings' Power & sleep page
share this module, so both always show and change the same thing."""
import re
import subprocess

BUS = ["org.freedesktop.UPower.PowerProfiles", "/org/freedesktop/UPower/PowerProfiles",
       "org.freedesktop.UPower.PowerProfiles", "ActiveProfile"]
PROFILES = [("power-saver", "\U000f032a  Saver"), ("balanced", "\U000f05d1  Balanced"),
            ("performance", "\U000f04c5  Speed")]


def read():
    """The active profile key, or None when power-profiles-daemon is not there."""
    try:
        r = subprocess.run(["busctl", "--system", "get-property", *BUS],
                           capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r'"([^"]+)"', r.stdout)
    return m.group(1) if r.returncode == 0 and m else None


def set_profile(key):
    """Set the active profile. Returns busctl's (code, out, err) triple, so a
    caller that shows errors can, and one that doesn't can ignore it."""
    try:
        r = subprocess.run(["busctl", "--system", "set-property", *BUS, "s", key],
                           capture_output=True, text=True, timeout=5)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)
