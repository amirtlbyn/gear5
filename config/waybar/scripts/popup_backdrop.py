"""
Shared by every popup: close it when you click on ANY screen, not only its own.

A popup is a full-screen layer on the screen you opened it on, so a click on another
screen used to go straight to the window there and leave the popup open. While a
popup is shown, this puts a transparent click-catcher on every other screen too.

It also turns off font hinting (see smooth_text), and gives each popup a "close-popup" action and marks it as open in
$XDG_RUNTIME_DIR/popups, so `popup.sh --close-all` can close whatever is open (used
when you switch desks, open a window, or open another popup).

    import popup_backdrop
    popup_backdrop.attach(win)      # right after the popup's layer-shell set-up
"""
import json
import os
import subprocess

from gi.repository import Gio, Gtk

try:
    from gi.repository import Gtk4LayerShell as LS
except ImportError:
    LS = None

MARKS = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "popups")
CSS = "window.popup-catcher { background: alpha(black, 0.12); }"


def focused_output():
    try:
        mons = json.loads(subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True,
                                         text=True, timeout=2).stdout)
        return next(m["name"] for m in mons if m.get("focused"))
    except (OSError, ValueError, StopIteration, KeyError, subprocess.TimeoutExpired):
        return None


class Catchers:
    def __init__(self, win):
        self.win = win
        self.windows = {}            # connector -> catcher window
        app = win.get_application()
        self.mark = os.path.join(MARKS, app.get_application_id() if app else "popup")
        if app:
            action = Gio.SimpleAction.new("close-popup", None)
            action.connect("activate", lambda *_: win.get_visible() and win.close())
            app.add_action(action)
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(win.get_display(), prov,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER)
        win.connect("notify::visible", self.on_visible)

    def on_visible(self, win, _pspec):
        if win.get_visible():
            self.show()
        else:
            self.hide()

    def show(self):
        try:
            os.makedirs(MARKS, exist_ok=True)
            open(self.mark, "w").close()
        except OSError:
            pass
        if LS is None:
            return
        own = focused_output()       # the popup itself opened on the focused screen
        monitors = self.win.get_display().get_monitors()
        present = set()
        for i in range(monitors.get_n_items()):
            mon = monitors.get_item(i)
            name = mon.get_connector()
            present.add(name)
            if name == own:
                continue
            catcher = self.windows.get(name)
            if catcher is None:
                catcher = self.windows[name] = self.make(mon)
            catcher.present()
        for name in list(self.windows):         # screens that were unplugged
            if name not in present:
                self.windows.pop(name).destroy()

    def hide(self):
        try:
            os.remove(self.mark)
        except OSError:
            pass
        for catcher in self.windows.values():
            catcher.set_visible(False)

    def make(self, mon):
        c = Gtk.Window(decorated=False)
        c.add_css_class("popup-catcher")
        LS.init_for_window(c)
        LS.set_namespace(c, "popup-catcher")
        LS.set_layer(c, LS.Layer.OVERLAY)
        LS.set_monitor(c, mon)
        for edge in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
            LS.set_anchor(c, edge, True)
        LS.set_exclusive_zone(c, -1)
        LS.set_keyboard_mode(c, LS.KeyboardMode.NONE)   # the popup keeps the keyboard
        box = Gtk.Box(hexpand=True, vexpand=True)
        click = Gtk.GestureClick(button=0)
        click.connect("pressed", lambda *_: self.win.close())
        box.add_controller(click)
        c.set_child(box)
        return c


def smooth_text():
    """No font hinting in the popups: on scale-1 screens hinting snaps the tops of
    round letters to the pixel grid, so B, C, O ... look cut flat."""
    s = Gtk.Settings.get_default()
    if s is None:
        return
    if hasattr(Gtk, "FontRendering"):          # GTK >= 4.16
        s.props.gtk_font_rendering = Gtk.FontRendering.MANUAL
    s.props.gtk_hint_font_metrics = False
    s.props.gtk_xft_hinting = 0
    s.props.gtk_xft_hintstyle = "hintnone"
    s.props.gtk_xft_antialias = 1


def attach(win):
    smooth_text()
    win._catchers = Catchers(win)
    return win._catchers
