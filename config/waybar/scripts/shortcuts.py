"""
The shortcuts the Settings app lets you change. No GTK, so tests can load it.

hyprland.lua owns the list: every `shortcut("group.word", "Label", keys, action)` line is
one shortcut. This module reads those lines, builds Hyprland's key text from a key press,
and checks keys against the other shortcuts and the binds Hyprland has now.

    import shortcuts
    shortcuts.catalog(path)                       # [(name, label, group, default_keys), ...]
    shortcuts.keys_text(["SUPER", "SHIFT"], "w")  # "SUPER + SHIFT + W"
    shortcuts.conflict(keys, name, current, shortcuts.live_binds())  # None, or why not
"""

import json
import os
import re
import subprocess

HYPRLAND_LUA = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "hypr", "hyprland.lua")
# the order Hyprland's own docs list them in, and their bits in a bind's modmask
MODIFIERS = {"SUPER": 64, "CTRL": 4, "ALT": 8, "SHIFT": 1}
SHORTCUT_LINE = re.compile(r'^shortcut\("([a-z]+\.[a-z_]+)", "([^"]*)", (mainMod \.\. )?"([^"]*)",', re.M)
NEEDS_MODIFIER = "needs SUPER, ALT, CTRL or SHIFT"


def catalog(path=HYPRLAND_LUA):
    """[(name, label, group, default_keys)] from the shortcut lines of hyprland.lua, in file order."""
    with open(path) as f:
        text = f.read()
    found = re.search(r'^local mainMod\s*=\s*"(\w+)"', text, re.M)
    main = found.group(1) if found else "SUPER"
    return [
        (name, label, name.split(".")[0], (main if uses_main else "") + keys)
        for name, label, uses_main, keys in SHORTCUT_LINE.findall(text)
    ]


def keys_text(mods, keyname):
    """Hyprland's text for a key press: modifier names and a key name -> "SUPER + SHIFT + W"."""
    names = [m for m in MODIFIERS if m in mods]
    key = keyname.upper() if len(keyname) == 1 else keyname
    return " + ".join(names + [key])


def keys_label(keys):
    """What a shortcut's key button says: its keys, or "Off" for none (KEYS-4)."""
    return keys or "Off"


def _split(keys):
    """"SUPER + W" -> (modmask, "w"): the same keys give the same pair, however they are written."""
    *mods, key = [part.strip() for part in keys.split("+")]
    return sum(MODIFIERS.get(m.upper(), 0) for m in mods), key.lower()


def _describe(modmask, key):
    return keys_text([m for m, bit in MODIFIERS.items() if modmask & bit], key)


def conflict(keys, name, current, live_binds):
    """Why `keys` cannot be the keys of shortcut `name`, or None when they can.
    `current` lists every shortcut as (name, label, keys) with its keys now ("" is off);
    `live_binds` is Hyprland's bind list (live_binds())."""
    modmask, key = _split(keys)
    if not modmask and not re.fullmatch(r"f\d{1,2}|print", key):
        return NEEDS_MODIFIER
    for other, label, other_keys in current:
        if other != name and other_keys and _split(other_keys) == (modmask, key):
            return f"already used by “{label}”"
    known = {other for other, _, _ in current}
    for bind in live_binds:
        owner = str(bind.get("description", "")).split("|")[0]
        if owner not in known and (bind.get("modmask"), str(bind.get("key", "")).lower()) == (modmask, key):
            return f"already used by another desktop key ({_describe(modmask, bind['key'])})"
    return None


def live_binds():
    """The binds Hyprland has now (`hyprctl binds -j`); [] when it cannot say."""
    try:
        done = subprocess.run(["hyprctl", "binds", "-j"], capture_output=True, text=True, timeout=3, check=True)
        binds = json.loads(done.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return [b for b in binds if isinstance(b, dict)] if isinstance(binds, list) else []
