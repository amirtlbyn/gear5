#!/usr/bin/env python3
"""
Software brightness for a screen that can't change its own (e.g. behind a dock
that blocks DDC/CI): a click-through dark layer over that one screen.

  dim-screen.py OUTPUT          keep OUTPUT dimmed to the level in its level file
  dim-screen.py --restore       start one for every screen that has a saved level

The level file $XDG_RUNTIME_DIR/screen-dim/OUTPUT holds a brightness 10-100.
Write a new number to change it live; 100 (or deleting the file) ends the layer.
Only one runs per screen; starting it again does nothing.
"""
import os
import subprocess
import sys

LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if not os.environ.get("DIM_SCREEN_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["DIM_SCREEN_PRELOADED"] = "1"
    if lib:
        old = os.environ.get("LD_PRELOAD", "")
        os.environ["LD_PRELOAD"] = lib + (":" + old if old else "")
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])

import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LS  # noqa: E402

LEVEL_DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "screen-dim")
MAX_DARK = 0.85   # brightness 10% still leaves the screen readable


def read_level(output):
    try:
        with open(os.path.join(LEVEL_DIR, output)) as f:
            return max(10, min(100, int(f.read().strip())))
    except (OSError, ValueError):
        return 100


def restore():
    try:
        outputs = os.listdir(LEVEL_DIR)
    except OSError:
        return 0
    for output in outputs:
        if read_level(output) < 100:
            subprocess.Popen([sys.executable, os.path.abspath(__file__), output],
                             start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 0


class Dimmer(Gtk.Application):
    def __init__(self, output):
        app_id = "io.local.dim." + "".join(c if c.isalnum() else "_" for c in output)
        super().__init__(application_id=app_id)
        self.output = output
        self.win = None
        self.css = Gtk.CssProvider()

    def do_activate(self):
        if self.win:            # already dimming this screen
            return
        monitor = self.find_monitor()
        if monitor is None:
            self.quit()
            return
        monitor.connect("invalidate", lambda *_: self.quit())   # screen unplugged / asleep

        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER)
        win = Gtk.Window(application=self, decorated=False)
        win.add_css_class("dim")
        LS.init_for_window(win)
        LS.set_namespace(win, "screen-dim")
        LS.set_layer(win, LS.Layer.OVERLAY)
        LS.set_monitor(win, monitor)
        for edge in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
            LS.set_anchor(win, edge, True)
        LS.set_exclusive_zone(win, -1)
        LS.set_keyboard_mode(win, LS.KeyboardMode.NONE)
        # clicks and scrolling go straight through to the windows below
        win.connect("realize", lambda w: w.get_surface().set_input_region(cairo.Region()))
        self.win = win

        path = os.path.join(LEVEL_DIR, self.output)
        self.watch = Gio.File.new_for_path(path).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.watch.connect("changed", lambda *_: self.apply())
        self.apply()
        win.present()

    def find_monitor(self):
        monitors = Gdk.Display.get_default().get_monitors()
        for i in range(monitors.get_n_items()):
            m = monitors.get_item(i)
            if m.get_connector() == self.output:
                return m
        return None

    def apply(self):
        level = read_level(self.output)
        if level >= 100:
            self.quit()
            return
        dark = (100 - level) / 90 * MAX_DARK
        self.css.load_from_string(f"window.dim {{ background: rgba(0,0,0,{dark:.3f}); }}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--restore":
        sys.exit(restore())
    sys.exit(Dimmer(sys.argv[1]).run([sys.argv[0]]))
