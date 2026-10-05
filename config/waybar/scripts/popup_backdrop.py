"""
Shared by every popup: close it when you click on ANY screen, not only its own.

A popup is a full-screen layer on the screen you opened it on, so a click on another
screen used to go straight to the window there and leave the popup open. While a
popup is shown, this puts a transparent click-catcher on every other screen too.

It also plays the popup's entry motion (see animate_in), turns off font hinting (see
smooth_text), and gives each popup a "close-popup" action and marks it as open in
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

# The entry motion (roadmap 4.1). A popup is hidden and shown again, never made
# again, and GTK plays a CSS animation on it again only when the animation's name
# changes: so each kind has two identical keyframes, and every open takes the other.
MOTION_MS = 120
BAR_REACH = 80   # a box aligned to the top this close to it hangs from the bar
MOTION = {
    "slide": "opacity: 0; transform: translateY(-8px);",   # from the bar
    "scale": "opacity: 0; transform: scale(0.97);",        # centered popups
}
MOTION_CSS = "".join(
    f"@keyframes popup-{kind}-{n} {{ from {{ {start} }} to {{ opacity: 1; transform: none; }} }}\n"
    f".popup.motion-{kind}-{n} {{ animation: popup-{kind}-{n} {MOTION_MS}ms ease-out; }}\n"
    for kind, start in MOTION.items()
    for n in "ab"
)
MOTION_CLASSES = [f"motion-{kind}-{n}" for kind in MOTION for n in "ab"]


def cursor_on_screen():
    """(x, y, screen width) of the mouse on the focused screen, in logical pixels,
    or None when Hyprland can't tell. A popup opened by a click on the bar uses
    it to open under that click."""
    try:
        pos = json.loads(subprocess.run(["hyprctl", "-j", "cursorpos"], capture_output=True,
                                        text=True, timeout=2, check=False).stdout)
        mons = json.loads(subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True,
                                         text=True, timeout=2, check=False).stdout)
        mon = next(m for m in mons if m.get("focused"))
        width = (mon["height"] if mon.get("transform", 0) % 2 else mon["width"]) / mon["scale"]
        return pos["x"] - mon["x"], pos["y"] - mon["y"], width
    except (OSError, ValueError, KeyError, StopIteration, subprocess.TimeoutExpired):
        return None


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
        prov.load_from_string(CSS + MOTION_CSS)
        Gtk.StyleContext.add_provider_for_display(win.get_display(), prov,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER)
        win.connect("notify::visible", self.on_visible)

    def on_visible(self, win, _pspec):
        if win.get_visible():
            animate_in(outermost_popup(win))
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


def outermost_popup(win):
    """The window's first `.popup` box, breadth first: control-center's panels
    are `.popup` boxes too, inside its own, and only the outer one moves."""
    queue = [win.get_child()]
    while queue:
        widget = queue.pop(0)
        if widget is None:
            continue
        if widget.has_css_class("popup"):
            return widget
        child = widget.get_first_child()
        while child is not None:
            queue.append(child)
            child = child.get_next_sibling()
    return None


def motion_kind(box):
    """"slide" for a box that hangs from the bar, "scale" for the others."""
    if box.get_valign() == Gtk.Align.START and box.get_margin_top() <= BAR_REACH:
        return "slide"
    return "scale"


def animate_in(box):
    """Give the box the other entry-animation class than last time, so GTK plays
    the motion on this open too."""
    if box is None:
        return
    last = next((c for c in MOTION_CLASSES if box.has_css_class(c)), None)
    for c in MOTION_CLASSES:
        box.remove_css_class(c)
    n = "b" if last is not None and last.endswith("-a") else "a"
    box.add_css_class(f"motion-{motion_kind(box)}-{n}")


def motion_setting():
    """Settings > Look & behavior > Animations off: GTK plays no CSS animation.
    Turning it on or off restarts the popups (Hyprland reloads), so reading it
    once at start is enough."""
    s = Gtk.Settings.get_default()
    if s is None:
        return
    try:
        import settings_store

        s.props.gtk_enable_animations = settings_store.load()["animations"]
    except (ImportError, OSError, KeyError):
        pass


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
    motion_setting()
    win._catchers = Catchers(win)
    return win._catchers
