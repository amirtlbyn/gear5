"""
The choices made in the Settings app (settings.py), kept in
~/.config/hypr/user-settings.json and turned into ~/.config/hypr/user-settings.lua,
which hyprland.lua loads last, so they win over its defaults. Writing the Lua file
makes Hyprland reload by itself.

    import settings_store as store
    s = store.load()                  # every setting, defaults filled in
    store.save(dict(s, gaps=False))   # raises ValueError for a value Hyprland can't take
"""

import json
import os
import re

CONFIG = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
XKB_SYMBOLS = "/usr/share/X11/xkb/symbols"

DEFAULTS = dict(
    kb_layout="us,ir",
    natural_scroll=True,
    tap_to_click=True,
    gaps=True,
    animations=True,
    bar_strip=True,
    font_en="JetBrainsMono Nerd Font",
    font_fa="Vazirmatn",
    battery_stop=100,
    battery_start=95,
    battery_speed="Fast",
    sticker_bar=True,
    sticker_switch=True,
    bar_gif="ac",  # when the bar's GIF plays (gif_player.py): "always", "ac" or "switch"
    moments={},  # theme id -> {"glyph": ..., "motion": ...}, the person's choices (moment.py)
    night_mode="off",  # the night light (night_light.py): "off", "sunset" or "schedule"
    night_temp=4000,
    night_start="20:00",
    night_end="07:00",
)
SWITCHES = ("natural_scroll", "tap_to_click", "gaps", "animations", "bar_strip", "sticker_bar", "sticker_switch")
FONTS = ("font_en", "font_fa")
# the values hyprland.lua uses (and toggle-gaps.sh puts back)
GAPS_ON = dict(gaps_in=10, gaps_out=20, rounding=10)
NIGHT_MODES = ("off", "sunset", "schedule")
BAR_GIF_MODES = ("always", "ac", "switch")
NIGHT_TEMPS = (2500, 5500)  # the warmth slider's range, in kelvin


def paths(config=CONFIG):
    hypr = os.path.join(config, "hypr")
    return os.path.join(hypr, "user-settings.json"), os.path.join(hypr, "user-settings.lua")


def known_layouts(symbols=XKB_SYMBOLS):
    """Keyboard layouts this system has, or None if it can't tell."""
    try:
        return set(os.listdir(symbols))
    except OSError:
        return None


def check_layouts(value, symbols=XKB_SYMBOLS):
    """ "us, ir" -> "us,ir". A layout the system doesn't have would leave you without a
    working keyboard, so it is refused."""
    parts = [p.strip().lower() for p in str(value).split(",") if p.strip()]
    if not parts or len(parts) > 4:
        raise ValueError("Give one to four keyboard layouts, like: us,ir")
    known = known_layouts(symbols)
    for p in parts:
        if not re.fullmatch(r"[a-z]{2,8}", p) or (known is not None and p not in known):
            raise ValueError(f"“{p}” is not a keyboard layout on this system (examples: us, ir, de, fr)")
    return ",".join(parts)


def check_font(value):
    """A font family name: not empty, not endless. The Fonts page only offers
    installed names; this guards a hand-edited file."""
    name = str(value).strip()
    if not name or len(name) > 60 or any(c in name for c in '"{};'):
        raise ValueError(f"“{value}” is not a font family name")
    return name


def check_night_mode(value):
    if value not in NIGHT_MODES:
        raise ValueError(f"“{value}” is not a night light mode ({', '.join(NIGHT_MODES)})")
    return value


def check_bar_gif(value):
    if value not in BAR_GIF_MODES:
        raise ValueError(f"“{value}” is not a Bar GIF choice ({', '.join(BAR_GIF_MODES)})")
    return value


def check_night_temp(value):
    if isinstance(value, bool) or not isinstance(value, int) or not NIGHT_TEMPS[0] <= value <= NIGHT_TEMPS[1]:
        raise ValueError(f"The night light warmth is {NIGHT_TEMPS[0]} to {NIGHT_TEMPS[1]} K, not {value}")
    return value


def check_time(value):
    """ "HH:MM" from 00:00 to 23:59, as wlsunset takes it."""
    if not isinstance(value, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError(f"“{value}” is not a time like 20:00")
    return value


# a hand-edited value that fails its check falls back to the default on load
CHOICE_CHECKS = dict(bar_gif=check_bar_gif, night_mode=check_night_mode, night_temp=check_night_temp,
                    night_start=check_time, night_end=check_time)


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def load(config=CONFIG):
    json_path, _ = paths(config)
    try:
        with open(json_path) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = {}
    s = dict(DEFAULTS)
    if isinstance(saved, dict):
        for k, v in saved.items():
            if k not in DEFAULTS or type(v) is not type(DEFAULTS[k]):
                continue
            check = check_font if k in FONTS else CHOICE_CHECKS.get(k)
            if check:  # a hand-edited value the pages would never offer
                try:
                    v = check(v)
                except ValueError:
                    continue
            s[k] = v
    s["moments"] = dict(s["moments"])  # not DEFAULTS' own dict
    import battery  # local: battery.py imports this module

    try:  # one bad battery value must not block saving the other pages' settings
        battery.valid(s["battery_stop"], s["battery_start"], s["battery_speed"])
    except ValueError:
        s.update({k: DEFAULTS[k] for k in ("battery_stop", "battery_start", "battery_speed")})
    return s


def to_lua(s):
    """The Lua that applies these settings over hyprland.lua's defaults."""
    gaps = GAPS_ON if s["gaps"] else dict(gaps_in=0, gaps_out=0, rounding=0)
    b = lambda v: "true" if v else "false"  # noqa: E731
    return (
        "-- generated by the Settings app (SUPER+I) from user-settings.json: edits here are lost\n"
        "hl.config({\n"
        f"    input = {{ kb_layout = {json.dumps(s['kb_layout'])},\n"
        f"              touchpad = {{ natural_scroll = {b(s['natural_scroll'])},"
        f" tap_to_click = {b(s['tap_to_click'])} }} }},\n"
        f"    general = {{ gaps_in = {gaps['gaps_in']}, gaps_out = {gaps['gaps_out']} }},\n"
        f"    decoration = {{ rounding = {gaps['rounding']} }},\n"
        f"    animations = {{ enabled = {b(s['animations'])} }},\n"
        "})\n"
    )


def save(s, config=CONFIG, symbols=XKB_SYMBOLS):
    """Check and store the settings, then write the Lua (Hyprland reloads by itself)."""
    s = dict(DEFAULTS, **{k: v for k, v in s.items() if k in DEFAULTS})
    s["kb_layout"] = check_layouts(s["kb_layout"], symbols)
    for k in SWITCHES:
        if not isinstance(s[k], bool):
            raise ValueError(f"{k} must be on or off")
    for k in FONTS:
        s[k] = check_font(s[k])
    for k, check in CHOICE_CHECKS.items():
        s[k] = check(s[k])
    import battery  # local: battery.py imports this module, so avoid a cycle at load time

    s["battery_stop"], s["battery_start"], s["battery_speed"] = battery.valid(
        s["battery_stop"], s["battery_start"], s["battery_speed"]
    )
    json_path, lua_path = paths(config)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    for path, text in ((json_path, json.dumps(s, indent=1) + "\n"), (lua_path, to_lua(s))):
        if path == lua_path and _read(path) == text:
            continue  # unchanged: writing it would make Hyprland reload for nothing
        with open(path + ".tmp", "w") as f:
            f.write(text)
        os.replace(path + ".tmp", path)
    return s
