"""
LIVE test of the Quickshell lock (spec QSL, live criteria). It LOCKS YOUR REAL SESSION, so
it refuses to run unless you ask for it and are present, and it skips when `qs` is missing:

    GEAR5_LIVE_LOCK=1 python3 tests/live_lock.py

It locks once and runs the tests in order on that one lock. The last test waits up to 2
minutes for YOU to type the right password, which ends the lock. Nothing here ever kills
the lock for good: the kill test kills `qs` once and lock.sh puts a new one up, and if a
test fails the session stays locked under a running lock, so type your password.
Needs: qs, grim, hyprctl; wtype for the wrong-password test; Pillow for the screen and
GIF tests.
"""

import os
import shutil
import subprocess
import tempfile
import time
import unittest

LOCK_SH = os.path.expanduser("~/.config/hypr/scripts/lock.sh")
LOG = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "lock.log")


def qs_pids():
    """The PIDs of the running qs processes."""
    out = subprocess.run(["pgrep", "-x", "qs"], capture_output=True, text=True, check=False).stdout
    return [int(p) for p in out.split()]


def wait_for(condition, seconds):
    """True once condition() is, within the seconds."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return False


def shot(path, output=None):
    """A grim screenshot of one output, or of every output, in this file."""
    cmd = ["grim"] + (["-o", output] if output else []) + [path]
    subprocess.run(cmd, check=True, timeout=10)


@unittest.skipUnless(os.environ.get("GEAR5_LIVE_LOCK") == "1", "locks the real session: set GEAR5_LIVE_LOCK=1")
@unittest.skipUnless(shutil.which("qs"), "quickshell (qs) is not installed")
class LiveLock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert qs_pids() == [], "a lock is already running"
        cls.locker = subprocess.Popen([LOCK_SH])
        assert wait_for(qs_pids, 5), "no qs started"
        time.sleep(1)  # the lock surfaces are up

    def test_1_qsl_4_a_wrong_password_stays_locked_and_counts(self):
        """QSL-4: given a lock, when a wrong password is typed, then qs still runs and
        lock.log has "Wrong password (1)"."""
        if not shutil.which("wtype"):
            self.skipTest("wtype is not installed")
        subprocess.run(["wtype", "definitely-not-my-password\n"], check=True, timeout=10)
        self.assertTrue(wait_for(lambda: "Wrong password (1)" in open(LOG).read(), 10))
        self.assertTrue(qs_pids())
        self.assertIsNone(self.locker.poll())

    def test_5_qsl_5_the_right_password_unlocks_with_status_0(self):
        """QSL-5: given a lock, when YOU type the right password within 2 minutes, then
        lock.sh exits 0 and qs is gone."""
        print("\ntype your password now (2 minutes)", flush=True)
        self.assertEqual(self.locker.wait(timeout=120), 0)
        self.assertEqual(qs_pids(), [])

    def test_4_qsl_7_a_killed_lock_is_replaced_and_the_session_stays_locked(self):
        """QSL-7: given a lock, when qs is killed (SIGKILL), then within 3 s a new qs
        runs (lock.sh restarts it once). Eye check: the screen shows the lock, not the
        "lockscreen app died" page."""
        old = qs_pids()
        subprocess.run(["kill", "-9", *map(str, old)], check=True)
        self.assertTrue(wait_for(lambda: qs_pids() and qs_pids() != old, 3))
        self.assertIsNone(self.locker.poll())  # lock.sh restarted it, and still runs

    def test_3_qsl_8_a_screen_added_while_locked_gets_a_lock_surface(self):
        """QSL-8: given a lock, when a headless output is created, then within 2 s its
        screenshot is not one flat color (the lock is drawn there), with the same qs."""
        from PIL import Image

        pids = qs_pids()
        subprocess.run(["hyprctl", "output", "create", "headless"], check=True)
        name = None
        try:
            time.sleep(2)
            monitors = subprocess.run(["hyprctl", "monitors"], capture_output=True, text=True, check=True).stdout
            name = next(w for line in monitors.splitlines() for w in line.split() if w.startswith("HEADLESS-"))
            with tempfile.TemporaryDirectory() as tmp:
                shot(f"{tmp}/new.png", name)
                colors = Image.open(f"{tmp}/new.png").convert("RGB").getcolors(maxcolors=2**24)
            self.assertGreater(len(colors), 1)
            self.assertEqual(qs_pids(), pids)
        finally:
            if name:
                subprocess.run(["hyprctl", "output", "remove", name], check=False)

    def test_2_qsl_9_the_gif_animates(self):
        """QSL-9: given a theme with a GIF, when two screenshots are taken 300 ms apart,
        then they differ (the clock is the same, so the difference is the GIF box)."""
        from PIL import Image, ImageChops

        with tempfile.TemporaryDirectory() as tmp:
            shot(f"{tmp}/a.png")
            time.sleep(0.3)
            shot(f"{tmp}/b.png")
            a, b = Image.open(f"{tmp}/a.png").convert("RGB"), Image.open(f"{tmp}/b.png").convert("RGB")
            self.assertIsNotNone(ImageChops.difference(a, b).getbbox(), "no change: no GIF, or it is still")


if __name__ == "__main__":
    unittest.main()
