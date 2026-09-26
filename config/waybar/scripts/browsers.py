"""
What the launcher needs to know about web browsers: which family a browser is, and
the command that opens a new tab, window or private window in it (in the running
browser when there is one).

    fam = family("app.zen_browser.zen.desktop", "flatpak run ... app.zen_browser.zen @@u %u @@")
    argv = command("flatpak run ... @@u %u @@", fam, "tab")
"""

import re
import shlex

FIREFOX = ("firefox", "zen", "librewolf", "floorp", "waterfox", "mullvad", "icecat", "torbrowser")
CHROMIUM = ("chrome", "chromium", "brave", "vivaldi", "edge", "opera", "thorium", "helium", "cromite")

# kind -> (label, extra arguments) per family
KINDS = {
    "firefox": {
        "tab": ("New Tab", ["--new-tab", "about:newtab"]),
        "window": ("New Window", ["--new-window"]),
        "private": ("New Private Window", ["--private-window"]),
    },
    "chromium": {
        "tab": ("New Tab", ["chrome://newtab/"]),
        "window": ("New Window", ["--new-window"]),
        "private": ("New Private Window", ["--incognito"]),
    },
}
# desktop-file actions that already do one of these (then the launcher doesn't add its own)
ACTION_KINDS = {"new-window": "window", "new-private-window": "private", "new-incognito-window": "private"}


def family(app_id, commandline=""):
    """ "firefox", "chromium" or None, from the desktop id and the command."""
    if any(a.startswith(("--app-id", "--app=")) for a in split(commandline)):
        return None  # a web app (e.g. a site installed from Chrome), not the browser
    argv = split(commandline)
    program = argv[0].rsplit("/", 1)[-1] if argv else ""
    # the desktop id and the program name only: arguments can say anything
    words = re.split(r"[^a-z0-9]+", f"{app_id} {program}".lower())
    # whole words: "zen" in app.zen_browser.zen, but not in "zenity"
    if any(w in FIREFOX for w in words):
        return "firefox"
    if any(w in CHROMIUM for w in words):
        return "chromium"
    return None


def split(commandline):
    try:
        return shlex.split(commandline or "")
    except ValueError:
        return []


def base(commandline):
    """The desktop file's command without its placeholders (%u, %U, ..., flatpak's @@u ... @@)."""
    return [a for a in split(commandline) if not re.fullmatch(r"%[a-zA-Z]|@@[a-z]?", a)]


def command(commandline, fam, kind):
    """argv that opens a new tab / window / private window, or None."""
    argv = base(commandline)
    if not argv or fam not in KINDS or kind not in KINDS[fam]:
        return None
    if fam == "chromium" and "edge" in argv[0]:
        extra = ["--inprivate"] if kind == "private" else KINDS[fam][kind][1]
    else:
        extra = KINDS[fam][kind][1]
    return argv + extra
