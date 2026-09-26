#!/usr/bin/env python3
"""
Power popup for Waybar (Everforest style).  power-popup.py [THEME]
Choose what happens when you're away, and after how long. Click outside / Esc to close.
"""
import os
import subprocess
import sys

LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if not os.environ.get("POWER_POPUP_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["POWER_POPUP_PRELOADED"] = "1"
    if lib:
        old = os.environ.get("LD_PRELOAD", "")
        os.environ["LD_PRELOAD"] = lib + (":" + old if old else "")
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LS  # noqa: E402
except (ValueError, ImportError):
    LS = None

import palette  # noqa: E402

import popup_backdrop  # noqa: E402

IDLE = os.path.expanduser("~/.config/hypr/scripts/idle.sh")
THEME = sys.argv[1] if len(sys.argv) > 1 else palette.current()
P = palette.load(THEME, edge="edge_deep")
CSS = "".join(f"@define-color {k} {v};\n" for k, v in P.items()) + """
window.power-popup { background: transparent; }
.backdrop { background: transparent; }
.popup {
  background: @bg0; color: @fg;
  border-radius: 14px; border-bottom: 6px solid @edge; padding: 14px;
  font-family: "JetBrainsMono Nerd Font", sans-serif; font-weight: bold; font-size: 14px;
}
.title { font-size: 18px; }
.section { color: @grey; font-size: 12px; margin: 10px 2px 2px 2px; }

button.opt {
  background: @bg1; color: @fg;
  border: none; border-radius: 10px; border-bottom: 4px solid @edge; box-shadow: none;
  padding: 8px 12px; margin: 3px 0;
}
button.opt:hover { background: @bg2; }
button.opt.on { background: @bg2; box-shadow: inset 4px 0 0 @green; }
button.opt .icon { font-size: 18px; min-width: 30px; }
button.opt .desc { color: @grey; font-weight: normal; font-size: 12px; }
button.opt.on .icon { color: @green; }

button.chip {
  background: @bg1; color: @fg;
  border: none; border-radius: 8px; border-bottom: 3px solid @edge; box-shadow: none;
  padding: 3px 0; min-height: 0; min-width: 44px;
}
button.chip:hover { background: @bg2; }
button.chip.on { background: @green; color: @bg0; border-bottom-color: @green_edge; }
button.chip:disabled { opacity: 0.35; }

button.act {
  background: @bg3; color: @fg;
  border: none; border-radius: 8px; border-bottom: 3px solid @edge; box-shadow: none;
  padding: 6px 10px; min-height: 0;
}
button.act:hover { background: shade(@bg3, 1.1); }
button.act.danger { background: @red; color: @bg0; border-bottom-color: @red_edge; }
"""

MODES = [
    ("sleep", "\U000f04b2", "Sleep", "Lock, then sleep once nothing is running"),
    ("lock",  "\U000f033e", "Lock only", "Builds and terminals keep running"),
    ("awake", "\U000f0176", "Stay awake", "Nothing happens automatically"),
]
TIMES = [1, 2, 5, 10, 15, 30, 60]


def idle(*args):
    return subprocess.run([IDLE, *args], capture_output=True, text=True).stdout.strip()


class Power(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.local.powerpopup")
        self.win = None
        mode, _, mins = (idle("get") or "sleep 5").partition(" ")
        self.mode = mode or "sleep"
        self.mins = int(mins) if mins.isdigit() else 5

    # stays running hidden after the first use, so clicking the bar opens it instantly
    def do_activate(self):
        if self.win is not None:
            if self.win.get_visible():
                self.win.close()
            elif GLib.get_monotonic_time() - getattr(self, "closed_at", 0) > 400_000:
                # the click that just closed it (outside the popup, on the bar box)
                # also reaches the bar, which asks to open it again: ignore that one
                self.show_popup()
            return
        self.hold()
        self.build()
        if "--hidden" not in sys.argv:
            self.show_popup()

    def show_popup(self):
        # the mode may have changed elsewhere (quick settings' Stay awake)
        mode, _, mins = (idle("get") or "sleep 5").partition(" ")
        self.mode = mode or "sleep"
        self.mins = int(mins) if mins.isdigit() else 5
        self.update()
        self.win.present()

    def on_close(self, win):
        self.closed_at = GLib.get_monotonic_time()
        win.set_visible(False)   # hide, don't destroy
        return True

    def build(self):
        prov = Gtk.CssProvider()
        if hasattr(prov, "load_from_string"):
            prov.load_from_string(CSS)
        else:
            prov.load_from_data(CSS, -1)
        add = getattr(Gtk, "style_context_add_provider_for_display", None) \
            or Gtk.StyleContext.add_provider_for_display
        add(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)

        win = Gtk.ApplicationWindow(application=self, title="Power")
        win.add_css_class("power-popup")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win

        popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.add_css_class("popup")
        popup.set_size_request(360, -1)

        title = Gtk.Label(label="\U000f0425  Power", xalign=0)
        title.add_css_class("title")
        popup.append(title)

        sec = Gtk.Label(label="WHEN I'M AWAY", xalign=0)
        sec.add_css_class("section")
        popup.append(sec)
        self.opt_buttons = {}
        for key, icon, name, desc in MODES:
            btn = Gtk.Button()
            btn.add_css_class("opt")
            row = Gtk.Box(spacing=8)
            ic = Gtk.Label(label=icon)
            ic.add_css_class("icon")
            txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            n = Gtk.Label(label=name, xalign=0)
            d = Gtk.Label(label=desc, xalign=0)
            d.add_css_class("desc")
            txt.append(n)
            txt.append(d)
            row.append(ic)
            row.append(txt)
            btn.set_child(row)
            btn.connect("clicked", lambda _b, k=key: self.choose(mode=k))
            popup.append(btn)
            self.opt_buttons[key] = btn

        sec2 = Gtk.Label(label="AFTER", xalign=0)
        sec2.add_css_class("section")
        popup.append(sec2)
        chips = Gtk.Box(spacing=6, homogeneous=True)
        self.chip_buttons = {}
        for m in TIMES:
            b = Gtk.Button(label=f"{m // 60}h" if m >= 60 else f"{m}m")
            b.add_css_class("chip")
            b.connect("clicked", lambda _b, m=m: self.choose(mins=m))
            chips.append(b)
            self.chip_buttons[m] = b
        popup.append(chips)

        sec3 = Gtk.Label(label="NOW", xalign=0)
        sec3.add_css_class("section")
        popup.append(sec3)
        acts = Gtk.Box(spacing=6, homogeneous=True)
        for label, cmd, danger in (
            ("\U000f033e  Lock", "pidof hyprlock || (hyprctl switchxkblayout all 0; hyprlock)", False),
            ("\U000f04b2  Sleep", "systemctl suspend", False),
            ("\U000f0425  Power off", "systemctl poweroff", True),
        ):
            b = Gtk.Button(label=label)
            b.add_css_class("act")
            if danger:
                b.add_css_class("danger")
            b.connect("clicked", lambda _b, c=cmd: self.run_now(c))
            acts.append(b)
        popup.append(acts)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, kv, *_: (win.close(), True)[1] if kv == Gdk.KEY_Escape else False)
        win.add_controller(keys)

        if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
            LS.init_for_window(win)
            LS.set_namespace(win, "power-popup")
            LS.set_layer(win, LS.Layer.OVERLAY)
            for e in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
                LS.set_anchor(win, e, True)
            LS.set_exclusive_zone(win, -1)
            LS.set_keyboard_mode(win, LS.KeyboardMode.EXCLUSIVE)
            popup_backdrop.attach(win)   # clicks on the other screens close it too
            backdrop = Gtk.Box(hexpand=True, vexpand=True)
            backdrop.add_css_class("backdrop")
            click = Gtk.GestureClick()
            click.connect("pressed", lambda *_: win.close())
            backdrop.add_controller(click)
            popup.set_halign(Gtk.Align.END)
            popup.set_valign(Gtk.Align.START)
            popup.set_margin_top(72)
            popup.set_margin_end(420)
            overlay = Gtk.Overlay()
            overlay.set_child(backdrop)
            overlay.add_overlay(popup)
            win.set_child(overlay)
        else:
            win.set_child(popup)
            win.connect("notify::is-active", lambda w, _p: None if w.is_active() else w.close())

        self.update()

    def update(self):
        for k, b in self.opt_buttons.items():
            (b.add_css_class if k == self.mode else b.remove_css_class)("on")
        for m, b in self.chip_buttons.items():
            (b.add_css_class if m == self.mins else b.remove_css_class)("on")
            b.set_sensitive(self.mode != "awake")

    def choose(self, mode=None, mins=None):
        if mode:
            self.mode = mode
        if mins:
            self.mins = mins
        idle("set", self.mode, str(self.mins))
        self.update()

    def run_now(self, cmd):
        self.win.close()
        subprocess.Popen(["sh", "-c", f"sleep 0.3; {cmd}"], start_new_session=True)


if __name__ == "__main__":
    sys.exit(Power().run([sys.argv[0]]))
