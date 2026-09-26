#!/usr/bin/env python3
"""
Settings (SUPER+I, or the button in the control center), in the theme's colors.

  settings.py [theme|wallpaper|system|input]     open on that page

- Theme: pick a Straw Hat (or Summer night); everything switches at once.
- Wallpaper: an image per theme, copied into ~/.config/hypr/wallpapers/.
- System: opens the Displays, Wi-Fi, Sound, ... popups.
- Input & behavior: keyboard layouts, touchpad, gaps, animations, sleep timer.
  Kept in ~/.config/hypr/user-settings.json (see settings_store.py).

A normal window, not a popup: the file chooser has to be able to open over it.
"""
import os
import shutil
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
try:
    gi.require_version("Gtk4LayerShell", "1.0")  # popup_backdrop imports it
except ValueError:
    pass
import palette  # noqa: E402
import popup_backdrop  # noqa: E402
import settings_store as store  # noqa: E402
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
THEME_PY = os.path.join(SCRIPTS, "theme.py")
POPUP = os.path.join(SCRIPTS, "popup.sh")
IDLE = os.path.expanduser("~/.config/hypr/scripts/idle.sh")
PAGES = [
    ("theme", "\U000f03d8", "Theme"),
    ("wallpaper", "\U000f02e9", "Wallpaper"),
    ("system", "\U000f0493", "System"),
    ("input", "\U000f030c", "Input & behavior"),
]
SYSTEM = [  # (popup, icon, name, what it does)
    ("displays", "\U000f0379", "Displays", "Arrange, resolution, scale, rotation"),
    ("wifi-menu", "\U000f05a9", "Wi-Fi", "Networks and passwords"),
    ("volume-popup", "\U000f057e", "Sound", "Speakers, microphone, apps"),
    ("control-center", "\U000f00af", "Bluetooth & quick settings", "Devices, brightness, battery mode"),
    ("power-popup", "\U000f0425", "Power & sleep", "Lock, sleep, restart, power off"),
    ("clipboard", "\U000f0147", "Clipboard", "Everything you copied"),
    ("emoji-picker", "\U000f0785", "Emoji", "Search and paste emoji"),
    ("notifications", "\U000f009a", "Notifications", "The notification center"),
]
IDLE_MODES = [("sleep", "Lock, then sleep"), ("lock", "Lock only"), ("awake", "Stay awake")]
IDLE_MINUTES = [1, 2, 5, 10, 15, 30, 60]
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp")

CSS = """
window.settings { background: @bg_dim; color: @fg; }
window.settings * { font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif; }
.side { background: @bg0; padding: 16px 10px; border-right: 1px solid alpha(@fg, 0.06); }
.side .app-title { font-size: 18px; font-weight: 800; margin: 2px 10px 14px 10px; }
.side button { background: transparent; color: @fg; border: none; box-shadow: none; border-radius: 12px;
               padding: 9px 12px; font-weight: bold; }
.side button:hover { background: @bg1; }
.side button.active { background: @green; color: @on_accent; }
.page { padding: 22px 26px; }
.page-title { font-size: 22px; font-weight: 800; }
.page-sub { color: @grey; font-size: 12.5px; margin-bottom: 16px; }
.section { color: @grey; font-size: 11px; font-weight: bold; letter-spacing: 2px; margin: 18px 2px 8px 2px; }
button.card { background: @bg0; color: @fg; border: none; box-shadow: none; border-radius: 16px;
              border-bottom: 4px solid @edge_deep; padding: 10px; }
button.card:hover { background: @bg1; }
button.card.current { box-shadow: inset 0 0 0 2px @green; }
.card .name { font-weight: 800; font-size: 14px; }
.card .char { color: @grey; font-size: 11px; }
.card .badge { color: @green; font-size: 11px; font-weight: bold; }
.row { background: @bg0; border-radius: 14px; border-bottom: 3px solid @edge_deep; padding: 10px 14px; }
.row .title { font-weight: bold; }
.row .desc { color: @grey; font-size: 11.5px; }
.row .error, .page .error { color: @red; font-size: 11.5px; }
.thumb { border-radius: 10px; }
.plain { border-radius: 10px; color: @grey; font-size: 10px; }
button.act { background: @bg2; color: @fg; border: none; box-shadow: none; border-radius: 12px;
             border-bottom: 3px solid @edge_deep; padding: 6px 14px; font-weight: bold; }
button.act:hover { background: @bg3; }
button.act.primary { background: @green; color: @on_accent; border-bottom-color: @green_edge; }
button.act:disabled { opacity: 0.4; }
button.tile { background: @bg0; color: @fg; border: none; box-shadow: none; border-radius: 16px;
              border-bottom: 4px solid @edge_deep; padding: 14px; }
button.tile:hover { background: @bg1; }
.tile .icon { font-size: 26px; color: @green; }
.tile .name { font-weight: 800; }
.tile .desc { color: @grey; font-size: 11px; }
entry { background: @bg2; color: @fg; border: none; border-radius: 10px; min-height: 32px; }
switch { background: @bg3; border: none; }
switch:checked { background: @green; }
switch slider { background: @fg; border: none; box-shadow: none; }
dropdown > button { background: @bg2; color: @fg; border: none; border-radius: 10px; box-shadow: none; }
popover > contents { background: @bg1; color: @fg; border-radius: 12px; }
scrollbar { background: transparent; }
"""


def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


def spawn(argv):
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def in_background(work, done=None):
    """Run work() off the UI thread; done(result) runs on it after (result is the
    exception if work() failed)."""

    def target():
        try:
            result = work()
        except Exception as e:  # noqa: BLE001 - handed to done(), never lost
            result = e
        if done:
            GLib.idle_add(lambda: (done(result), False)[1])

    threading.Thread(target=target, daemon=True).start()


def swatch(colors, names=("bg0", "fg", "green", "blue", "red", "yellow")):
    """A strip of a theme's main colors."""
    area = Gtk.DrawingArea(content_height=34, hexpand=True)

    def draw(_a, cr, w, h):
        step = w / len(names)
        for i, n in enumerate(names):
            rgba = Gdk.RGBA()
            rgba.parse(colors.get(n, "#000000"))
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
            cr.rectangle(i * step, 0, step + 1, h)
            cr.fill()

    area.set_draw_func(draw)
    area.set_overflow(Gtk.Overflow.HIDDEN)
    area.add_css_class("thumb")
    return area


class Settings(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.local.settings", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win = None
        self.provider = None
        self.page = "theme"
        self.busy = False  # a theme switch or wallpaper copy is running

    # ----- lifecycle -----------------------------------------------------------
    def do_command_line(self, cmd):
        args = cmd.get_arguments()[1:]
        page = next((a for a in args if a in {p for p, _i, _n in PAGES}), None)
        if self.win is None:
            self.hold()
            self.build()
        if page:
            self.show_page(page)
        if "--hidden" not in args:  # --hidden: start in the background (tests)
            self.win.present()
        return 0

    def apply_css(self):
        if self.provider is None:
            self.provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
        colors = palette.load()
        self.provider.load_from_string("".join(f"@define-color {k} {v};\n" for k, v in colors.items()) + CSS)

    def build(self):
        popup_backdrop.smooth_text()
        self.apply_css()
        win = Gtk.ApplicationWindow(application=self, title="Settings", default_width=860, default_height=640)
        win.add_css_class("settings")
        win.connect("close-request", self.on_close)
        self.win = win

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        side.add_css_class("side")
        side.set_size_request(210, -1)
        side.append(label("\U000f0493  Settings", "app-title", xalign=0))
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)
        self.side_btns = {}
        for key, icon, name in PAGES:
            b = Gtk.Button(label=f"{icon}   {name}")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, k=key: self.show_page(k))
            side.append(b)
            self.side_btns[key] = b
        self.pages = dict(
            theme=self.theme_page,
            wallpaper=self.wallpaper_page,
            system=self.system_page,
            input=self.input_page,
        )
        for key, _icon, _name in PAGES:
            self.stack.add_named(self.scrolled(self.pages[key]()), key)

        body = Gtk.Box()
        body.append(side)
        body.append(self.stack)
        win.set_child(body)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)
        self.show_page(self.page)

    def scrolled(self, child):
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        sw.set_child(child)
        return sw

    def rebuild(self, key):
        """Draw a page again (after a theme or wallpaper change)."""
        old = self.stack.get_child_by_name(key)
        self.stack.remove(old)
        self.stack.add_named(self.scrolled(self.pages[key]()), key)
        if self.page == key:
            self.stack.set_visible_child_name(key)

    def show_page(self, key):
        self.page = key
        self.stack.set_visible_child_name(key)
        for k, b in self.side_btns.items():
            (b.add_css_class if k == key else b.remove_css_class)("active")

    def on_close(self, win):
        win.set_visible(False)
        return True

    def on_key(self, _ctl, keyval, _code, state):
        if keyval == Gdk.KEY_Escape or (state & Gdk.ModifierType.CONTROL_MASK and keyval == Gdk.KEY_w):
            self.win.close()
            return True
        return False

    def page_box(self, title, sub):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("page")
        box.append(label(title, "page-title", xalign=0))
        box.append(label(sub, "page-sub", xalign=0, wrap=True))
        return box

    # ----- theme -------------------------------------------------------------------
    def theme_page(self):
        box = self.page_box(
            "Theme",
            "Pick a character. The bar, popups, notifications, window borders, "
            "lock screen and wallpaper all switch together.",
        )
        current = palette.current()
        flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            max_children_per_line=3,
            min_children_per_line=2,
            column_spacing=12,
            row_spacing=12,
        )
        for tid, name, character in palette.available():
            colors = palette.load(tid)
            b = Gtk.Button(can_focus=True)
            b.add_css_class("card")
            if tid == current:
                b.add_css_class("current")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            inner.append(swatch(colors))
            top = Gtk.Box(spacing=6)
            top.append(label(name, "name", xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
            if tid == current:
                top.append(label("in use", "badge"))
            inner.append(top)
            inner.append(
                label(
                    character or "The original Everforest look",
                    "char",
                    xalign=0,
                    ellipsize=Pango.EllipsizeMode.END,
                )
            )
            b.set_child(inner)
            b.connect("clicked", lambda _b, t=tid: self.pick_theme(t))
            flow.append(b)
        box.append(flow)
        return box

    def pick_theme(self, tid):
        if self.busy or tid == palette.current():
            return  # one switch at a time: the last click must be the theme you get
        self.busy = True

        def done(_r):
            self.busy = False
            self.apply_css()
            self.rebuild("theme")
            self.rebuild("wallpaper")

        in_background(lambda: subprocess.run([THEME_PY, "apply", tid], capture_output=True, timeout=20), done)

    # ----- wallpaper -----------------------------------------------------------------
    def wallpaper_page(self):
        box = self.page_box(
            "Wallpaper",
            "One picture per theme. Use images you may use (fan art: check the "
            "artist's terms). With none, the desktop is the theme's color.",
        )
        current = palette.current()
        if getattr(self, "wall_error", None):
            box.append(label(self.wall_error, "error", xalign=0, wrap=True))
            self.wall_error = None
        for tid, name, _character in palette.available():
            path = palette.wallpaper(tid)
            row = Gtk.Box(spacing=14)
            row.add_css_class("row")
            if path:
                pic = Gtk.Picture.new_for_filename(path)
                pic.set_content_fit(Gtk.ContentFit.COVER)
                pic.set_size_request(128, 72)
                pic.set_overflow(Gtk.Overflow.HIDDEN)
                pic.add_css_class("thumb")
                row.append(pic)
            else:
                plain = swatch(palette.load(tid), names=("bg0",))
                plain.set_size_request(128, 72)
                plain.set_hexpand(False)
                row.append(plain)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
            text.append(label(name + ("  ·  in use" if tid == current else ""), "title", xalign=0))
            text.append(
                label(
                    os.path.basename(path) if path else "Plain color",
                    "desc",
                    xalign=0,
                    ellipsize=Pango.EllipsizeMode.MIDDLE,
                )
            )
            row.append(text)
            choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
            choose.add_css_class("act")
            choose.connect("clicked", lambda _b, t=tid: self.choose_wallpaper(t))
            remove = Gtk.Button(label="Remove", valign=Gtk.Align.CENTER, sensitive=bool(path))
            remove.add_css_class("act")
            remove.connect("clicked", lambda _b, t=tid: self.set_wallpaper(t, None))
            row.append(choose)
            row.append(remove)
            box.append(row)
        return box

    def choose_wallpaper(self, tid):
        images = Gtk.FileFilter(name="Images (PNG, JPEG, WebP)")
        for mime in IMAGE_TYPES:
            images.add_mime_type(mime)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(images)
        dialog = Gtk.FileDialog(title="Wallpaper for " + tid, filters=filters, default_filter=images)
        pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        if pictures and os.path.isdir(pictures):
            dialog.set_initial_folder(Gio.File.new_for_path(pictures))

        def picked(d, result):
            try:
                f = d.open_finish(result)
            except GLib.Error:
                return  # cancelled
            if f and f.get_path():
                self.set_wallpaper(tid, f.get_path())

        dialog.open(self.win, None, picked)

    def set_wallpaper(self, tid, source):
        """Copy source in as the theme's wallpaper (None removes it)."""
        ext = os.path.splitext(source)[1].lower() if source else ""
        if self.busy or (source and ext not in palette.WALLPAPER_EXTS):
            return
        self.busy = True

        def work():
            os.makedirs(palette.WALLPAPERS, exist_ok=True)
            new = os.path.join(palette.WALLPAPERS, tid + ext)
            if source:  # copy first: a failed copy keeps the old wallpaper
                shutil.copyfile(source, new + ".part")
            for e in palette.WALLPAPER_EXTS:  # one picture per theme
                old = os.path.join(palette.WALLPAPERS, tid + e)
                if os.path.exists(old):
                    os.remove(old)
            if source:
                os.replace(new + ".part", new)
            if tid == palette.current():  # show it now
                subprocess.run([THEME_PY, "apply", tid], capture_output=True, timeout=20)

        def done(result):
            self.busy = False
            if isinstance(result, Exception):
                try:
                    os.remove(os.path.join(palette.WALLPAPERS, tid + ext + ".part"))
                except OSError:
                    pass
                self.wall_error = f"Couldn't use that picture: {result}"
            self.rebuild("wallpaper")

        in_background(work, done)

    # ----- system -----------------------------------------------------------------------
    def system_page(self):
        box = self.page_box("System", "Opens the same panels as the bar.")
        flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            max_children_per_line=3,
            min_children_per_line=2,
            column_spacing=12,
            row_spacing=12,
        )
        for key, icon, name, desc in SYSTEM:
            b = Gtk.Button()
            b.add_css_class("tile")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            inner.append(label(icon, "icon", xalign=0))
            inner.append(label(name, "name", xalign=0))
            inner.append(label(desc, "desc", xalign=0, wrap=True))
            b.set_child(inner)
            b.connect("clicked", lambda _b, k=key: self.open_panel(k))
            flow.append(b)
        box.append(flow)
        return box

    def open_panel(self, key):
        if key == "notifications":
            spawn(["swaync-client", "-t", "-sw"])
        else:
            spawn([POPUP, key])

    # ----- input & behavior ----------------------------------------------------------------
    def input_page(self):
        box = self.page_box(
            "Input & behavior",
            "Saved in ~/.config/hypr/user-settings.json and applied "
            "at once (the bar blinks while Hyprland reloads).",
        )
        s = store.load()
        self.error = None

        box.append(label("KEYBOARD", "section", xalign=0))
        row, text = self.row(
            "Keyboard layouts",
            "In switching order, separated by commas. " "Alt+Shift or SUPER+Space switches.",
        )
        entry = Gtk.Entry(text=s["kb_layout"], valign=Gtk.Align.CENTER, width_chars=12)
        apply_btn = Gtk.Button(label="Apply", valign=Gtk.Align.CENTER)
        apply_btn.add_css_class("act")
        apply_btn.add_css_class("primary")
        self.error = label("", "error", xalign=0, wrap=True, visible=False)
        text.append(self.error)
        apply_btn.connect("clicked", lambda *_: self.save(kb_layout=entry.get_text()))
        entry.connect("activate", lambda *_: self.save(kb_layout=entry.get_text()))
        row.append(entry)
        row.append(apply_btn)
        box.append(row)

        box.append(label("TOUCHPAD", "section", xalign=0))
        box.append(
            self.switch_row("Natural scrolling", "Content moves with your fingers.", s, "natural_scroll")
        )
        box.append(self.switch_row("Tap to click", "A light tap is a click.", s, "tap_to_click"))

        box.append(label("LOOK", "section", xalign=0))
        box.append(
            self.switch_row(
                "Gaps and rounded corners",
                "Space between windows (SUPER+H hides it " "until the next reload).",
                s,
                "gaps",
            )
        )
        box.append(self.switch_row("Animations", "Windows and desks slide and fade.", s, "animations"))

        box.append(label("SLEEP TIMER", "section", xalign=0))
        mode, minutes = self.idle_state()
        row, _text = self.row("When I'm away", "What happens after the time below with no input.")
        dd_mode = Gtk.DropDown.new_from_strings([n for _m, n in IDLE_MODES])
        dd_mode.set_selected(next((i for i, (m, _n) in enumerate(IDLE_MODES) if m == mode), 0))
        dd_min = Gtk.DropDown.new_from_strings([f"{m} min" if m < 60 else "1 hour" for m in IDLE_MINUTES])
        dd_min.set_selected(IDLE_MINUTES.index(minutes) if minutes in IDLE_MINUTES else 2)
        dd_min.set_sensitive(mode != "awake")

        def idle_changed(*_):
            m = IDLE_MODES[dd_mode.get_selected()][0]
            dd_min.set_sensitive(m != "awake")
            spawn([IDLE, "set", m, str(IDLE_MINUTES[dd_min.get_selected()])])

        for dd in (dd_mode, dd_min):
            dd.set_valign(Gtk.Align.CENTER)
            dd.connect("notify::selected", idle_changed)
            row.append(dd)
        box.append(row)
        return box

    def row(self, title, desc):
        row = Gtk.Box(spacing=12)
        row.add_css_class("row")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text.append(label(title, "title", xalign=0))
        text.append(label(desc, "desc", xalign=0, wrap=True))
        row.append(text)
        return row, text

    def switch_row(self, title, desc, s, key):
        row, _text = self.row(title, desc)
        sw = Gtk.Switch(active=s[key], valign=Gtk.Align.CENTER)
        sw.connect("notify::active", lambda w, _p: self.save(**{key: w.get_active()}))
        row.append(sw)
        return row

    def save(self, **changes):
        # Hyprland reloads by itself when user-settings.lua changes, but only watches
        # it once it has loaded it: the first time, ask for the reload
        first = not os.path.exists(store.paths()[1])
        try:
            store.save(dict(store.load(), **changes))
        except (ValueError, OSError) as e:
            self.error.set_label(str(e))
            self.error.set_visible(True)
            return
        self.error.set_visible(False)
        if first:
            spawn(["hyprctl", "reload"])

    @staticmethod
    def idle_state():
        try:
            mode, minutes = subprocess.run(
                [IDLE, "get"], capture_output=True, text=True, timeout=3
            ).stdout.split()[:2]
            return mode, int(minutes)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return "sleep", 5


if __name__ == "__main__":
    sys.exit(Settings().run(sys.argv))
