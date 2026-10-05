#!/usr/bin/env python3
"""
A theme's GIF (spec GIFT). The GIF of theme <id> is ~/.config/hypr/themes/<id>.gif. This
file cuts it into frame pictures for the bar's pill and the lock screen, and
gif_player.py steps them.

  theme_gif.py refresh    make the frames of the current theme's GIF, and tell the
                          bar's player (used after a Settings change)

    import theme_gif
    theme_gif.gif("zoro")        # the path of zoro's GIF, or None
    theme_gif.refresh(theme)     # theme.py calls this where it writes the bar colors
"""
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import palette  # noqa: E402

CONFIG = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "gear5")
PLAYER_UNIT = "bar-gif.service"
BAR_FRAME_PX = 60  # 2x the pill's 30 px, so a high-density screen stays sharp
LOCK_FRAME_PX = 200  # hyprlock.conf's image size
MIN_FRAME_MS = 50  # a shorter frame time in the GIF is raised to this (GIF-2)
MAX_FRAMES = 500  # a GIF with more frames is cut here
MAX_GIF_BYTES = 8 * 2**20  # a larger GIF is refused (CHAR-9)


def gif(theme_id, themes=os.path.join(CONFIG, "hypr", "themes")):
    """The person's GIF for this theme, or None (GIFT-5)."""
    if not palette.read_id_ok(theme_id):
        return None
    path = os.path.join(themes, theme_id + ".gif")
    return path if os.path.isfile(path) else None


def gif_dir():
    return os.path.join(CACHE, "gif")


def nudge_player():
    """Tell the bar's player (bar-gif.service) to read the frames again. It is
    decoration: no service, no bar, no problem."""
    subprocess.run(["systemctl", "--user", "kill", "-s", "USR1", PLAYER_UNIT],
                   capture_output=True, timeout=5, check=False)


def _decode(source):
    """([(pixbuf, ms)], one per frame) of a GIF, from an explicit clock: GdkPixbuf
    gives the frame at a time, so the clock steps past each frame's time. The
    iterator returns the first frame's picture again when the GIF loops."""
    import gi

    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib

    def at(ms):
        """The clock ms after the start (1000 s, any fixed time works)."""
        clock = GLib.TimeVal()
        clock.tv_sec, clock.tv_usec = 1000 + ms // 1000, (ms % 1000) * 1000
        return clock

    frame_iter = GdkPixbuf.PixbufAnimation.new_from_file(source).get_iter(at(0))
    frames, elapsed = [], 0  # elapsed: the exact start of the next frame, in ms
    while len(frames) < MAX_FRAMES:
        pixbuf, ms = frame_iter.get_pixbuf(), frame_iter.get_delay_time()
        if any(pixbuf is seen for seen, _ in frames):
            break
        frames.append((pixbuf, max(ms, MIN_FRAME_MS)))
        if ms < 0:  # a GIF that does not loop ends on this frame
            break
        elapsed += ms
        frame_iter.advance(at(elapsed + 1))  # 1 ms into the next frame, never adding up
    return frames


def _write_frames(frames, folder, px, mtime_ns):
    """Frame i as folder/NNN.png, fitted in px x px (never enlarged), with its own
    modification time: hyprlock reloads a picture only when path or mtime changes."""
    from gi.repository import GdkPixbuf

    os.makedirs(folder)
    for i, (pixbuf, _) in enumerate(frames):
        scale = min(1, px / max(pixbuf.get_width(), pixbuf.get_height()))
        if scale < 1:
            pixbuf = pixbuf.scale_simple(max(1, round(pixbuf.get_width() * scale)),
                                         max(1, round(pixbuf.get_height() * scale)),
                                         GdkPixbuf.InterpType.BILINEAR)
        path = os.path.join(folder, f"{i:03d}.png")
        pixbuf.savev(path, "png", [], [])
        os.utime(path, ns=(mtime_ns + i * 1_000_000,) * 2)


def make_frames(theme_id, config=CONFIG):
    """Cut the theme's GIF into frame pictures for the bar and the lock screen:
    gif/<n>/bar/NNN.png, gif/<n>/lock/NNN.png and gif/<n>/frames.json (the frame
    times). The set is complete in a new folder, then the `current` link is swapped
    to it (INV-3), then the old folders go. A theme without a GIF, or a GIF that
    cannot be read, removes `current` (GIF-6). Returns True when frames are ready."""
    root = gif_dir()
    current = os.path.join(root, "current")
    source = gif(theme_id, os.path.join(config, "hypr", "themes"))
    frames = []
    if source:
        try:
            frames = _decode(source)
        except Exception:  # noqa: BLE001 - GLib.Error, ImportError, ...: any failure only costs the GIF
            frames = []
    if not frames:
        if os.path.islink(current):
            os.remove(current)
        return False
    os.makedirs(root, exist_ok=True)
    name = str(time.time_ns())
    folder = os.path.join(root, name)
    mtime_ns = time.time_ns()
    try:
        _write_frames(frames, os.path.join(folder, "bar"), BAR_FRAME_PX, mtime_ns)
        _write_frames(frames, os.path.join(folder, "lock"), LOCK_FRAME_PX, mtime_ns)
        with open(os.path.join(folder, "frames.json"), "w") as f:
            json.dump({"ms": [ms for _, ms in frames]}, f)
        os.symlink(name, current + ".tmp")
        os.replace(current + ".tmp", current)
        # hyprlock reads lock.png once when it starts: point it at frame 0 now, so a
        # one-frame GIF, or a GIF shorter than the last theme's, still shows (GIF-4)
        lock = os.path.join(os.path.dirname(root), "lock.png")
        os.symlink(os.path.join("gif", "current", "lock", "000.png"), lock + ".tmp")
        os.replace(lock + ".tmp", lock)
    except Exception:  # noqa: BLE001 - a half set never becomes current
        shutil.rmtree(folder, ignore_errors=True)
        if os.path.islink(current):
            os.remove(current)
        return False
    for old in os.listdir(root):
        if old not in ("current", name):
            shutil.rmtree(os.path.join(root, old), ignore_errors=True)
    return True


def refresh(t, config=CONFIG):
    """Make the frames of theme t, then tell the bar's player. The frames are
    complete before the player hears about them (INV-3)."""
    make_frames(t["id"], config)
    nudge_player()


def refresh_current(config=CONFIG):
    """refresh() for the theme in use."""
    themes = os.path.join(config, "hypr", "themes")
    refresh(palette.theme(palette.current(themes), themes), config)


def set_gif(theme_id, source, themes=None):
    """Copy source in as themes/<id>.gif (None removes it). Anything that is not a
    GIF, or is over MAX_GIF_BYTES, is refused before the copy (a big GIF is decoded
    into memory frame by frame). The old file stays until the copy is complete (CHAR-9)."""
    themes = themes or os.path.join(CONFIG, "hypr", "themes")
    if not palette.read_id_ok(theme_id):
        raise ValueError(f"“{theme_id}” is not a theme id")
    new = os.path.join(themes, theme_id + ".gif")
    if source is None:
        if os.path.exists(new):
            os.remove(new)
        remake_if_current(theme_id, themes)
        return
    with open(source, "rb") as f:
        if f.read(6) not in (b"GIF87a", b"GIF89a"):
            raise ValueError("Pick a GIF file")
    if os.path.getsize(source) > MAX_GIF_BYTES:
        raise ValueError(f"That GIF is over {MAX_GIF_BYTES // 2**20} MB")
    os.makedirs(themes, exist_ok=True)
    try:
        shutil.copyfile(source, new + ".part")
    except OSError:
        if os.path.exists(new + ".part"):
            os.remove(new + ".part")
        raise
    os.replace(new + ".part", new)
    remake_if_current(theme_id, themes)


def remake_if_current(theme_id, themes):
    """A GIF picked or removed for the theme in use reaches the bar at once (GIF-6)."""
    config = os.path.dirname(os.path.dirname(themes))
    if palette.current(themes) == theme_id:
        refresh_current(config)


def forget(theme_id, config=CONFIG):
    """A deleted theme leaves its GIF behind no more (CHAR-11)."""
    set_gif(theme_id, None, os.path.join(config, "hypr", "themes"))


def migrate(config=CONFIG):
    """Move each characters/<id>.sticker.gif to themes/<id>.gif (GIFT-10). A GIF that
    is already in themes/ is never overwritten, and a move that fails leaves the old
    file where it is. A pass with no failure leaves themes/.gifs-moved, and then it
    never runs again: an old file left beside a newer GIF must not come back after
    the user removes that GIF."""
    characters = os.path.join(config, "hypr", "characters")
    themes = os.path.join(config, "hypr", "themes")
    done = os.path.join(themes, ".gifs-moved")
    if os.path.exists(done):
        return
    try:
        names = os.listdir(characters)
    except OSError:
        names = []
    failed = False
    for name in names:
        theme_id = name.removesuffix(".sticker.gif")
        if theme_id == name or not palette.read_id_ok(theme_id):
            continue
        old = os.path.join(characters, name)
        try:
            os.link(old, os.path.join(themes, theme_id + ".gif"))  # fails when the target exists
        except FileExistsError:
            continue
        except OSError as e:
            print(f"theme_gif: could not move {old}: {e}", file=sys.stderr)
            failed = True
            continue
        os.unlink(old)
    if not failed:
        try:
            open(done, "w").close()
        except OSError:
            pass


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "refresh":
        refresh_current()
    else:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
