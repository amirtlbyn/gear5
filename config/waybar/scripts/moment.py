#!/usr/bin/env python3
"""
A theme's "character moment" (roadmap 6.2, spec CHAR; the bar half was replaced by
spec GIF). The pop-up sticker draws a Nerd Font glyph as a die-cut sticker and plays
a motion once. The bar's pill shows the theme's GIF as a flip-book: this file cuts the
GIF into frame pictures, and gif_player.py steps them.

  moment.py refresh    make the frames of the current theme's GIF, and tell the
                       bar's player (used after a Settings change)

    import moment
    moment.moment("zoro")     # {"glyph": "sword_cross", "motion": "swing"}
    moment.refresh(theme)     # theme.py calls this where it writes the bar colors
"""
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import palette  # noqa: E402
import settings_store as store  # noqa: E402

CONFIG = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "gear5")
FONT = "JetBrainsMono Nerd Font"
PLAYER_UNIT = "bar-gif.service"
BAR_FRAME_PX = 60  # 2x the pill's 30 px, so a high-density screen stays sharp
LOCK_FRAME_PX = 200  # hyprlock.conf's image size
MIN_FRAME_MS = 50  # a shorter frame time in the GIF is raised to this (GIF-2)
MAX_FRAMES = 500  # a GIF with more frames is cut here
MAX_GIF_BYTES = 8 * 2**20  # a larger GIF is refused (CHAR-9)
MAX_MS = 1200  # no motion lasts longer (CHAR-5)

# Material Design icons in the Nerd Font, by name, in groups
GLYPHS = {
    # people and faces
    "pirate": 0xF0A08, "ninja": 0xF0774, "person": 0xF0004, "smile": 0xF01F5,
    "skull": 0xF068C, "skull_crossbones": 0xF0BC6, "ghost": 0xF02A0, "robot": 0xF06A9,
    "straw_hat": 0xF0BA4, "chef_hat": 0xF0B7C, "medical_bag": 0xF06EF, "crown": 0xF01A5,
    # weather and sky
    "sun": 0xF0599, "lightning": 0xF0593, "cloud": 0xF0590, "rain": 0xF0597,
    "snow": 0xF0598, "wind": 0xF059D, "sunset": 0xF059B, "umbrella": 0xF054B,
    "snowflake": 0xF0717, "fire": 0xF0238, "water": 0xF058C, "waves": 0xF078D,
    # nature and animals
    "palm_tree": 0xF1055, "flower": 0xF024A, "leaf": 0xF032A, "tree": 0xF0531,
    "pine_tree": 0xF0405, "cactus": 0xF0DB5, "sprout": 0xF0E66, "mushroom": 0xF07DF,
    "fish": 0xF023A, "paw": 0xF03E9, "bird": 0xF15C6, "cat": 0xF011B,
    "dog": 0xF0A43, "rabbit": 0xF0907, "owl": 0xF03D2, "butterfly": 0xF1589,
    "bee": 0xF0FA1, "penguin": 0xF0EC0,
    # things
    "crossed_swords": 0xF0787, "shield": 0xF0498, "bullseye": 0xF08C9, "target": 0xF04FE,
    "anchor": 0xF0031, "compass": 0xF018B, "map": 0xF034D, "treasure": 0xF0726,
    "key": 0xF0306, "diamond": 0xF01C8, "rocket": 0xF0463, "wrench": 0xF05B7,
    "hammer": 0xF08EA, "cog": 0xF0493, "lightbulb": 0xF0335, "violin": 0xF060F,
    "music": 0xF075A, "coffee": 0xF0176, "beer": 0xF0098, "cocktail": 0xF0356,
    "ice_cream": 0xF082A, "gamepad": 0xF02B4, "headphones": 0xF02CB, "camera": 0xF0100,
    "bomb": 0xF0691, "earth": 0xF01E7, "flag": 0xF023B, "palette": 0xF03D8,
    # symbols
    "star": 0xF04CE, "heart": 0xF02D1, "flash": 0xF0241,
}

# One row per motion: (milliseconds, [(percent, rotate deg, scale x, scale y, move x px, move y px)]).
# Each frame lists the same six values, so a browser can blend between any two.
MOTIONS = {
    "wobble": (900, [(0, 0, 1, 1, 0, 0), (20, -18, 1.1, 1.1, 0, 0), (40, 14, 1, 1, 0, 0),
                     (60, -9, 1, 1, 0, 0), (80, 4, 1, 1, 0, 0), (100, 0, 1, 1, 0, 0)]),
    "bounce": (800, [(0, 0, 1, 1, 0, 0), (25, 0, 0.95, 1.08, 0, -10), (50, 0, 1.1, 0.9, 0, 0),
                     (70, 0, 1, 1, 0, -4), (100, 0, 1, 1, 0, 0)]),
    "spin": (800, [(0, 0, 1, 1, 0, 0), (50, 180, 1.15, 1.15, 0, 0), (100, 360, 1, 1, 0, 0)]),
    "pop": (600, [(0, 0, 1, 1, 0, 0), (40, 0, 1.4, 1.4, 0, 0), (70, 0, 0.92, 0.92, 0, 0),
                  (100, 0, 1, 1, 0, 0)]),
    "stretch": (800, [(0, 0, 1, 1, 0, 0), (30, 0, 1.4, 0.8, 0, 0), (60, 0, 0.85, 1.25, 0, 0),
                      (80, 0, 1.1, 0.95, 0, 0), (100, 0, 1, 1, 0, 0)]),
    "swing": (1100, [(0, 0, 1, 1, 0, 0), (20, 25, 1, 1, -4, 0), (45, -20, 1, 1, 3, 0),
                     (65, 12, 1, 1, -2, 0), (85, -5, 1, 1, 1, 0), (100, 0, 1, 1, 0, 0)]),
    "sway": (1200, [(0, 0, 1, 1, 0, 0), (25, -6, 1, 1, -5, 0), (50, 6, 1, 1, 5, 0),
                    (75, -3, 1, 1, -2, 0), (100, 0, 1, 1, 0, 0)]),
    "none": (0, []),
}
FALLBACK = {"glyph": "palette", "motion": "wobble"}


def _first_known(names, known, fallback):
    """The first of names that is a string in known, else fallback. Both the theme
    file and user-settings.json can be edited by hand, so a bad name is skipped."""
    return next((n for n in names if isinstance(n, str) and n in known), fallback)


def moment(theme_id, themes=palette.THEMES):
    """{"glyph", "motion"} of a theme: the person's choice, else the theme file,
    else the fallback (CHAR-2). Each of the two is chosen on its own."""
    own = palette.read(theme_id, themes) or {}
    mine = store.load()["moments"].get(theme_id)
    mine = mine if isinstance(mine, dict) else {}
    return {
        "glyph": _first_known((mine.get("glyph"), own.get("glyph")), GLYPHS, FALLBACK["glyph"]),
        "motion": _first_known((mine.get("motion"), own.get("motion")), MOTIONS, FALLBACK["motion"]),
    }


def draw(glyph, color, path, size=128):
    """Write the sticker picture: the glyph in color, centered on its ink, with a
    soft shadow and no outline. The file appears complete or not at all (INV-4)."""
    import cairo
    import gi

    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    layout = PangoCairo.create_layout(cr)
    font = Pango.FontDescription(FONT)
    font.set_absolute_size(200 * Pango.SCALE)  # drawn big, then scaled to fit
    layout.set_font_description(font)
    layout.set_text(chr(GLYPHS[glyph]), -1)
    ink = layout.get_extents()[0]
    ink_x, ink_y, ink_w, ink_h = (v / Pango.SCALE for v in (ink.x, ink.y, ink.width, ink.height))
    scale = size * 0.78 / max(ink_w, ink_h)
    blur = size * 0.02  # the shadow's soft edge
    cr.translate((size - ink_w * scale) / 2 - ink_x * scale, (size - ink_h * scale) / 2 - ink_y * scale)
    cr.scale(scale, scale)
    PangoCairo.layout_path(cr, layout)
    shape = cr.copy_path()
    cr.new_path()
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    for dy, alpha in ((size * 0.05, 0.18), (size * 0.035, 0.22), (size * 0.02, 0.26)):  # soft shadow
        cr.save()
        cr.translate(0, dy / scale)
        cr.append_path(shape)
        cr.set_line_width(2 * blur / scale)
        cr.set_source_rgba(0, 0, 0, alpha)
        cr.stroke_preserve()
        cr.fill()
        cr.restore()
    cr.append_path(shape)
    cr.set_source_rgb(*(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)))
    cr.fill()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    surface.write_to_png(path + ".part")
    os.replace(path + ".part", path)


def _frames(name, prop="-gtk-icon-transform"):
    ms, rows = MOTIONS[name]
    body = "".join(
        f"  {pct}% {{ {prop}: translate({dx}px, {dy}px) rotate({rot}deg) scale({sx}, {sy}); }}\n"
        for pct, rot, sx, sy, dx, dy in rows
    )
    return ms, body


def gif(theme_id, characters=os.path.join(CONFIG, "hypr", "characters")):
    """The person's GIF for this theme, or None (CHAR-7)."""
    if not palette.read_id_ok(theme_id):
        return None
    path = os.path.join(characters, theme_id + ".sticker.gif")
    return path if os.path.isfile(path) else None


def motion_css(motion):
    """The pop-up sticker's CSS for one motion: `.sticker-art` plays it once, with
    GTK4's `transform` (CHAR-7)."""
    if motion == "none":
        return "/* motion: none */\n"
    ms, body = _frames(motion, "transform")
    return (f"@keyframes sticker-{motion} {{\n{body}}}\n"
            f".sticker-art {{ animation: sticker-{motion} {ms}ms ease-in-out 1; }}\n")


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
    source = gif(theme_id, os.path.join(config, "hypr", "characters"))
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


def set_choice(theme_id, glyph=None, motion=None, config=CONFIG):
    """Save the person's glyph and/or motion for a theme (CHAR-8). Only the pop-up
    shows them. A name left as None is kept."""
    settings = store.load(config)
    moments = dict(settings["moments"])
    mine = dict(moments.get(theme_id) if isinstance(moments.get(theme_id), dict) else {})
    mine.update({k: v for k, v in (("glyph", glyph), ("motion", motion)) if v is not None})
    moments[theme_id] = mine
    store.save(dict(settings, moments=moments), config)


def set_gif(theme_id, source, characters=None):
    """Copy source in as characters/<id>.sticker.gif (None removes it). Anything
    that is not a GIF, or is over MAX_GIF_BYTES, is refused before the copy (a big
    GIF is decoded into memory frame by frame). The old file stays until the copy
    is complete (CHAR-9). characters/<id>.png, the lock picture, is never touched."""
    characters = characters or os.path.join(CONFIG, "hypr", "characters")
    if not palette.read_id_ok(theme_id):
        raise ValueError(f"“{theme_id}” is not a theme id")
    new = os.path.join(characters, theme_id + ".sticker.gif")
    if source is None:
        if os.path.exists(new):
            os.remove(new)
        remake_if_current(theme_id, characters)
        return
    with open(source, "rb") as f:
        if f.read(6) not in (b"GIF87a", b"GIF89a"):
            raise ValueError("Pick a GIF file")
    if os.path.getsize(source) > MAX_GIF_BYTES:
        raise ValueError(f"That GIF is over {MAX_GIF_BYTES // 2**20} MB")
    os.makedirs(characters, exist_ok=True)
    try:
        shutil.copyfile(source, new + ".part")
    except OSError:
        if os.path.exists(new + ".part"):
            os.remove(new + ".part")
        raise
    os.replace(new + ".part", new)
    remake_if_current(theme_id, characters)


def remake_if_current(theme_id, characters):
    """A GIF picked or removed for the theme in use reaches the bar at once (GIF-6)."""
    config = os.path.dirname(os.path.dirname(characters))
    if palette.current(os.path.join(config, "hypr", "themes")) == theme_id:
        refresh_current(config)


def forget(theme_id, config=CONFIG):
    """A deleted theme leaves nothing behind: its choices and its GIF (CHAR-11)."""
    settings = store.load(config)
    if theme_id in settings["moments"]:
        kept = {k: v for k, v in settings["moments"].items() if k != theme_id}
        store.save(dict(settings, moments=kept), config)
    set_gif(theme_id, None, os.path.join(config, "hypr", "characters"))


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
