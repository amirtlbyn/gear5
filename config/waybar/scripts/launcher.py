#!/usr/bin/env python3
"""
Search everything (SUPER+D), Everforest style — like Spotlight on macOS or the
Activities search on Ubuntu.

  launcher.py [THEME] [--hidden]

One box finds:
- Apps (the ones you open most come first), and open windows on any desk.
- Actions: Wi-Fi, Bluetooth, sound, lock, suspend, reboot, ... (power actions ask
  for a second Enter).
- Files and folders in your home: by name (plocate + LocalSearch, the GNOME
  indexer) and by what is inside them (LocalSearch).
- Math and conversions ("2^10", "5 km to mi", "20% of 350") with qalc; Enter copies.
- Nothing fits? Search the web, or run what you typed as a command.
With an empty box it shows your most used apps and recent files.
Tabs narrow it down: All · Apps · Windows · Files · Actions (an empty box then lists
everything in that tab, e.g. every app).

Keys: Tab / Shift+Tab (or Alt+1..5) switch tabs · Up/Down (Ctrl+J/K) move · Enter
open · Ctrl+Enter show a file in its folder · Esc clear / close. Clicking anywhere, on any screen, closes it.
Stays running hidden, so it opens instantly.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse

LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if not os.environ.get("LAUNCHER_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["LAUNCHER_PRELOADED"] = "1"
    if lib:
        old = os.environ.get("LD_PRELOAD", "")
        os.environ["LD_PRELOAD"] = lib + (":" + old if old else "")
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LS  # noqa: E402
except (ValueError, ImportError):
    LS = None

import browsers  # noqa: E402
import palette  # noqa: E402

import popup_backdrop  # noqa: E402

THEME = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else palette.current()
WIDTH = 640
LIST_H = 470
TERMINAL = "kitty"
HOME = os.path.expanduser("~")
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
USAGE_FILE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.join(HOME, ".cache")),
                          "launcher", "usage.json")
WEB_SEARCH = "https://www.google.com/search?q="
# how many results each section shows
LIMITS = dict(apps=6, windows=4, actions=4, files=8, folders=4, recent=6, most_used=8)
# folders in your home that are noise, not your files
SKIP_DIRS = ("/.", "/node_modules/", "/__pycache__/", "/site-packages/", "/venv/", "/.venv/",
             "/snap/", "/go/pkg/", "/target/debug/", "/target/release/")

P = palette.load(THEME)

CSS = "".join(f"@define-color {k} {v};\n" for k, v in P.items()) + """
window.launcher { background: transparent; }
.backdrop { background: alpha(black, 0.12); }
.popup {
  background: @bg0; color: @fg;
  border-radius: 22px; border: 1px solid alpha(@fg, 0.07);
  box-shadow: 0 22px 50px @shadow, 0 2px 6px alpha(black, 0.25);
  padding: 14px;
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif; font-weight: bold; font-size: 14px;
}
entry.search {
  background: @bg1; color: @fg; border: none; box-shadow: none; outline: none;
  border-radius: 14px; border-bottom: 3px solid @edge; padding: 4px 12px; min-height: 46px; font-size: 17px;
}
list { background: transparent; }
list > row { border-radius: 14px; padding: 5px 10px; min-height: 0; outline: none; }
list > row.item:hover { background: alpha(@fg, 0.06); }
list > row.item:selected { background: alpha(@green, 0.20); box-shadow: inset 3px 0 0 @green; }
list > row.item:selected .name { color: @green; }
list > row.header { padding: 12px 6px 3px 6px; }
list > row.header:hover { background: transparent; }
.section { color: @grey; font-size: 11px; letter-spacing: 2px; }
.name { font-size: 15px; }
.desc { color: @grey; font-weight: normal; font-size: 12px; }
.kind { color: @grey; font-weight: normal; font-size: 11px; }
.calc .name { font-size: 22px; color: @yellow; }
.confirm .desc { color: @red; }
image.symbolic { color: @fg; }
.empty { color: @grey; font-weight: normal; padding: 26px 10px; }
.hint { color: @grey; font-weight: normal; font-size: 11px; margin: 10px 6px 0 6px; }
.busy { color: @grey; font-weight: normal; font-size: 11px; }
.chips { margin: 10px 0 2px 0; }
.chips button {
  background: @bg1; color: @fg; border: none; box-shadow: none; border-radius: 12px;
  padding: 4px 12px; min-height: 0; font-size: 12px;
}
.chips button:hover { background: @bg2; }
.chips button.active { background: @green; color: @on_accent; }
"""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def load_usage():
    try:
        with open(USAGE_FILE) as f:
            data = json.load(f)
        # older versions saved bare app ids
        return {(k if ":" in k else "app:" + k): v for k, v in data.items()
                if isinstance(v, list) and len(v) == 2}
    except (OSError, ValueError, AttributeError):
        return {}


def save_usage(usage):
    try:
        os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
        with open(USAGE_FILE, "w") as f:
            json.dump(usage, f)
    except OSError:
        pass


def frecency(entry):
    """Opened often and lately = high. Halves for every week since the last time."""
    if not entry:
        return 0.0
    count, last = entry
    weeks = max(0.0, time.time() - last) / (7 * 86400)
    return count * 0.5 ** weeks


def fuzzy(q, text):
    """All letters of q, in order, somewhere in text: None, or a score of 5-20 that is
    higher when the letters start words or follow each other ("gchr" -> Google CHRome)."""
    pos, prev, bonus = 0, -2, 0
    for ch in q:
        pos = text.find(ch, pos)
        if pos < 0:
            return None
        if pos == 0 or not text[pos - 1].isalnum():
            bonus += 3
        elif pos == prev + 1:
            bonus += 2
        prev, pos = pos, pos + 1
    return min(20, 5 + bonus)


def words(text):
    return [w for w in re.split(r"[\s\-_.;,/()]+", text.lower()) if w]


def score_term(t, name, name_words, extra, extra_words):
    if name.startswith(t):
        return 100
    if any(w.startswith(t) for w in name_words):
        return 80
    if t in name:
        return 60
    if any(w.startswith(t) for w in extra_words):
        return 40
    if t in extra:
        return 25
    return fuzzy(t, name) if len(t) >= 2 else None


def score(query, name, name_words, extra="", extra_words=()):
    total = 0
    for t in query:
        s = score_term(t, name, name_words, extra, extra_words)
        if s is None:
            return None
        total += s
    return total


def child_env():
    """What we start must not inherit the layer-shell preload this process runs with."""
    env = dict(os.environ)
    env.pop("LAUNCHER_PRELOADED", None)
    lib = [p for p in env.get("LD_PRELOAD", "").split(":") if p and p not in LAYER_LIBS]
    if lib:
        env["LD_PRELOAD"] = ":".join(lib)
    else:
        env.pop("LD_PRELOAD", None)
    return env


def spawn(argv):
    try:
        subprocess.Popen(argv, env=child_env(), cwd=HOME,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def run(argv, timeout=3):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def pretty_path(path):
    return "~" + path[len(HOME):] if path.startswith(HOME) else path


def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------
class Item:
    """One result row."""

    def __init__(self, key, title, sub="", icon=None, kind="", run=None, reveal=None,
                 confirm=None, css=""):
        self.key, self.title, self.sub, self.icon, self.kind = key, title, sub, icon, kind
        self.run, self.reveal, self.confirm, self.css = run, reveal, confirm, css
        self.armed = False       # power actions: the first Enter only asks


class App:
    def __init__(self, info):
        self.info = info
        self.id = info.get_id() or info.get_name()
        self.title = info.get_display_name() or info.get_name() or self.id
        self.name = self.title.lower()
        self.name_words = words(self.name)
        generic = info.get_generic_name() or ""
        comment = info.get_description() or ""
        self.desc = generic if generic and generic.lower() != self.name else comment
        keywords = " ".join(info.get_keywords() or [])
        exe = os.path.basename(info.get_executable() or "")
        self.extra = " ".join((generic, comment, keywords, exe, self.id.removesuffix(".desktop"))).lower()
        self.extra_words = words(self.extra)
        self.wm_class = (info.get_startup_wm_class() or "").lower()

    def launch(self):
        info = self.info
        if info.get_boolean("Terminal"):
            cmd = re.sub(r"%[a-zA-Z]", "", info.get_commandline() or "").strip()
            if cmd:
                spawn([TERMINAL, "-e", *shlex.split(cmd)])
            return
        path = info.get_filename()
        if path:
            spawn(["gio", "launch", path])

    def item(self):
        return Item("app:" + self.id, self.title, self.desc, self.info.get_icon(), "App", self.launch)


def load_apps():
    apps, seen = [], set()
    for info in Gio.AppInfo.get_all():
        if not isinstance(info, Gio.DesktopAppInfo) or not info.should_show():
            continue
        app = App(info)
        if app.id not in seen:
            seen.add(app.id)
            apps.append(app)
    return apps


def popup(name):
    # after this window is gone, so popup.sh doesn't close the new one right away
    return lambda: GLib.timeout_add(120, lambda: (spawn([os.path.join(SCRIPTS, "popup.sh"), name, THEME]),
                                                  False)[1])


def hypr(lua):
    return lambda: spawn(["hyprctl", "dispatch", lua])


def hypr_eval(lua):
    return lambda: spawn(["hyprctl", "eval", lua])


def sh(cmd):
    return lambda: spawn(["sh", "-c", cmd])


# (title, search words, icon, what it does, needs a second Enter)
ACTIONS = [
    ("Sound", "volume audio speaker headphones microphone output", "audio-volume-high-symbolic",
     popup("volume-popup"), False),
    ("Wi-Fi", "wifi wireless network internet", "network-wireless-symbolic", popup("wifi-menu"), False),
    ("Quick settings", "bluetooth battery power mode brightness screen control center",
     "preferences-system-symbolic", popup("control-center"), False),
    ("Bluetooth", "bluetooth devices headset buds mouse keyboard pair", "bluetooth-active-symbolic",
     popup("control-center"), False),
    ("Calendar", "date time weather persian jalali", "x-office-calendar-symbolic", popup("calendar-popup"), False),
    ("Calculator", "math calc convert units", "accessories-calculator-symbolic", popup("calculator"), False),
    ("Clipboard history", "paste copy clipboard", "edit-paste-symbolic", popup("clipboard"), False),
    ("Emoji", "emoji smiley picker", "face-smile-symbolic", popup("emoji-picker"), False),
    ("World clock", "time zones clock", "preferences-system-time-symbolic", popup("worldclock"), False),
    ("Notifications", "notification center swaync", "preferences-system-notifications-symbolic",
     sh("swaync-client -t -sw"), False),
    ("Screenshot", "screenshot capture area grim", "camera-photo-symbolic",
     sh('sleep 0.3; grim -g "$(slurp)" - | wl-copy'), False),
    ("Lock screen", "lock", "system-lock-screen-symbolic",
     sh("pidof hyprlock || (hyprctl switchxkblayout all 0; hyprlock)"), False),
    ("Suspend", "sleep suspend", "weather-clear-night-symbolic", sh("systemctl suspend"), True),
    ("Log out", "logout exit quit session hyprland", "system-log-out-symbolic", hypr("hl.dsp.exit()"), True),
    ("Restart", "reboot restart", "system-reboot-symbolic", sh("systemctl reboot"), True),
    ("Shut down", "shutdown power off poweroff", "system-shutdown-symbolic", sh("systemctl poweroff"), True),
    ("Reload Hyprland", "reload config hyprland", "view-refresh-symbolic", sh("hyprctl reload"), False),
]


def action_items():
    out = []
    for title, extra, icon, fn, confirm in ACTIONS:
        it = Item("action:" + title, title, "", icon, "Action", fn, confirm=confirm)
        it.name, it.name_words = title.lower(), words(title)
        it.extra, it.extra_words = extra, words(extra)
        out.append(it)
    return out


def launch_action(info, action):
    """An app's own desktop action (e.g. Zen's "New Blank Window")."""
    ctx = Gio.AppLaunchContext()
    env = child_env()
    for var in ("LD_PRELOAD", "LAUNCHER_PRELOADED"):
        if var in env:
            ctx.setenv(var, env[var])
        else:
            ctx.unsetenv(var)
    try:
        info.launch_action(action, ctx)
    except GLib.Error:
        pass


def app_action_item(app, key, title, run):
    it = Item(key, title, app.title, app.info.get_icon(), "Action", run)
    it.name = f"{title} {app.title}".lower()
    it.name_words = words(it.name)
    it.extra, it.extra_words = app.extra, app.extra_words
    return it


def app_action_items(apps):
    """Every app's desktop actions, plus New Tab (and any missing New Window /
    New Private Window) for each web browser."""
    out = []
    for a in apps:
        info = a.info
        own, covered = [], set()
        for act in info.list_actions() or []:
            covered.add(browsers.ACTION_KINDS.get(act))
            own.append(app_action_item(a, f"appaction:{a.id}:{act}", info.get_action_name(act),
                                       lambda i=info, n=act: launch_action(i, n)))
        fam = browsers.family(a.id, info.get_commandline() or "")
        added = []
        for kind in ("tab", "window", "private") if fam else ():
            argv = browsers.command(info.get_commandline() or "", fam, kind)
            if argv and kind not in covered:
                added.append(app_action_item(a, f"appaction:{a.id}:{kind}", browsers.KINDS[fam][kind][0],
                                             lambda v=argv: spawn(v)))
        out += added + own
    return out


def read_windows():
    try:
        clients = json.loads(run(["hyprctl", "-j", "clients"]) or "[]")
    except ValueError:
        return []
    return [c for c in clients if c.get("mapped", True) and c.get("title")]


MINIMIZED = "special:minimized"
MINIMIZED_FILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "hypr-minimized")


def is_minimized(c):
    return (c.get("workspace") or {}).get("name") == MINIMIZED


def minimized_windows(windows):
    """The minimized windows, the last one hidden first (hyprland.lua keeps the order)."""
    try:
        with open(MINIMIZED_FILE) as f:
            order = [line.strip() for line in f if line.strip()]
    except OSError:
        order = []
    rank = {addr: i for i, addr in enumerate(order)}
    return sorted((c for c in windows if is_minimized(c)), key=lambda c: -rank.get(c.get("address"), -1))


# ---- calculator (same idea as calculator.py) -------------------------------
ANSI = re.compile(r"\x1b\[[0-9;]*m")
MATHY = re.compile(r"\d\s*[-+*/^%×÷!]|\d.*\s(to|in)\s+\S|^\s*(sqrt|sin|cos|tan|log|ln|pi)\b|^=")


def calc(expr):
    e = expr.strip().lstrip("=").strip()
    for a, b in (("×", "*"), ("÷", "/"), ("−", "-"), ("π", "pi"), ("√", "sqrt")):
        e = e.replace(a, b)
    e = re.sub(r"([\d.]+)\s*%\s*of\s+", r"(\1/100)*", e, flags=re.I)
    e = re.sub(r"(?<=\S)\s+in\s+(?=[^\s\d]\S*$)", " to ", e)    # "37 C in F" = "37 C to F"
    # "25 C to F" -> degrees, not coulombs and farads
    e = re.sub(r"(?<=[\d\s])([CFcf])(?=\s+(?:to|in)\s)", lambda m: "°" + m.group(1).upper(), e)
    e = re.sub(r"\b(to|in)(\s+)([CFcf])$", lambda m: f"{m.group(1)}{m.group(2)}°{m.group(3).upper()}", e)
    # "5 km to mi" -> one unit (3.1 mi), not "3 mi + 188 yd"
    e = re.sub(r"\b(to|in)\s+(?![-+])([^\s,]+)$", r"\1 -\2", e)
    try:
        r = subprocess.run(["qalc", "-t", e], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = [ANSI.sub("", ln).strip() for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]
    if r.returncode != 0 or not lines or any(ln.lower().startswith("error") for ln in lines):
        return None
    ans = next((ln for ln in reversed(lines) if not ln.lower().startswith("warning")), None)
    if not ans or ans == e:
        return None
    return ans.strip('"')


# ---- files -----------------------------------------------------------------
def wanted(path):
    if not path.startswith(HOME + "/"):
        return False
    rest = path[len(HOME):] + "/"
    return not any(s in rest for s in SKIP_DIRS)


def find_files(query):
    """[(path, is_dir, matched_inside)] best first: plocate + LocalSearch by name,
    then LocalSearch hits that only match the contents."""
    terms = query
    by_name, inside = {}, []

    def plocate():
        out = run(["plocate", "-i", "-b", "-l", "3000", "--", *terms], timeout=3)
        for p in out.splitlines():
            if wanted(p):
                by_name.setdefault(p, None)

    def localsearch():
        for flag in ("-f", "-s"):
            out = run(["localsearch", "search", flag, "-l", "40", *terms], timeout=3)
            for line in out.splitlines():
                line = line.strip()
                if not line.startswith("file://"):
                    continue
                p = urllib.parse.unquote(line[len("file://"):])
                if not wanted(p):
                    continue
                base = os.path.basename(p).lower()
                if all(t in base for t in terms):
                    by_name.setdefault(p, None)
                elif p not in inside:
                    inside.append(p)

    jobs = [threading.Thread(target=f) for f in (plocate, localsearch)]
    for j in jobs:
        j.start()
    for j in jobs:
        j.join()

    def rank(p):
        base = os.path.basename(p).lower()
        stem = base.rsplit(".", 1)[0]
        first = terms[0]
        s = 0 if stem == first else 1 if base.startswith(first) else 2 if any(
            w.startswith(first) for w in words(base)) else 3
        return (s, p.count("/"), len(base))

    results = []
    for p in sorted(by_name, key=rank)[:200]:
        if os.path.exists(p):
            results.append((p, os.path.isdir(p), False))
    for p in inside[:20]:
        if os.path.exists(p) and p not in by_name:
            results.append((p, os.path.isdir(p), True))
    return results


def file_icon(path, is_dir):
    if is_dir:
        return Gio.ThemedIcon.new("folder")
    ctype, _ = Gio.content_type_guess(path, None)
    return Gio.content_type_get_icon(ctype) if ctype else Gio.ThemedIcon.new("text-x-generic")


def open_path(path):
    return lambda: spawn(["gio", "open", path])


def reveal_path(path):
    # the file manager opens the folder with the file selected
    return lambda: spawn(["nemo", path]) if shutil.which("nemo") else spawn(["gio", "open", os.path.dirname(path)])


def file_item(path, is_dir, inside=False, terms=()):
    where = pretty_path(os.path.dirname(path))
    sub = f"contains “{' '.join(terms)}” · {where}" if inside else where
    return Item("file:" + path, os.path.basename(path) or path, sub, file_icon(path, is_dir),
                "Folder" if is_dir else "File", open_path(path), reveal=reveal_path(path))


def recent_files(limit=LIMITS["recent"]):
    items = []
    try:
        infos = Gtk.RecentManager.get_default().get_items()
    except GLib.Error:
        return items
    infos.sort(key=lambda i: i.get_modified().to_unix() if i.get_modified() else 0, reverse=True)
    for info in infos:
        uri = info.get_uri()
        if not uri.startswith("file://"):
            continue
        path = urllib.parse.unquote(uri[len("file://"):])
        if os.path.exists(path):
            items.append(file_item(path, os.path.isdir(path)))
        if len(items) >= limit:
            break
    return items


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
class Launcher(Gtk.Application):
    SCOPES = [("all", "All"), ("apps", "Apps"), ("windows", "Windows"), ("minimized", "Minimized"),
              ("files", "Files"), ("actions", "Actions")]

    def __init__(self):
        super().__init__(application_id="io.local.launcher")
        self.win = None
        self.usage = load_usage()
        self.apps = []
        self.actions = action_items()
        self.windows = []
        self.query = []
        self.text = ""
        self.seq = 0
        self.sections = []           # [(title, [Item])]
        self.async_parts = {}        # "calc" / "files" -> [(title, [Item])] for the current query
        self.rows = []               # selectable rows, top to bottom
        self.scope = "all"           # which tab

    def do_activate(self):
        if self.win is not None:
            if self.win.get_visible():
                self.win.close()
            elif GLib.get_monotonic_time() - getattr(self, "closed_at", 0) > 400_000:
                self.show_popup()
            return
        self.hold()
        self.build()
        self.reload_apps()
        self.monitor = Gio.AppInfoMonitor.get()       # apps installed or removed
        self.monitor.connect("changed", lambda *_: self.reload_apps())
        # popup.sh launcher --minimized: open on the list of minimized windows
        action = Gio.SimpleAction.new("show-minimized", None)
        action.connect("activate", lambda *_: self.show_popup("minimized"))
        self.add_action(action)
        if "--hidden" not in sys.argv:
            self.show_popup("minimized" if "--minimized" in sys.argv else "all")

    def show_popup(self, scope="all"):
        self.search.set_text("")
        self.text, self.query = "", []
        self.set_scope(scope, update=False)
        self.windows = read_windows()
        self.update()
        self.win.present()
        self.search.grab_focus()

    def on_close(self, win):
        self.closed_at = GLib.get_monotonic_time()
        win.set_visible(False)
        return True

    def build(self):
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER)
        win = Gtk.ApplicationWindow(application=self, title="Search")
        win.add_css_class("launcher")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("popup")
        box.set_size_request(WIDTH, -1)

        self.search = Gtk.SearchEntry(placeholder_text="Search apps, files, actions, math…")
        self.search.add_css_class("search")
        self.search.connect("search-changed", lambda *_: self.on_search())
        box.append(self.search)

        chips = Gtk.Box(spacing=6)
        chips.add_css_class("chips")
        self.chip_btns = {}
        for key, name in self.SCOPES:
            b = Gtk.Button(label=name, can_focus=False)
            b.connect("clicked", lambda _b, k=key: self.set_scope(k))
            self.chip_btns[key] = b
            chips.append(b)
        box.append(chips)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE, activate_on_single_click=True)
        self.list.connect("row-activated", lambda _l, row: self.activate(row, reveal=False))
        self.scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                         min_content_height=LIST_H, max_content_height=LIST_H)
        self.scroll.set_child(self.list)
        box.append(self.scroll)

        foot = Gtk.Box(spacing=8)
        foot.append(label("Tab switch tab  ·  ↑↓ move  ·  Enter open  ·  Ctrl+Enter show in folder",
                          "hint", xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END,
                          max_width_chars=1))
        self.busy = label("", "busy hint")
        foot.append(self.busy)
        box.append(foot)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)

        if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
            LS.init_for_window(win)
            LS.set_namespace(win, "launcher")
            LS.set_layer(win, LS.Layer.OVERLAY)
            for edge in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
                LS.set_anchor(win, edge, True)
            LS.set_exclusive_zone(win, -1)
            LS.set_keyboard_mode(win, LS.KeyboardMode.EXCLUSIVE)
            popup_backdrop.attach(win)   # clicks on the other screens close it too
            backdrop = Gtk.Box(hexpand=True, vexpand=True)
            backdrop.add_css_class("backdrop")
            click = Gtk.GestureClick()
            click.connect("pressed", lambda *_: win.close())
            backdrop.add_controller(click)
            box.set_halign(Gtk.Align.CENTER)
            box.set_valign(Gtk.Align.START)
            box.set_margin_top(160)
            overlay = Gtk.Overlay()
            overlay.set_child(backdrop)
            overlay.add_overlay(box)
            win.set_child(overlay)
        else:
            win.set_child(box)
            win.connect("notify::is-active", lambda w, _p: None if w.is_active() else w.close())

    def reload_apps(self):
        self.apps = load_apps()
        self.actions = action_items() + app_action_items(self.apps)
        self.by_class = {}
        for a in self.apps:
            for k in (a.wm_class, a.id.removesuffix(".desktop").lower(),
                      a.id.removesuffix(".desktop").lower().rsplit(".", 1)[-1]):
                if k:
                    self.by_class.setdefault(k, a)
        if self.win and self.win.get_visible():
            self.update()

    # ----- searching ---------------------------------------------------------
    def on_search(self):
        self.seq += 1
        seq = self.seq

        def apply():
            if seq == self.seq:
                self.text = self.search.get_text().strip()
                self.query = self.text.lower().split()
                self.update()
            return False
        GLib.timeout_add(40, apply)

    def boost(self, key):
        return frecency(self.usage.get(key))

    def set_scope(self, key, update=True):
        self.scope = key
        for k, b in self.chip_btns.items():
            (b.add_css_class if k == key else b.remove_css_class)("active")
        if update:
            self.update()
        self.search.grab_focus()

    def limit(self, key):
        # a single tab has room for many more
        return LIMITS[key] * (1 if self.scope == "all" else 6)

    def window_item(self, c):
        title, cls = c.get("title", ""), c.get("class", "")
        app = self.by_class.get(cls.lower())
        icon = app.info.get_icon() if app else Gio.ThemedIcon.new(cls.lower() or "window")
        desk = (c.get("workspace") or {}).get("id", 0)
        addr = c.get("address", "")
        if not re.fullmatch(r"0x[0-9a-f]+", addr):      # it goes into Lua code below
            addr = ""
        if is_minimized(c):
            # comes back onto the desk you're on
            return Item("win:" + addr, title, f"{app.title if app else cls} · minimized", icon,
                        "Window", hypr_eval(f'restoreMinimized("{addr}")'))
        where = f"desk {(desk - 1) % 10 + 1}" if desk >= 1 else "hidden"
        return Item("win:" + addr, title, f"{app.title if app else cls} · {where}", icon,
                    "Window", hypr(f'hl.dsp.focus({{ window = "address:{addr}" }})'))

    def update(self):
        """Fast results now; files and math arrive a moment later."""
        self.seq += 1
        seq, q, text = self.seq, self.query, self.text
        self.async_parts = {}
        scope = self.scope
        for it in self.actions:
            it.armed = False
        if not q:
            ranked = sorted(self.apps, key=lambda a: (-self.boost("app:" + a.id), a.name))
            if scope == "apps":
                self.sections = [("ALL APPS", [a.item() for a in ranked])]
            elif scope == "windows":
                self.sections = [("OPEN WINDOWS", [self.window_item(c) for c in self.windows])]
            elif scope == "minimized":
                mins = [self.window_item(c) for c in minimized_windows(self.windows)]
                self.sections = [("MINIMIZED  ·  newest first", mins) if mins else
                                 ("NOTHING MINIMIZED  ·  SUPER+A hides a window", [])]
            elif scope == "files":
                self.sections = [("RECENT FILES", recent_files(self.limit("recent")))]
            elif scope == "actions":
                self.sections = [("ACTIONS", list(self.actions))]
            else:
                used = [a.item() for a in ranked if self.boost("app:" + a.id) > 0][:LIMITS["most_used"]]
                self.sections = [("MOST USED", used or [a.item() for a in ranked[:LIMITS["most_used"]]]),
                                 ("RECENT FILES", recent_files())]
            self.render()
            return

        apps = []
        for a in self.apps:
            s = score(q, a.name, a.name_words, a.extra, a.extra_words)
            if s is not None:
                apps.append((-s, -self.boost("app:" + a.id), a.name, a))
        apps = [a.item() for *_k, a in sorted(apps, key=lambda x: x[:3])][:self.limit("apps")]

        wins = []
        for c in minimized_windows(self.windows) if scope == "minimized" else self.windows:
            title, cls = c.get("title", ""), c.get("class", "")
            s = score(q, title.lower(), words(title), cls.lower(), words(cls))
            if s is not None:
                wins.append((-s, self.window_item(c)))
        wins = [it for _s, it in sorted(wins, key=lambda x: x[0])][:self.limit("windows")]

        acts = []
        for it in self.actions:
            s = score(q, it.name, it.name_words, it.extra, it.extra_words)
            if s is not None:
                acts.append((-s, -self.boost(it.key), it))
        acts = [it for *_k, it in sorted(acts, key=lambda x: x[:2])][:self.limit("actions")]

        tail = []
        if shutil.which(q[0]) and len(text.split()) and not apps:
            tail.append(Item("run:" + text, f"Run “{text}”", "as a command", "utilities-terminal-symbolic",
                             "Command", lambda: spawn(["sh", "-c", text])))
        tail.append(Item("web:" + text, f"Search the web for “{text}”", "Google",
                         "web-browser-symbolic", "Web",
                         lambda: spawn(["xdg-open", WEB_SEARCH + urllib.parse.quote(text)])))

        pick = dict(all=[("APPS", apps), ("WINDOWS", wins), ("ACTIONS", acts)], apps=[("APPS", apps)],
                    windows=[("WINDOWS", wins)], minimized=[("MINIMIZED", wins)], actions=[("ACTIONS", acts)],
                    files=[])[scope]
        # the web / command row only in "All"; the list always ends with it (maybe empty)
        self.sections = pick + [("", tail if scope == "all" else [])]
        self.render()

        if scope in ("all", "files"):
            self.busy.set_label("searching files…")
            threading.Thread(target=self.search_files, args=(seq, q), daemon=True).start()
        if scope == "all" and MATHY.search(text):
            threading.Thread(target=self.search_calc, args=(seq, text), daemon=True).start()

    def search_files(self, seq, q):
        found = find_files(q)
        if seq != self.seq:
            return
        files = [file_item(p, d, inside, q) for p, d, inside in found if not d]
        folders = [file_item(p, d, inside, q) for p, d, inside in found if d]
        files.sort(key=lambda it: -self.boost(it.key))            # stable: keeps name ranking
        folders.sort(key=lambda it: -self.boost(it.key))

        def done():
            if seq == self.seq:
                self.async_parts["files"] = [("FILES", files[:self.limit("files")]),
                                             ("FOLDERS", folders[:self.limit("folders")])]
                self.busy.set_label("")
                self.render()
            return False
        GLib.idle_add(done)

    def search_calc(self, seq, text):
        ans = calc(text)
        if seq != self.seq or not ans:
            return

        def copy():
            spawn(["wl-copy", "--", ans.split("=")[-1].strip()])

        def done():
            if seq == self.seq:
                self.async_parts["calc"] = [("CALCULATOR", [Item("calc:" + text, ans, f"{text}  ·  Enter copies",
                                                                 "accessories-calculator-symbolic", "Math",
                                                                 copy, css="calc")])]
                self.render()
            return False
        GLib.idle_add(done)

    # ----- list --------------------------------------------------------------
    def all_sections(self):
        parts = list(self.async_parts.get("calc", []))
        # the web / command row stays last
        parts += self.sections[:-1] if self.query else self.sections
        parts += self.async_parts.get("files", [])
        if self.query:
            parts.append(self.sections[-1])
        return parts

    def render(self):
        selected = self.list.get_selected_row()
        keep = selected.item.key if selected is not None and hasattr(selected, "item") else None
        at_top = selected is None or (self.rows and selected is self.rows[0])
        while (row := self.list.get_first_child()) is not None:
            self.list.remove(row)
        self.rows = []
        for title, items in self.all_sections():
            if not items:
                continue
            if title:
                head = Gtk.ListBoxRow(selectable=False, activatable=False)
                head.add_css_class("header")
                head.set_child(label(title, "section", xalign=0))
                self.list.append(head)
            for it in items:
                row = self.make_row(it)
                self.list.append(row)
                self.rows.append(row)
        if not self.rows:
            self.list.append(Gtk.ListBoxRow(selectable=False, activatable=False,
                                            child=label("Nothing found", "empty")))
            return
        # keep what you picked with the arrows; otherwise the best hit
        target = self.rows[0]
        if keep and not at_top:
            target = next((r for r in self.rows if r.item.key == keep), target)
        self.select(target)

    def make_row(self, it):
        row = Gtk.ListBoxRow()
        row.item = it
        row.add_css_class("item")
        if it.css:
            row.add_css_class(it.css)
        box = Gtk.Box(spacing=14)
        img = Gtk.Image(pixel_size=32)
        if isinstance(it.icon, Gio.Icon):
            img.set_from_gicon(it.icon)
        else:
            img.set_from_icon_name(it.icon or "application-x-executable")
            if it.icon and it.icon.endswith("-symbolic"):
                img.set_pixel_size(24)
                img.set_size_request(32, 32)
                img.add_css_class("symbolic")
        box.append(img)
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        txt.append(label(it.title, "name", xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=1))
        row.desc = label(it.sub, "desc", xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=1)
        row.desc.set_visible(bool(it.sub))
        txt.append(row.desc)
        box.append(txt)
        if it.kind:
            box.append(label(it.kind, "kind", valign=Gtk.Align.CENTER))
        row.set_child(box)
        return row

    def select(self, row):
        self.list.select_row(row)
        if row is None:
            return
        # keep it in view without taking the keyboard away from the search box
        adj = self.scroll.get_vadjustment()
        if row is self.rows[0]:
            adj.set_value(0)
            return
        ok, bounds = row.compute_bounds(self.list)
        if ok:
            y, h = bounds.get_y(), bounds.get_height()
            if y < adj.get_value():
                adj.set_value(y)
            elif y + h > adj.get_value() + adj.get_page_size():
                adj.set_value(y + h - adj.get_page_size())

    def move(self, step):
        if not self.rows:
            return
        cur = self.list.get_selected_row()
        i = self.rows.index(cur) if cur in self.rows else -1
        self.select(self.rows[max(0, min(len(self.rows) - 1, i + step))])

    # ----- opening -----------------------------------------------------------
    def activate(self, row, reveal):
        it = getattr(row, "item", None)
        if it is None:
            return
        if it.confirm and not it.armed:
            it.armed = True
            row.add_css_class("confirm")
            row.desc.set_label(f"Press Enter again to {it.title.lower()}")
            row.desc.set_visible(True)
            return
        entry = self.usage.get(it.key) or [0, 0]
        if not it.key.startswith(("web:", "run:", "calc:", "win:")):
            self.usage[it.key] = [frecency(entry) + 1, time.time()]
            save_usage(self.usage)
        self.win.close()
        (it.reveal if reveal and it.reveal else it.run)()

    # ----- keys --------------------------------------------------------------
    def on_key(self, _ctl, keyval, _code, state):
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if keyval == Gdk.KEY_Escape:
            if self.search.get_text():      # first Esc clears, the next one closes
                self.search.set_text("")
            else:
                self.win.close()
            return True
        # Tab / Shift+Tab: next / previous tab; Alt+1..6: straight to one
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            keys = [k for k, _ in self.SCOPES]
            step = -1 if keyval == Gdk.KEY_ISO_Left_Tab or state & Gdk.ModifierType.SHIFT_MASK else 1
            self.set_scope(keys[(keys.index(self.scope) + step) % len(keys)])
            return True
        if state & Gdk.ModifierType.ALT_MASK and Gdk.KEY_1 <= keyval < Gdk.KEY_1 + len(self.SCOPES):
            self.set_scope(self.SCOPES[keyval - Gdk.KEY_1][0])
            return True
        if keyval == Gdk.KEY_Down or (ctrl and keyval in (Gdk.KEY_j, Gdk.KEY_n)):
            self.move(1)
            return True
        if keyval == Gdk.KEY_Up or (ctrl and keyval in (Gdk.KEY_k, Gdk.KEY_p)):
            self.move(-1)
            return True
        if keyval == Gdk.KEY_Page_Down:
            self.move(6)
            return True
        if keyval == Gdk.KEY_Page_Up:
            self.move(-6)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.seq and self.text != self.search.get_text().strip():
                # typed faster than the search: search now, then open the best hit
                self.text = self.search.get_text().strip()
                self.query = self.text.lower().split()
                self.update()
            row = self.list.get_selected_row()
            if row is not None:
                self.activate(row, reveal=bool(ctrl))
            return True
        if not self.search.has_focus():
            self.search.grab_focus()
        return False


if __name__ == "__main__":
    sys.exit(Launcher().run([sys.argv[0]]))
