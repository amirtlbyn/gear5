#!/usr/bin/env python3
"""
Plays the theme's GIF on the bar as a flip-book (spec GIF). theme_gif.py cuts the GIF
into frame pictures; this service moves the link the bar's pill reads, then signals
Waybar to read it again. Waybar and hyprlock play no GIF themselves.

  gif_player.py --bar       run for the bar (the bar-gif user service)
  gif_player.py --lock PID  run beside the hyprlock process PID (started by lock.sh)

The pill reads ~/.cache/gear5/bar.png. A link to a file that does not exist hides
the pill (Waybar 0.15.0 hides an image it cannot load; empty output would keep the
old picture). SIGUSR1 makes the player read the frames and the settings again (new frames: a
theme switch or a GIF change). In "ac" mode a resting pill looks at the charger
every 5 s; in "switch" mode the GIF plays for 5 s after that signal.
While the pill rests on one picture no timer runs (INV-2): the player sleeps until
a signal comes.
"""
import json
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import theme_gif  # noqa: E402
import settings_store as store  # noqa: E402

WAYBAR_SIGNAL = 11  # image#character's "signal" in modules.jsonc
HIDDEN_PATH = "/nonexistent/gear5-no-gif.png"  # a picture Waybar cannot load hides the pill
LOCK_SIGNAL = signal.SIGUSR2  # the only signal the lock player sends: SIGUSR1 unlocks hyprlock (INV-1)
POWER_ROOT = "/sys/class/power_supply"
POWER_POLL_S = 5  # "ac" mode: how often a resting pill looks at the charger (GIF-3)
SWITCH_PLAY_S = 5  # "switch" mode: how long the GIF plays after a theme switch (GIF-3)


def is_waybar(pid):
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip() == "waybar"
    except OSError:
        return False


def waybar_pids():
    """The PIDs of the running Waybar processes."""
    pids = []
    for entry in os.listdir("/proc"):
        try:
            with open(f"/proc/{entry}/comm") as f:
                if f.read().strip() == "waybar":
                    pids.append(int(entry))
        except (OSError, ValueError):
            continue
    return pids


def on_mains(root=POWER_ROOT):
    """True when a mains supply is online. A machine with no mains supply (a
    desktop) counts as on AC."""
    try:
        names = os.listdir(root)
    except OSError:
        return True  # no power folder: nothing to wait for
    found = False
    for name in names:
        try:
            with open(os.path.join(root, name, "type")) as f:
                if f.read().strip() != "Mains":
                    continue
        except OSError:
            continue
        found = True
        try:
            with open(os.path.join(root, name, "online")) as f:
                if f.read().strip() == "1":
                    return True
        except OSError:
            return True  # a Mains supply we cannot read counts as on AC
    return not found


class BarPlayer:
    """The bar's flip-book. `load()` reads the frames and the settings; `step()`
    shows the next frame; `wait()` says how many seconds until the next `step()`,
    or None to wait for a signal. The "Bar GIF plays" choice decides `playing()`."""

    def __init__(self, cache=None, tell_bar=None, power_root=POWER_ROOT, clock=time.monotonic):
        self.power_root = power_root
        self.clock = clock
        self.mode = "ac"
        self.on_ac = True
        self.play_until = 0
        self.cache = cache or theme_gif.CACHE
        self.link = os.path.join(self.cache, "bar.png")
        self.tell_bar = tell_bar or self.signal_waybar
        self.ms = []
        self.index = 0
        self.pids = []

    def signal_waybar(self):
        """Tell each Waybar a new frame is ready. A cached PID is used only while
        its process is still named waybar: after a restart the PID may belong to
        another program, and SIGRTMIN+11 would end it."""
        if not self.pids or not all(is_waybar(pid) for pid in self.pids):
            self.pids = waybar_pids()
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGRTMIN + WAYBAR_SIGNAL)
            except (ProcessLookupError, PermissionError):
                self.pids = []  # gone or not ours: look again at the next frame

    def show(self, target):
        """Point the pill's link at target (a frame, or HIDDEN_PATH), then tell Waybar."""
        os.makedirs(self.cache, exist_ok=True)
        if os.path.lexists(self.link + ".tmp"):
            os.remove(self.link + ".tmp")
        os.symlink(target, self.link + ".tmp")
        os.replace(self.link + ".tmp", self.link)
        self.tell_bar()

    def load(self, switched=False):
        """Read the frames and the settings, and rest on the first frame; the pill is
        hidden when the switch is off or the theme has no readable GIF (GIF-1).
        `switched` is true when new frames just came (a theme switch or a GIF
        change): the "switch" choice then plays for SWITCH_PLAY_S seconds."""
        self.ms, self.index = [], 0
        settings = store.load()
        self.mode = settings["bar_gif"]
        self.play_until = self.clock() + SWITCH_PLAY_S if switched else 0
        self.on_ac = on_mains(self.power_root)
        if settings["gif_bar"]:
            try:
                with open(os.path.join(theme_gif.gif_dir(), "current", "frames.json")) as f:
                    self.ms = [int(ms) for ms in json.load(f)["ms"]]
            except (OSError, ValueError, KeyError, TypeError):
                self.ms = []
        self.show(self.frame_path(0) if self.ms else HIDDEN_PATH)

    def frame_path(self, index):
        """Frame index of the current set, relative to the link's folder."""
        return os.path.join("gif", "current", "bar", f"{index:03d}.png")

    def playing(self):
        if len(self.ms) < 2:
            return False
        if self.mode == "always":
            return True
        if self.mode == "ac":
            return self.on_ac
        return self.clock() < self.play_until

    def step(self):
        """Show the next frame while playing, or rest on the first one; returns
        `wait()`."""
        if self.mode == "ac":
            self.on_ac = on_mains(self.power_root)
        if self.playing():
            self.index = (self.index + 1) % len(self.ms)
            self.show(self.frame_path(self.index))
        elif self.index:
            self.index = 0
            self.show(self.frame_path(0))
        return self.wait()

    def wait(self):
        """Seconds until the next `step()`. None: no timer, wait for a signal (INV-2);
        a resting pill in "ac" mode looks at the charger every POWER_POLL_S."""
        if len(self.ms) < 2:
            return None
        if self.playing():
            seconds = self.ms[self.index] / 1000
            return min(seconds, max(0, self.play_until - self.clock())) if self.mode == "switch" else seconds
        return POWER_POLL_S if self.mode == "ac" else None


def is_hyprlock(pid, proc="/proc"):
    try:
        with open(f"{proc}/{pid}/comm") as f:
            return f.read().strip() == "hyprlock"
    except OSError:
        return False


def catches_lock_signal(pid, proc="/proc"):
    """True once the process has its own handler for LOCK_SIGNAL (the SigCgt mask in
    /proc/<pid>/status). hyprlock 0.9.6 installs it only after it has locked the
    session; before that, SIGUSR2 has its default action and would end hyprlock
    unlocked. So nothing is sent until this is true."""
    try:
        with open(f"{proc}/{pid}/status") as f:
            for line in f:
                if line.startswith("SigCgt:"):
                    return bool(int(line.split()[1], 16) & (1 << (LOCK_SIGNAL - 1)))
    except (OSError, ValueError, IndexError):
        pass
    return False


class LockPlayer:
    """The lock screen's flip-book (GIF-5). hyprlock reads lock.png again when it gets
    SIGUSR2 (its image has reload_time = 0). The player sends LOCK_SIGNAL to the one
    PID it was given, only while /proc/<pid>/comm reads hyprlock, and stops as soon as
    that stops being true: a later process that reuses the PID is never signaled."""

    def __init__(self, pid, cache=None, kill=os.kill, proc="/proc"):
        self.pid = pid
        self.kill = kill
        self.proc = proc
        self.cache = cache or theme_gif.CACHE
        self.link = os.path.join(self.cache, "lock.png")
        self.index = 0
        self.ms = []

    def load(self):
        try:
            with open(os.path.join(theme_gif.gif_dir(), "current", "frames.json")) as f:
                self.ms = [int(ms) for ms in json.load(f)["ms"]]
        except (OSError, ValueError, KeyError, TypeError):
            self.ms = []

    def show(self, index):
        target = os.path.join("gif", "current", "lock", f"{index:03d}.png")
        os.makedirs(self.cache, exist_ok=True)
        if os.path.lexists(self.link + ".tmp"):
            os.remove(self.link + ".tmp")
        os.symlink(target, self.link + ".tmp")
        os.replace(self.link + ".tmp", self.link)

    def step(self):
        """Move to the next frame and tell hyprlock. False when hyprlock is gone (or
        is not hyprlock): the caller stops."""
        if not is_hyprlock(self.pid, self.proc):
            return False
        if not catches_lock_signal(self.pid, self.proc):
            return True  # hyprlock is still starting: wait, and send nothing
        self.index = (self.index + 1) % len(self.ms)
        self.show(self.index)
        try:
            self.kill(self.pid, LOCK_SIGNAL)
        except OSError:
            return False
        return True

    def run(self, sleep=time.sleep):
        """Play until hyprlock ends. A GIF of fewer than two frames has nothing to flip."""
        self.load()
        if len(self.ms) < 2:
            return
        self.show(0)
        while True:
            sleep(self.ms[self.index] / 1000)
            if not self.step():
                return


def serve_bar():
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR1})
    player = BarPlayer()
    player.load()
    while True:
        wait = player.wait()
        caught = signal.sigwaitinfo({signal.SIGUSR1}) if wait is None else signal.sigtimedwait({signal.SIGUSR1}, wait)
        if caught:
            player.load(switched=True)
        else:
            player.step()


def main(argv):
    if len(argv) > 1 and argv[1] == "--bar":
        serve_bar()
        return 0
    if len(argv) > 2 and argv[1] == "--lock" and argv[2].isdigit():
        LockPlayer(int(argv[2])).run()
        return 0
    print((__doc__ or "").strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
