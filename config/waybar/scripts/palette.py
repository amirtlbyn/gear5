"""
Theme colors for the popups, the bar and Hyprland: one JSON file per theme in
~/.config/hypr/themes/ (see the README there).

    import palette
    P = palette.load(THEME)            # {"bg0": "#2d353b", "fg": ..., ...}
    P = palette.load(THEME, edge="edge_deep")   # this popup uses the deeper edge

A theme only lists what differs from summer-night; an unknown or broken theme
gives summer-night, so a popup always starts.
"""

import json
import os
import re
import shutil

DEFAULT = "summer-night"
THEMES = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "hypr", "themes")
WALLPAPERS = os.path.join(os.path.dirname(THEMES), "wallpapers")
CHARACTERS = os.path.join(os.path.dirname(THEMES), "characters")  # lock-screen pictures
WALLPAPER_EXTS = (".png", ".jpg", ".jpeg", ".webp")
SINGLE_MARK = ".single"  # in WALLPAPERS: the one wallpaper was set or removed at least once


def read(theme_id, themes=THEMES):
    """The theme file as a dict, or None if it's missing or broken."""
    if not read_id_ok(theme_id):
        return None
    try:
        with open(os.path.join(themes, theme_id + ".json")) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("colors", {}), dict):
        return None
    return data


def theme(theme_id, themes=THEMES):
    """The full theme: its own values over summer-night's. Unknown id -> summer-night."""
    base = read(DEFAULT, themes) or {}
    own = read(theme_id, themes)
    if own is None:
        theme_id, own = DEFAULT, {}
    colors = dict(base.get("colors", {}))
    colors.update({k: v for k, v in own.get("colors", {}).items() if isinstance(v, str)})
    return dict(
        id=theme_id,
        name=own.get("name") or base.get("name") or theme_id,
        character=own.get("character", ""),
        gtk=own.get("gtk") or base.get("gtk") or "Adwaita:dark",
        colors=colors,
    )


def load(theme_id=None, themes=THEMES, **aliases):
    """The colors of a theme (the current one when no id is given)."""
    colors = theme(theme_id or current(themes), themes)["colors"]
    for name, source in aliases.items():
        colors[name] = colors[source]
    return colors


def current(themes=THEMES):
    try:
        with open(os.path.join(themes, "current")) as f:
            theme_id = f.read().strip()
    except OSError:
        return DEFAULT
    return theme_id if read(theme_id, themes) else DEFAULT


def available(themes=THEMES):
    """[(id, name, character)] of every valid theme, summer-night first."""
    out = []
    try:
        names = sorted(os.listdir(themes))
    except OSError:
        names = []
    for n in names:
        if n.endswith(".json") and (data := read(n[:-5], themes)):
            out.append((n[:-5], data.get("name") or n[:-5], data.get("character", "")))
    out.sort(key=lambda t: (t[0] != DEFAULT, t[1].lower()))
    return out


def _old_theme_wallpaper(theme_id, wallpapers):
    """The pre-Gear5 per-theme picture for theme_id, or None."""
    for ext in WALLPAPER_EXTS:
        path = os.path.join(wallpapers, theme_id + ext)
        if os.path.isfile(path):
            return path
    return None


def wallpaper(wallpapers=WALLPAPERS, themes=THEMES):
    """The one wallpaper file used by every theme, or None (then the desktop is
    the current theme's bg0 color).

    Before the one wallpaper was ever set or removed, this copies the current
    theme's old per-theme picture in (GEAR-2). That old file is not removed.
    """
    for ext in WALLPAPER_EXTS:
        single = os.path.join(wallpapers, "wallpaper" + ext)
        if os.path.isfile(single):
            return single
    if os.path.exists(os.path.join(wallpapers, SINGLE_MARK)):
        return None  # removed on purpose: don't bring an old picture back
    old = _old_theme_wallpaper(current(themes), wallpapers)
    if old is None:
        return None
    set_wallpaper(old, wallpapers)
    return os.path.join(wallpapers, "wallpaper" + os.path.splitext(old)[1])


def set_wallpaper(source, wallpapers=WALLPAPERS):
    """Copy source in as the one wallpaper (None removes it); see _install."""
    _install(source, wallpapers, "wallpaper",
             after_copy=lambda: open(os.path.join(wallpapers, SINGLE_MARK), "w").close())


def character(theme_id, characters=CHARACTERS):
    """The person's lock-screen picture for this theme, or None (LOCK-1)."""
    if read_id_ok(theme_id):
        for ext in WALLPAPER_EXTS:
            path = os.path.join(characters, theme_id + ext)
            if os.path.isfile(path):
                return path
    return None


def set_character(theme_id, source, characters=CHARACTERS):
    """Copy source in as this theme's lock-screen picture (None removes it); see
    _install. An id that is not a plain name, or a file that is not a picture,
    is refused (LOCK-5)."""
    if not read_id_ok(theme_id):
        raise ValueError(f"“{theme_id}” is not a theme id")
    if source and os.path.splitext(source)[1].lower() not in WALLPAPER_EXTS:
        raise ValueError("Pick a PNG, JPEG or WebP picture")
    _install(source, characters, theme_id)


def read_id_ok(theme_id):
    """A theme id is a plain name: it ends up in file paths and shell commands."""
    return isinstance(theme_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", theme_id) is not None


def _install(source, folder, stem, after_copy=None):
    """Copy source in as folder/stem.<ext> (None removes it). The copy is done
    before any old file is removed, so a failed copy leaves the old picture in
    place, and only one `stem.<ext>` ever exists at once."""
    os.makedirs(folder, exist_ok=True)
    new = os.path.join(folder, stem + os.path.splitext(source)[1].lower()) if source else None
    if new:
        try:
            shutil.copyfile(source, new + ".part")
        except OSError:
            if os.path.exists(new + ".part"):
                os.remove(new + ".part")
            raise
    if after_copy:
        after_copy()
    for ext in WALLPAPER_EXTS:
        old = os.path.join(folder, stem + ext)
        if old != new and os.path.exists(old):
            os.remove(old)
    if new:
        os.replace(new + ".part", new)
