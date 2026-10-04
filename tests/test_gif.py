"""The theme's GIF on the bar (spec GIF). See config/waybar/scripts/theme_gif.py
(make_frames) and gif_player.py (BarPlayer). GdkPixbuf cannot write a GIF, so the
tests write the bytes of a small one."""

import os
import signal
import struct
import subprocess

import gif_player
import pytest
import settings_store as store
import theme_gif
from conftest import ROOT
from test_bar_strip import settings_method


def make_gif(*delays_cs):
    """The bytes of a 1 x 1 GIF with one frame per delay, each delay in 1/100 s."""
    head = b"GIF89a" + struct.pack("<HHBBB", 1, 1, 0x80, 0, 0) + bytes([0, 0, 0, 255, 255, 255])
    loop = b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
    frames = b"".join(
        b"\x21\xf9\x04\x00" + struct.pack("<H", cs) + b"\x00\x00"
        + b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00"
        for cs in delays_cs
    )
    return head + loop + frames + b"\x3b"


def install_gif(config, theme_id, data):
    themes = config / "hypr" / "themes"
    themes.mkdir(parents=True, exist_ok=True)
    (themes / f"{theme_id}.gif").write_bytes(data)


def bar_player(told):
    return gif_player.BarPlayer(tell_bar=lambda: told.append("told"))


def test_the_pill_shows_the_gif_and_is_hidden_without_one_or_with_the_switch_off(tmp_path, monkeypatch):
    """GIF-1: given the bar player, when the theme has a GIF and the switch is on,
    then the pill link points at a frame that exists; when the theme has no GIF, or
    the switch is off, then the link points at nothing."""
    install_gif(tmp_path, "zoro", make_gif(10, 10))
    told = []
    player = bar_player(told)
    link = os.path.join(theme_gif.CACHE, "bar.png")
    monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS, gif_bar=True))

    theme_gif.make_frames("zoro", str(tmp_path))
    player.load()
    assert os.path.isfile(link)

    monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS, gif_bar=False))
    player.load()
    assert os.path.islink(link) and not os.path.exists(link)

    monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS, gif_bar=True))
    theme_gif.make_frames("brook", str(tmp_path))
    player.load()
    assert os.path.islink(link) and not os.path.exists(link)


def test_the_player_steps_frames_in_order_with_their_times_and_a_still_pill_steps_none(tmp_path, monkeypatch):
    """GIF-2: given a two-frame GIF of 100 ms and 30 ms, when the bar plays it, then
    the frames come in order with the times 0.1 s and 0.05 s (the 50 ms floor) and
    loop; when the GIF has one frame, then no timer is due and no frame is stepped."""
    monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS, gif_bar=True, bar_gif="always"))
    install_gif(tmp_path, "zoro", make_gif(10, 3))
    install_gif(tmp_path, "brook", make_gif(10))
    told = []
    player = bar_player(told)

    theme_gif.make_frames("zoro", str(tmp_path))
    player.load()
    assert os.path.realpath(player.link).endswith("/bar/000.png")
    assert player.wait() == 0.1
    assert player.step() == 0.05
    assert os.path.realpath(player.link).endswith("/bar/001.png")
    assert player.step() == 0.1
    assert os.path.realpath(player.link).endswith("/bar/000.png")

    theme_gif.make_frames("brook", str(tmp_path))
    player.load()
    told.clear()
    assert player.wait() is None
    assert player.step() is None
    assert told == []


def test_frames_are_made_whole_or_the_theme_has_none(tmp_path):
    """GIF-6: given a two-frame GIF, when frames are made, then there are two bar and
    two lock frames with distinct modification times and the frame times; when they are
    made again, then one set is left and `current` points at it; when the GIF cannot
    be read, then `current` is gone."""
    install_gif(tmp_path, "zoro", make_gif(10, 3))
    root = theme_gif.gif_dir()

    assert theme_gif.make_frames("zoro", str(tmp_path)) is True
    assert theme_gif.make_frames("zoro", str(tmp_path)) is True

    current = os.path.join(root, "current")
    assert sorted(os.listdir(os.path.join(current, "bar"))) == ["000.png", "001.png"]
    assert sorted(os.listdir(os.path.join(current, "lock"))) == ["000.png", "001.png"]
    bar_times = {os.stat(os.path.join(current, "bar", n)).st_mtime_ns for n in ("000.png", "001.png")}
    lock_times = {os.stat(os.path.join(current, "lock", n)).st_mtime_ns for n in ("000.png", "001.png")}
    assert len(bar_times) == 2 and len(lock_times) == 2
    assert sorted(os.listdir(root)) == sorted(["current", os.readlink(current)])
    with open(os.path.join(current, "frames.json")) as f:
        assert f.read() == '{"ms": [100, 50]}'

    install_gif(tmp_path, "zoro", b"GIF89a not really a gif")
    assert theme_gif.make_frames("zoro", str(tmp_path)) is False
    assert not os.path.lexists(current)


def test_a_long_gif_keeps_every_frame_in_order():
    """Review of session 1: given a GIF of 60 frames of 20 ms, when it is decoded,
    then all 60 frames come back (the decode clock does not drift and skip any),
    each held at least 50 ms."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".gif") as f:
        f.write(make_gif(*[2] * 60))
        f.flush()
        frames = theme_gif._decode(f.name)
    assert len(frames) == 60
    assert all(ms == theme_gif.MIN_FRAME_MS for _pixbuf, ms in frames)


def test_the_bar_player_signals_only_a_process_named_waybar(monkeypatch):
    """Review of session 1: given a cached Waybar PID that now belongs to another
    program, when the player tells the bar, then that PID gets no signal and the
    player looks up Waybar again."""
    names = {111: "waybar", 222: "waybar"}
    sent = []
    monkeypatch.setattr(gif_player, "is_waybar", lambda pid: names.get(pid) == "waybar")
    monkeypatch.setattr(gif_player, "waybar_pids", lambda: [p for p, n in names.items() if n == "waybar"])
    monkeypatch.setattr(gif_player.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    player = gif_player.BarPlayer(tell_bar=lambda: None)

    player.signal_waybar()
    names[111] = "firefox"  # Waybar 111 restarted; its PID was reused
    player.signal_waybar()

    rt = gif_player.signal.SIGRTMIN + gif_player.WAYBAR_SIGNAL
    assert sent == [(111, rt), (222, rt), (222, rt)]


def test_bar_gif_plays_by_the_choice_and_the_choice_is_checked_and_saved(tmp_path, monkeypatch):
    """GIF-3: given "Bar GIF plays", then the default is Only on AC power and a bad
    value is refused on save and ignored on load; when the choice is Always, the
    GIF plays; when Only on AC power, it plays on mains and rests on battery,
    following a plug or unplug at the next 5 s look; when Only after a theme
    switch, it plays for 5 s after new frames and then rests; when Settings saves
    the choice, then bar-gif.service is restarted."""
    assert store.DEFAULTS["bar_gif"] == "ac"
    xkb = tmp_path / "xkb"
    xkb.mkdir()
    (xkb / "us").write_text("")
    (tmp_path / "hypr").mkdir()
    (tmp_path / "hypr" / "user-settings.json").write_text('{"bar_gif": "sometimes"}')
    assert store.load(str(tmp_path))["bar_gif"] == "ac"
    with pytest.raises(ValueError):
        store.save(dict(store.DEFAULTS, bar_gif="sometimes"), str(tmp_path), str(xkb))

    supply = tmp_path / "power" / "ADP0"
    supply.mkdir(parents=True)
    (supply / "type").write_text("Mains\n")
    (supply / "online").write_text("1\n")
    now = [100.0]
    install_gif(tmp_path, "zoro", make_gif(10, 10))
    theme_gif.make_frames("zoro", str(tmp_path))
    player = gif_player.BarPlayer(tell_bar=lambda: None, power_root=str(tmp_path / "power"), clock=lambda: now[0])

    def load(mode, switched=False):
        monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS, gif_bar=True, bar_gif=mode))
        player.load(switched)

    load("always")
    assert player.playing() and player.wait() == 0.1

    load("ac")
    assert player.playing() and player.wait() == 0.1
    (supply / "online").write_text("0\n")
    assert player.step() == gif_player.POWER_POLL_S
    assert not player.playing() and player.index == 0
    (supply / "online").write_text("1\n")
    assert player.step() == 0.1 and player.playing()

    load("switch")
    assert not player.playing() and player.wait() is None
    load("switch", switched=True)
    assert player.playing() and player.wait() == 0.1
    assert player.step() == 0.1 and player.index == 1
    now[0] += 5.5
    assert player.step() is None and not player.playing() and player.index == 0
    assert os.path.realpath(player.link).endswith("/bar/000.png")

    spawned, saved = [], []
    (tmp_path / "a.lua").write_text("")
    fake_store = type("Store", (), {
        "load": staticmethod(lambda: dict(store.DEFAULTS)),
        "save": staticmethod(saved.append),
        "paths": staticmethod(lambda: (str(tmp_path / "a.json"), str(tmp_path / "a.lua"))),
    })
    ns = {"store": fake_store, "spawn": spawned.append, "os": os}
    exec(settings_method("save"), ns)  # noqa: S102 - the repo's own settings.py source
    error = type("Label", (), {"set_label": lambda *_: None, "set_visible": lambda *_: None})()
    ns["save"](type("Host", (), {"error": error})(), bar_gif="always")
    assert spawned == [["systemctl", "--user", "restart", "bar-gif.service"]]
    assert saved[0]["bar_gif"] == "always"


def test_a_mains_supply_that_cannot_be_read_or_a_missing_power_root_counts_as_on_ac(tmp_path):
    """Review of session 2: given a Mains supply with no online file, or a power
    folder that does not exist, when the player looks at the charger, then it
    counts as on AC."""
    supply = tmp_path / "power" / "ADP0"
    supply.mkdir(parents=True)
    (supply / "type").write_text("Mains\n")

    assert gif_player.on_mains(str(tmp_path / "power")) is True
    assert gif_player.on_mains(str(tmp_path / "missing")) is True


CATCHES_USR2 = "Name:\thyprlock\nSigCgt:\t0000000000000800\n"  # a handler for signal 12 only


def lock_player(tmp_path, sent):
    """A lock player for PID 4242 with a fake /proc, whose os.kill only records."""
    comm = tmp_path / "proc" / "4242" / "comm"
    comm.parent.mkdir(parents=True)
    comm.write_text("hyprlock\n")
    (comm.parent / "status").write_text(CATCHES_USR2)
    return gif_player.LockPlayer(4242, proc=str(tmp_path / "proc"), kill=lambda pid, sig: sent.append((pid, sig))), comm


def test_the_lock_flip_book_sends_only_sigusr2_only_to_hyprlock_and_stops_with_it(tmp_path):
    """GIF-5: given a lock player for PID 4242, when hyprlock runs, then each frame
    sends SIGUSR2 to 4242 and nothing else; when the name of that PID stops reading
    hyprlock, or the PID is gone, or the signal fails, then nothing more is sent
    and the player returns."""
    install_gif(tmp_path, "zoro", make_gif(10, 10, 10))
    theme_gif.make_frames("zoro", str(tmp_path))
    sent = []
    player, comm = lock_player(tmp_path, sent)
    actions = iter([lambda: None, lambda: None, lambda: comm.write_text("firefox\n")])

    player.run(sleep=lambda _s: next(actions)())

    assert gif_player.LOCK_SIGNAL == signal.SIGUSR2
    assert sent == [(4242, signal.SIGUSR2), (4242, signal.SIGUSR2)]
    assert os.path.realpath(player.link).endswith("/lock/002.png")

    sent.clear()
    comm.unlink()  # the PID is gone
    player.run(sleep=lambda _s: None)
    assert sent == []

    comm.write_text("hyprlock\n")

    def gone(pid, sig):
        raise ProcessLookupError

    sleeps = []

    def sleep(_s):
        sleeps.append(1)
        assert len(sleeps) < 5, "the player kept going after the signal failed"

    gif_player.LockPlayer(4242, proc=str(tmp_path / "proc"), kill=gone).run(sleep=sleep)
    assert len(sleeps) == 1  # one try, then the player returned


def source(path):
    with open(os.path.join(ROOT, path)) as f:
        return f.read()


def run_lock_sh(tmp_path, pidof_rc):
    """lock.sh with fake pidof, hyprctl, hyprlock and player; returns what each logged."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    log = tmp_path / "log"
    log.touch()
    fakes = {
        "pidof": f"exit {pidof_rc}",
        "hyprctl": f'echo "hyprctl $*" >> {log}',
        "hyprlock": f'echo "hyprlock $$" >> {log}; sleep 0.3',
    }
    for name, body in fakes.items():
        (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bin_dir / name).chmod(0o755)
    player = tmp_path / "home" / ".config" / "waybar" / "scripts" / "gif_player.py"
    player.parent.mkdir(parents=True)
    player.write_text(f'#!/bin/sh\necho "player $*" >> {log}\n')
    player.chmod(0o755)
    script = os.path.join(ROOT, "config", "hypr", "scripts", "lock.sh")
    env = dict(os.environ, HOME=str(tmp_path / "home"), XDG_CACHE_HOME=str(tmp_path / "home" / ".cache"), PATH=f"{bin_dir}:{os.environ['PATH']}")
    done = subprocess.run(["bash", script], env=env, timeout=10, check=False)
    return done.returncode, log.read_text().splitlines()


def test_every_lock_goes_through_lock_sh_which_starts_one_hyprlock_and_no_player(tmp_path):
    """GIF-7, LOCKSTILL-1: given the four places that lock, then each runs lock.sh;
    when hyprlock already runs, then lock.sh starts nothing; when it does not, then
    it starts hyprlock and never the GIF player, so nothing sends SIGUSR2 to it."""
    assert "scripts/lock.sh" in source("config/hypr/hyprland.lua")
    assert "scripts/lock.sh" in source("config/hypr/scripts/idle.sh")
    assert "scripts/lock.sh" in source("config/waybar/scripts/launcher.py")
    assert "scripts/lock.sh" in source("config/waybar/scripts/power-popup.py")
    assert "hyprlock)" not in source("config/hypr/scripts/idle.sh")

    code, log = run_lock_sh(tmp_path / "locked", pidof_rc=0)
    assert (code, log) == (0, [])

    code, log = run_lock_sh(tmp_path / "free", pidof_rc=1)
    assert code == 0 and log[0] == "hyprctl switchxkblayout all 0"
    assert [line.split()[0] for line in log[1:]] == ["hyprlock"]


def test_the_lock_picture_exists_before_the_first_lock_even_for_a_one_frame_gif(tmp_path):
    """Review of session 3: given a theme with a one-frame GIF (the lock player
    does not run for it), when its frames are made, then lock.png already shows
    frame 0, so hyprlock has a picture from its first draw."""
    install_gif(tmp_path, "zoro", make_gif(10))

    assert theme_gif.make_frames("zoro", str(tmp_path))
    lock = os.path.join(theme_gif.CACHE, "lock.png")
    assert os.path.isfile(lock)  # follows the link
    assert os.path.realpath(lock).endswith(os.path.join("lock", "000.png"))


def test_the_lock_player_waits_until_hyprlock_has_locked(tmp_path):
    """Review of session 3 (deep review): given hyprlock still starting (its SIGUSR2
    handler, set only after it locks, is not in SigCgt yet), when frames are due,
    then nothing is sent, because SIGUSR2 would end hyprlock before it locks; once
    the handler is set, then SIGUSR2 is sent."""
    install_gif(tmp_path, "zoro", make_gif(10, 10))
    theme_gif.make_frames("zoro", str(tmp_path))
    sent = []
    player, comm = lock_player(tmp_path, sent)
    status = comm.parent / "status"
    status.write_text("Name:\thyprlock\nSigCgt:\t0000000000004000\n")  # SIGTERM only
    player.load()

    assert player.step() and player.step()
    assert sent == []

    status.write_text(CATCHES_USR2)
    assert player.step()
    assert sent == [(4242, signal.SIGUSR2)]
