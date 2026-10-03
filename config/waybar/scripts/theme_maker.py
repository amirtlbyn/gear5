#!/usr/bin/env python3
"""
Make a theme: derive its colors from four picks, check its name, and save,
rename or delete it. No GTK import, so pytest can load it (settings.py has the
editor UI). The roles are the ones in ~/.config/hypr/themes/README.md.

    import theme_maker
    colors = theme_maker.derive(bg, fg, accent, accent2)
    error = theme_maker.check_name("My theme", palette.THEMES)
    theme_id = theme_maker.save("My theme", colors)
    theme_maker.rename(theme_id, "New name")
    theme_maker.delete(theme_id)
"""
import colorsys
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import moment  # noqa: E402
import palette  # noqa: E402
import theme  # noqa: E402

# (text, background, minimum): each pair appears on screen as text on a background.
# Shared with tests/test_contrast.py, which checks it against the 12 built-in themes.
PAIRS = [
    ("fg", "bg0", 7.0),  # popup and bar-box text
    ("bg0", "fg", 7.0),  # text on the bar itself
    ("green", "bg0", 4.5),  # accent text: highlights, the other-timezone clock
    ("on_accent", "green", 4.5),  # selected chips and buttons
    ("bg0", "green", 4.5),  # the launcher button
    ("bg0", "blue", 4.5),  # the active desk
    ("bg0", "red", 4.5),  # the power button
    ("grey", "bg0", 3.0),  # dim text: hints, section titles
    ("on_accent", "aqua", 4.5),  # calculator and control-center tiles (aqua-to-green gradient)
    ("on_accent", "purple", 4.5),  # calculator toggles that are on
    ("on_accent", "yellow", 4.5),  # the control center's open chevron
    ("yellow", "bg0", 4.5),  # the bar's "stay awake" sign
]

# The Summer night hues that a made theme's minor accents keep.
_HUES = {
    "red": "#e67e80",
    "red_hover": "#f08b8d",
    "orange": "#e69875",
    "yellow": "#dbbc7f",
    "aqua": "#83c092",
    "purple": "#d699b6",
}

THEME_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme.py")


# --- color math -------------------------------------------------------------
# Every derived color keeps its own hue and saturation; only its HSL lightness
# moves, to hit a target contrast (WCAG relative luminance, same formula as
# tests/test_contrast.py).


def _hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _luminance(rgb):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast_y(y_a, y_b):
    hi, lo = (y_a, y_b) if y_a >= y_b else (y_b, y_a)
    return (hi + 0.05) / (lo + 0.05)


def _with_lightness(color, lightness):
    """color's hue and saturation, at a new HSL lightness (0 to 1)."""
    r, g, b = (c / 255 for c in _hex_to_rgb(color))
    h, _, s = colorsys.rgb_to_hls(r, g, b)
    r2, g2, b2 = colorsys.hls_to_rgb(h, max(0.0, min(1.0, lightness)), s)
    return _rgb_to_hex((r2 * 255, g2 * 255, b2 * 255))


def _fit_luminance(color, target_y):
    """color, re-lit until its relative luminance is target_y (binary search: for a
    fixed hue and saturation, luminance rises with HSL lightness)."""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if _luminance(_hex_to_rgb(_with_lightness(color, mid))) < target_y:
            lo = mid
        else:
            hi = mid
    return _with_lightness(color, (lo + hi) / 2)


def _best_y(requirements, current_y, steps=400):
    """The luminance in [0, 1] closest to current_y that meets every (other_y, minimum)
    requirement, so a picked color moves only as far as it must. When no luminance
    meets them all, the one with the best worst-case margin."""
    if all(_contrast_y(current_y, other_y) >= minimum for other_y, minimum in requirements):
        return current_y
    nearest, fallback, best_score = None, current_y, -1e9
    for i in range(steps + 1):
        y = i / steps
        score = min(_contrast_y(y, other_y) - minimum for other_y, minimum in requirements)
        if score >= 0 and (nearest is None or abs(y - current_y) < abs(nearest - current_y)):
            nearest = y
        if score > best_score:
            best_score, fallback = score, y
    return fallback if nearest is None else nearest


def _fit_against(color, bg_y, minimum, margin=0.05):
    """color, re-lit to read against one background at least as well as minimum.
    A color that already reads well enough is returned unchanged."""
    y = _luminance(_hex_to_rgb(color))
    target = _best_y([(bg_y, minimum + margin)], y)
    return color if target == y else _fit_luminance(color, target)


def _mix(color_a, color_b, t):
    """Linear RGB blend, t of the way from color_a to color_b."""
    ra, ga, ba = _hex_to_rgb(color_a)
    rb, gb, bb = _hex_to_rgb(color_b)
    return _rgb_to_hex((ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t))


def _step(base, other, frac):
    """base, moved frac of the way toward other's lightness (frac can be negative)."""
    r, g, b = (c / 255 for c in _hex_to_rgb(base))
    l_base = colorsys.rgb_to_hls(r, g, b)[1]
    r2, g2, b2 = (c / 255 for c in _hex_to_rgb(other))
    l_other = colorsys.rgb_to_hls(r2, g2, b2)[1]
    return _with_lightness(base, l_base + frac * (l_other - l_base))


def derive(bg, fg, accent, accent2):
    """The 33 colors of README.md's role table, from four picks: background, text,
    main accent, second accent.

    bg never moves, except for the popup-text pair: on a mid-grey bg no text color
    can reach that pair's 7:1 minimum, so that one pair alone may also re-light bg.
    Every other role keeps its own hue but is re-lit, against bg (or against the
    accents, for on_accent), to meet every pair in tests/test_contrast.py's PAIRS.
    """
    bg0_y = _luminance(_hex_to_rgb(bg))
    fg_fit = _fit_against(fg, bg0_y, 7.0)
    if _contrast_y(_luminance(_hex_to_rgb(fg_fit)), bg0_y) >= 7.0:
        bg0 = bg
    else:
        fg_y = _luminance(_hex_to_rgb(fg))
        bg0 = _fit_luminance(bg, _best_y([(fg_y, 7.05)], bg0_y))
        bg0_y = _luminance(_hex_to_rgb(bg0))
        fg_fit = _fit_against(fg, bg0_y, 7.0)

    accent_y = _luminance(_hex_to_rgb(accent))
    grey = _fit_against(_mix(bg0, fg_fit, 0.42), bg0_y, 3.0)
    green = _fit_against(accent, bg0_y, 4.5)
    blue = _fit_against(_fit_luminance(accent2, accent_y), bg0_y, 4.5)
    red = _fit_against(_fit_luminance(_HUES["red"], accent_y), bg0_y, 4.5)
    yellow = _fit_against(_fit_luminance(_HUES["yellow"], accent_y), bg0_y, 4.5)
    aqua = _fit_against(_fit_luminance(_HUES["aqua"], accent_y), bg0_y, 4.5)
    purple = _fit_against(_fit_luminance(_HUES["purple"], accent_y), bg0_y, 4.5)

    on_accent_needs = [(_luminance(_hex_to_rgb(c)), 4.55) for c in (green, aqua, purple, yellow)]
    on_accent = _fit_luminance(bg0, _best_y(on_accent_needs, bg0_y))

    grey0 = _mix(bg0, fg_fit, 0.32)
    grey2 = _mix(bg0, fg_fit, 0.52)
    red_hover = _fit_luminance(_HUES["red_hover"], min(1.0, _luminance(_hex_to_rgb(red)) + 0.08))
    orange = _fit_luminance(_HUES["orange"], accent_y)
    bg1 = _step(bg0, fg_fit, 0.08)

    return {
        "bg_dim": _step(bg0, fg_fit, -0.05),
        "bg0": bg0,
        "bg1": bg1,
        "bg2": _step(bg0, fg_fit, 0.16),
        "bg3": _step(bg0, fg_fit, 0.24),
        "bg4": _step(bg0, fg_fit, 0.30),
        "bg5": _step(bg0, fg_fit, 0.36),
        "bg_visual": _mix(bg1, purple, 0.18),
        "bg_red": _mix(bg1, red, 0.18),
        "bg_green": _mix(bg1, green, 0.18),
        "bg_blue": _mix(bg1, blue, 0.18),
        "bg_yellow": _mix(bg1, yellow, 0.18),
        "fg": fg_fit,
        "grey0": grey0,
        "grey": grey,
        "grey2": grey2,
        "red": red,
        "red_hover": red_hover,
        "orange": orange,
        "yellow": yellow,
        "green": green,
        "aqua": aqua,
        "blue": blue,
        "purple": purple,
        "on_accent": on_accent,
        "edge": _step(bg0, fg_fit, -0.10),
        "edge_deep": _step(bg0, fg_fit, -0.16),
        "green_edge": _step(green, "#000000", 0.35),
        "red_edge": _step(red, "#000000", 0.30),
        "blue_edge": _step(blue, "#000000", 0.35),
        "bar_edge": _mix(fg_fit, bg0, 0.55),
        "shadow": "rgba(0,0,0,0.55)",
        "shadow_inactive": _step(bg0, fg_fit, -0.03),
    }


# --- naming, saving, renaming, deleting -------------------------------------


def check_name(name, themes=palette.THEMES, exclude_id=None):
    """None when the name is usable, else why it isn't. exclude_id is the theme being
    edited or renamed: it may keep its own name."""
    name = (name or "").strip()
    if not name:
        return "Name the theme."
    if len(name) > 40:
        return "40 characters or fewer."
    taken = {n.lower() for tid, n, _character in palette.available(themes) if tid != exclude_id}
    if name.lower() in taken:
        return "Another theme already has that name."
    return None


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "theme"


def _new_id(name, themes):
    """A file name from name: lowercase, hyphenated, never an existing theme's."""
    base = _slug(name)
    theme_id, n = base, 2
    while os.path.isfile(os.path.join(themes, theme_id + ".json")):
        theme_id = f"{base}-{n}"
        n += 1
    return theme_id


def _require_custom(theme_id, themes):
    """theme_id's data, or raise: a built-in theme is never touched here (INV-1)."""
    data = palette.read(theme_id, themes)
    if data is None or not data.get("custom"):
        raise ValueError(f"{theme_id!r} is not a custom theme")
    return data


def save(name, colors, theme_id=None, themes=palette.THEMES):
    """Write a custom theme: a new id from name, or an existing custom theme's id
    to replace it in place. Never overwrites a built-in theme's file."""
    name = (name or "").strip()
    if theme_id is None:
        theme_id = _new_id(name, themes)
    else:
        _require_custom(theme_id, themes)
    data = {"name": name, "character": "", "gtk": "Adwaita:dark", "custom": True, "colors": colors}
    theme.write(os.path.join(themes, theme_id + ".json"), json.dumps(data, indent=2) + "\n")
    return theme_id


def rename(theme_id, name, themes=palette.THEMES):
    """Give a custom theme a new name."""
    data = _require_custom(theme_id, themes)
    data = dict(data, name=(name or "").strip())
    theme.write(os.path.join(themes, theme_id + ".json"), json.dumps(data, indent=2) + "\n")


def _apply_theme_py(theme_id):
    """The default apply for delete(): the same switch settings.py itself runs."""
    subprocess.run([THEME_PY, "apply", theme_id], capture_output=True, timeout=20)


def delete(theme_id, themes=palette.THEMES, apply=_apply_theme_py):
    """Remove a custom theme's file. Switches to Summer night first, through apply,
    when this theme is the one in use."""
    _require_custom(theme_id, themes)
    if palette.current(themes) == theme_id:
        apply(palette.DEFAULT)
    os.remove(os.path.join(themes, theme_id + ".json"))
    moment.forget(theme_id, os.path.dirname(os.path.dirname(themes)))
