"""The lock screen: the theme's GIF, battery and media status (roadmap 4.2, specs
LOCK and GIFT). See config/hypr/hyprlock.conf, config/hypr/scripts/lockinfo.sh and
theme.py (lock_picture, write_lock)."""

import os
import re
import shutil
import subprocess
import time

import palette
import theme
from conftest import ROOT, THEMES

HYPRLOCK = os.path.join(ROOT, "config", "hypr", "hyprlock.conf")
LOCKINFO = os.path.join(ROOT, "config", "hypr", "scripts", "lockinfo.sh")


def test_a_theme_with_no_gif_has_no_lock_picture_not_even_face(tmp_path, monkeypatch):
    """GIFT-3: given an old lock picture in characters/ and a ~/.face, when the theme
    in use has no GIF frames, then the lock picture is empty and the lock file's
    $character is empty."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / ".face").write_bytes(b"x")
    chars = tmp_path / "hypr" / "characters"
    chars.mkdir(parents=True)
    (chars / "zoro.webp").write_bytes(b"x")
    monkeypatch.setattr(theme.theme_gif, "CACHE", str(tmp_path / "cache"))

    assert theme.lock_picture() == ""
    assert "$character = \n" in theme.hyprlock_conf(palette.theme("zoro", THEMES), None, theme.lock_picture())


def test_a_theme_with_gif_frames_shows_the_flip_book_on_the_lock_screen(tmp_path, monkeypatch):
    """GIFT-4: given a theme whose GIF has frames, when the lock picture is asked
    for, then it is the flip-book link, and it is empty again when the frames are
    gone."""
    current = tmp_path / "cache" / "gif" / "current"
    current.mkdir(parents=True)
    monkeypatch.setattr(theme.theme_gif, "CACHE", str(tmp_path / "cache"))

    (current / "frames.json").write_text('{"ms": [100, 100]}')
    assert theme.lock_picture() == str(tmp_path / "cache" / "lock.png")
    (current / "frames.json").unlink()
    assert theme.lock_picture() == ""


def run_lockinfo(tmp_path, battery=None, player=None):
    """lockinfo.sh with a fake battery folder and a fake playerctl."""
    power = tmp_path / "power"
    power.mkdir(exist_ok=True)
    if battery:
        bat = power / "BAT0"
        bat.mkdir(exist_ok=True)
        (bat / "capacity").write_text(f"{battery[0]}\n")
        (bat / "status").write_text(f"{battery[1]}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "playerctl"
    status, meta = player or ("No players found", "")
    fake.write_text(
        "#!/bin/bash\n"
        f'[[ "$1" == status ]] && {{ echo {status!r}; exit 0; }}\n'
        f"printf '%b\\n' {meta!r}\n"
    )
    fake.chmod(0o755)
    env = dict(
        os.environ, LOCKINFO_POWER=str(power), PATH=f"{bin_dir}:{os.environ['PATH']}"
    )
    out = subprocess.run(
        ["bash", LOCKINFO],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        check=False,
    )
    assert out.returncode == 0
    assert out.stdout.count("\n") == 1
    return out.stdout.rstrip("\n")


def test_the_battery_part(tmp_path):
    """LOCK-2: given a battery at 72 % discharging, then the icon for 70 % and
    "72%"; while charging, the charging icon; with no battery, no battery part."""
    assert run_lockinfo(tmp_path, battery=(72, "Discharging")) == "󰂀 72%"
    assert run_lockinfo(tmp_path, battery=(100, "Full")) == "󰁹 100%"
    assert run_lockinfo(tmp_path, battery=(40, "Charging")) == "󰂄 40%"
    shutil.rmtree(tmp_path / "power")
    assert run_lockinfo(tmp_path) == ""


def test_the_media_part(tmp_path):
    """LOCK-3: given a player that plays, then "♪ artist — title", with &, < and >
    made safe for Pango; the title alone when there is no artist; nothing when no
    player plays; and after the battery part when both are there."""
    assert (
        run_lockinfo(tmp_path, player=("Playing", "Tom & Jerry\t<Theme>"))
        == "♪ Tom &amp; Jerry — &lt;Theme&gt;"
    )
    assert (
        run_lockinfo(tmp_path, player=("Paused", "\tJust a title")) == "♪ Just a title"
    )
    assert run_lockinfo(tmp_path, player=("Stopped", "Old\tSong")) == ""
    both = run_lockinfo(
        tmp_path, battery=(55, "Discharging"), player=("Playing", "A\tB")
    )
    assert both == "󰁾 55%   ♪ A — B"


def test_hyprlock_uses_the_theme_picture_and_the_status_line():
    """LOCK-4: given hyprlock.conf, then its picture is $character and a label runs
    lockinfo.sh every 5 s, below the password field."""
    with open(HYPRLOCK, encoding="utf-8") as f:
        text = f.read()
    image = re.search(r"image \{([^}]*)\}", text).group(1)
    assert re.search(r"path = \$character\s", image)
    status = next(
        b for b in re.findall(r"label \{([^}]*)\}", text) if "lockinfo.sh" in b
    )
    assert "cmd[update:5000] @HOME@/.config/hypr/scripts/lockinfo.sh" in status
    y_status = int(re.search(r"position = 0, (-?\d+)", status).group(1))
    field = re.search(r"input-field \{([^}]*)\}", text).group(1)
    assert y_status < int(re.search(r"position = 0, (-?\d+)", field).group(1))


def test_the_lock_picture_is_read_once_and_never_reloaded():
    """LOCKSTILL-2: given hyprlock.conf, then its image has reload_time = -1, so
    hyprlock plants no reload timer for it."""
    with open(HYPRLOCK, encoding="utf-8") as f:
        image = re.search(r"image \{([^}]*)\}", f.read()).group(1)
    assert re.search(r"^\s*reload_time = -1$", image, re.M)


def test_lock_writes_only_the_lock_screen_file(tmp_path, monkeypatch):
    """LOCK-6: given `theme.py lock`, then only hyprlock-colors.conf is written, for
    the current theme."""
    shutil.copytree(THEMES, tmp_path / "hypr" / "themes")
    (tmp_path / "hypr" / "themes" / "current").write_text("nami\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    theme.write_lock(str(tmp_path))
    conf = (tmp_path / "hypr" / "hyprlock-colors.conf").read_text()
    assert "nami.json" in conf.splitlines()[0]
    assert not (tmp_path / "hypr" / "themes" / "current.lua").exists()
    assert not (tmp_path / "waybar").exists()


LOCK_SH = os.path.join(ROOT, "config", "hypr", "scripts", "lock.sh")
HYPRLAND_LUA = os.path.join(ROOT, "config", "hypr", "hyprland.lua")


def test_a_dead_locker_can_be_replaced():
    """LOCKR-1: the Hyprland config allows a new locker to take over the lock when
    hyprlock dies or hangs, instead of the lockdead screen until a reboot."""
    lua = open(HYPRLAND_LUA).read()
    misc = lua[lua.index("    misc = {"):]
    misc = misc[: misc.index("    },")]
    assert re.search(r"^\s*allow_session_lock_restore = true,", misc, re.M)


def lock_sandbox(tmp_path):
    """A PATH with fake hyprlock, pidof and hyprctl, and a HOME with a fake GIF
    player: lock.sh runs for real but never meets the real lock screen. The fake
    hyprlock logs "started", keeps its PID in a file, lives FAKE_LOCK_SECONDS, and
    logs the signal that ends it: "unlocked" for SIGUSR1, "term" for SIGTERM. It
    prints "fake hyprlock log" on its stdout. hyprctl lists FAKE_MONITORS, and ps
    says every process has run FAKE_ETIMES seconds (10: past the 5 s grace)."""
    bindir, home = tmp_path / "bin", tmp_path / "home"
    (home / ".config" / "waybar" / "scripts").mkdir(parents=True)
    bindir.mkdir()
    pidfile, calls = tmp_path / "hyprlock.pid", tmp_path / "calls"
    fakes = {
        bindir / "hyprlock": (f'echo started >> {calls}\necho $$ > {pidfile}\necho "fake hyprlock log"\n'
                               f"trap 'echo unlocked >> {calls}; exit 0' USR1\n"
                               f"trap 'echo term >> {calls}; exit 0' TERM\n"
                               'sleep "$FAKE_LOCK_SECONDS" & wait\n'),
        bindir / "pidof": f'p=$(cat {pidfile} 2>/dev/null) && kill -0 "$p" 2>/dev/null && echo "$p"\n',
        bindir / "hyprctl": 'for m in $FAKE_MONITORS; do echo "Monitor $m (ID 0):"; done\n',
        bindir / "ps": 'echo "${FAKE_ETIMES:-10}"\n',
        home / ".config" / "waybar" / "scripts" / "gif_player.py": "exit 0\n",
    }
    for path, body in fakes.items():
        path.write_text("#!/usr/bin/env bash\n" + body)
        path.chmod(0o755)
    env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(tmp_path), XDG_CACHE_HOME=str(home / ".cache"),
               PATH=f"{bindir}:{os.environ['PATH']}", FAKE_LOCK_SECONDS="0.5", FAKE_MONITORS="DP-1 HDMI-A-1")
    return env, pidfile, calls


def test_refresh_replaces_a_running_locker_once_and_starts_none_when_unlocked(tmp_path):
    """LOCKR-2: given no hyprlock, when lock.sh refresh runs, then no lock starts.
    Given a running hyprlock, when two refreshes come in a burst, then that hyprlock
    ends (SIGTERM, not an unlock) and exactly one new lock starts."""
    env, pidfile, calls = lock_sandbox(tmp_path)
    subprocess.run([LOCK_SH, "refresh"], env=env, check=True, timeout=10)
    assert not calls.exists()

    # the running locker, detached so that init reaps it when it ends
    subprocess.run(["bash", "-c", f"FAKE_LOCK_SECONDS=30 {tmp_path}/bin/hyprlock & disown"], env=env, check=True)
    for _ in range(50):
        if pidfile.exists() and pidfile.read_text().strip():
            break
        time.sleep(0.05)
    old = int(pidfile.read_text())

    burst = [subprocess.Popen([LOCK_SH, "refresh"], env=env) for _ in range(2)]
    assert [p.wait(timeout=15) for p in burst] == [0, 0]
    # the old one ends by SIGTERM (never an unlock), then exactly one new one starts
    assert calls.read_text().split() == ["started", "term", "started"]
    assert int(pidfile.read_text()) != old
    assert subprocess.run(["kill", "-0", str(old)], capture_output=True).returncode != 0


def test_a_screen_added_refreshes_the_lock():
    """LOCKR-3: when Hyprland adds a screen (the lid opens, a screen is plugged in),
    the config runs lock.sh refresh."""
    lua = open(HYPRLAND_LUA).read()
    hooks = re.findall(r'hl\.on\("monitor\.added",\s*function\(\) (.*?) end\)', lua)
    assert any('lock.sh refresh"' in h for h in hooks)


# hyprlock 0.9.6's own log lines, as seen live on 2026-10-03 (spec LOCKQ)
# (each line starts with hyprlock's color codes, as in the real log)
D = "\x1b[1;32mDEBUG \x1b[0m]: "
STARTED = "".join(D + line + "\n" for line in (
    "output DP-1 name DP-1",
    "output 86 description Microstep MSI MP271A 0000000000000 (DP-1)",
    "output HDMI-A-1 name HDMI-A-1",
    "output 87 description Samsung Electric Company LS27D300G H1AK500000 (HDMI-A-1)",
    "Configuring surface for logical [Vector2D: x: 1080, y: 1920]",
    "Configuring surface for logical [Vector2D: x: 1920, y: 1080]",
))
LOCKED = STARTED + D + "onLockLocked called\n"
HDMI_BACK = D + "output HDMI-A-1 name HDMI-A-1\n" + D + "output 88 description Samsung (HDMI-A-1)\n"
HDMI_SURFACE = D + "output 88 creating a new lock surface\n"


def refresh_with_log(tmp_path, log, later="", **extra):
    """A running fake hyprlock with this log, then one lock.sh refresh; `later` is
    added to the log 3 s into the refresh (it checks at 2 s). The calls."""
    env, pidfile, calls = lock_sandbox(tmp_path)
    env.update(extra)
    subprocess.run(["bash", "-c", f"FAKE_LOCK_SECONDS=30 {tmp_path}/bin/hyprlock >/dev/null & disown"], env=env, check=True)
    for _ in range(50):
        if pidfile.exists() and pidfile.read_text().strip():
            break
        time.sleep(0.05)
    (tmp_path / "hyprlock.log").write_text(log)
    refresh = subprocess.Popen([LOCK_SH, "refresh"], env=env)
    if later:
        time.sleep(3)
        with open(tmp_path / "hyprlock.log", "a") as f:
            f.write(later)
    assert refresh.wait(timeout=15) == 0
    calls_now = calls.read_text().split()
    subprocess.run(["kill", "-TERM", pidfile.read_text().strip()], capture_output=True)
    return calls_now


def test_the_lock_keeps_hyprlocks_log_of_this_lock(tmp_path):
    """LOCKQ-1: when lock.sh locks, then hyprlock's output is in
    $XDG_RUNTIME_DIR/hyprlock.log, written again at each lock, and the log of the
    lock before it is kept in hyprlock.log.1."""
    env = lock_sandbox(tmp_path)[0]
    (tmp_path / "hyprlock.log").write_text("the last lock\n")
    subprocess.run([LOCK_SH], env=env, check=True, timeout=10)
    assert (tmp_path / "hyprlock.log").read_text() == "fake hyprlock log\n"
    assert (tmp_path / "hyprlock.log.1").read_text() == "the last lock\n"


def test_the_lock_shows_the_first_frame_of_the_gif(tmp_path):
    """LOCKSTILL-3: given lock.png left on frame 7 by an animated lock, when lock.sh
    locks, then lock.png points at frame 000 again."""
    env = lock_sandbox(tmp_path)[0]
    pic = tmp_path / "home" / ".cache" / "gear5" / "lock.png"
    pic.parent.mkdir(parents=True)
    pic.symlink_to(os.path.join("gif", "current", "lock", "007.png"))
    subprocess.run([LOCK_SH], env=env, check=True, timeout=10)
    assert os.readlink(pic) == os.path.join("gif", "current", "lock", "000.png")


def test_the_lock_makes_no_picture_for_a_theme_that_never_had_a_gif(tmp_path):
    """LOCKSTILL-4: given no lock.png, when lock.sh locks, then it still locks and
    no lock.png is made."""
    env, _, calls = lock_sandbox(tmp_path)
    subprocess.run([LOCK_SH], env=env, check=True, timeout=10)
    assert calls.read_text() == "started\n"
    assert not os.path.lexists(tmp_path / "home" / ".cache" / "gear5" / "lock.png")


def test_refresh_leaves_a_hyprlock_that_is_unlocking(tmp_path):
    """LOCKQ-2: given a locked hyprlock that has begun to unlock (a screen just came
    back with no surface yet), when the refresh runs, then it ends nothing and starts
    nothing: after the password is accepted (before the fade-out), and after it logs
    the unlock itself."""
    accepted = LOCKED + HDMI_BACK + D + "auth: authenticated for amir\n"
    assert refresh_with_log(tmp_path / "a", accepted) == ["started"]
    assert refresh_with_log(tmp_path / "b", LOCKED + HDMI_BACK + D + "Unlocking session\n") == ["started"]


def test_refresh_leaves_a_hyprlock_that_covers_every_screen(tmp_path):
    """LOCKQ-3: given a locked hyprlock, when the refresh runs and every active screen
    was known before it locked, or came back and got a new lock surface, then it
    ends nothing and starts nothing."""
    assert refresh_with_log(tmp_path, LOCKED) == ["started"]
    assert refresh_with_log(tmp_path / "back", LOCKED + HDMI_BACK + HDMI_SURFACE) == ["started"]


def test_refresh_replaces_a_stuck_hyprlock_or_one_missing_a_screen(tmp_path):
    """LOCKQ-4: given a hyprlock that has not locked after 5 s, even one that logged
    an unlock it could not finish; or a locked one whose only unlock line came before
    the lock; or a locked one with no lock surface on a screen that came back, or on
    a screen it never saw (DP-1 is not covered by DP-10); or screens that cannot be
    listed: when the refresh runs, then it is ended by SIGTERM and one new lock
    starts. A hyprlock younger than 5 s is checked again once it is 5 s old: left
    alone when it has locked by then, replaced when it has not."""
    replaced = ["started", "term", "started"]
    unlock_signal = D + "Unlocking with a SIGUSR1\n"
    assert refresh_with_log(tmp_path / "a", STARTED + unlock_signal) == replaced
    early = STARTED + unlock_signal + D + "onLockLocked called\n" + HDMI_BACK
    assert refresh_with_log(tmp_path / "b", early) == replaced
    assert refresh_with_log(tmp_path / "c", LOCKED + HDMI_BACK) == replaced
    assert refresh_with_log(tmp_path / "d", LOCKED, FAKE_MONITORS="DP-1 HDMI-A-1 eDP-1") == replaced
    dp10 = LOCKED.replace("(DP-1)", "(DP-10)")
    assert refresh_with_log(tmp_path / "e", dp10, FAKE_MONITORS="DP-1 DP-10 HDMI-A-1") == replaced
    assert refresh_with_log(tmp_path / "f", LOCKED, FAKE_MONITORS="") == replaced
    assert refresh_with_log(tmp_path / "g", STARTED, FAKE_ETIMES="3") == replaced
    assert refresh_with_log(tmp_path / "h", STARTED, later=D + "onLockLocked called\n", FAKE_ETIMES="3") == ["started"]


def test_a_replaced_locker_shows_black_before_the_lockdead_page():
    """LOCKQ-5: the Hyprland config waits 3 s before it shows its lockdead page."""
    lua = open(HYPRLAND_LUA).read()
    misc = lua[lua.index("    misc = {"):]
    misc = misc[: misc.index("    },")]
    assert re.search(r"^\s*lockdead_screen_delay = 3000,", misc, re.M)


def test_the_lock_clock_shows_the_zone_the_bar_shows(tmp_path):
    """Regression: given a pinned zone shown on the bar, then the lock screen's time and
    date labels run `clock.sh now`, which prints them in that zone, not the system's."""
    with open(HYPRLOCK, encoding="utf-8") as f:
        text = f.read()
    clock = "@HOME@/.config/waybar/scripts/clock.sh now"
    assert "$TIME" not in text
    assert f"cmd[update:1000] {clock} +%H:%M" in text
    assert f'{clock} +"%A, %d %B"' in text

    (tmp_path / ".config" / "waybar").mkdir(parents=True)
    zones = tmp_path / ".config" / "waybar" / "clock-zones.json"
    script = os.path.join(ROOT, "config", "waybar", "scripts", "clock.sh")
    env = {k: v for k, v in os.environ.items() if k != "TZ"} | {"HOME": str(tmp_path)}
    # "local" is the system zone (/etc/localtime), which `date` uses with no TZ set
    for active, zone_env in (("Pacific/Kiritimati", {"TZ": "Pacific/Kiritimati"}), ("local", {})):
        zones.write_text(f'{{"active": "{active}", "pinned": ["local", "{active}"]}}')
        fmt = "+%Y-%m-%d %H:%M"
        want = subprocess.run(["date", fmt], env=env | zone_env, capture_output=True, text=True).stdout
        got = subprocess.run([script, "now", fmt], env=env, capture_output=True, text=True).stdout
        assert got == want, active
