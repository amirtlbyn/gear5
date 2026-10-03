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
    logs the signal that ends it: "unlocked" for SIGUSR1, "term" for SIGTERM."""
    bindir, home = tmp_path / "bin", tmp_path / "home"
    (home / ".config" / "waybar" / "scripts").mkdir(parents=True)
    bindir.mkdir()
    pidfile, calls = tmp_path / "hyprlock.pid", tmp_path / "calls"
    fakes = {
        bindir / "hyprlock": (f'echo started >> {calls}\necho $$ > {pidfile}\n'
                               f"trap 'echo unlocked >> {calls}; exit 0' USR1\n"
                               f"trap 'echo term >> {calls}; exit 0' TERM\n"
                               'sleep "$FAKE_LOCK_SECONDS" & wait\n'),
        bindir / "pidof": f'p=$(cat {pidfile} 2>/dev/null) && kill -0 "$p" 2>/dev/null && echo "$p"\n',
        bindir / "hyprctl": "exit 0\n",
        home / ".config" / "waybar" / "scripts" / "gif_player.py": "exit 0\n",
    }
    for path, body in fakes.items():
        path.write_text("#!/usr/bin/env bash\n" + body)
        path.chmod(0o755)
    env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(tmp_path),
               PATH=f"{bindir}:{os.environ['PATH']}", FAKE_LOCK_SECONDS="0.5")
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
