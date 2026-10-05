#!/usr/bin/env python3
"""
The pop-up (roadmap 6.2, spec GIFT): when a theme is applied, its GIF, its name and
its character show under the bar and go away by themselves. A theme with no GIF shows
nothing: the process exits at once. It takes no keyboard and no pointer input, and it
runs only for these 2.5 s: no process stays.  sticker.py [THEME]
"""
import os
import sys

LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if __name__ == "__main__" and not os.environ.get("STICKER_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["STICKER_PRELOADED"] = "1"
    if lib:
        old = os.environ.get("LD_PRELOAD", "")
        os.environ["LD_PRELOAD"] = lib + (":" + old if old else "")
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])

import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LS  # noqa: E402
except (ValueError, ImportError):
    LS = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import palette  # noqa: E402
import popup_backdrop  # noqa: E402
import theme_gif  # noqa: E402

SHOW_MS = 2500  # the pop-up exits after this (CHAR-7 allows 4 s)
BAR_HEIGHT = 60  # bar/config: the sticker hangs just under it
ART = 200  # the picture's size in px
STYLE = """
window.sticker {{ background: transparent; }}
.card {{
  background: {bg0}; color: {fg}; border-radius: 16px; border-bottom: 6px solid {edge};
  padding: 16px 28px; font-family: "JetBrainsMono Nerd Font", sans-serif; font-weight: bold;
}}
.name {{ font-size: 20px; }}
.character {{ color: {grey}; font-size: 13px; }}
"""


def art_widget(gif_path):
    """The GIF playing, or None when the file cannot be read."""
    try:
        anim = GdkPixbuf.PixbufAnimation.new_from_file(gif_path)
    except GLib.Error:
        return None
    pic = Gtk.Picture(can_shrink=False)
    pic.set_size_request(ART, ART)
    play(pic, anim)
    return pic


def play(pic, anim):
    """Step the GIF's frames on the main loop; the exit timer ends it."""
    it = anim.get_iter(None)

    def step():
        pic.set_paintable(Gdk.Texture.new_for_pixbuf(fit(it.get_pixbuf())))
        delay = it.get_delay_time()
        if delay < 0:  # a still GIF: one frame
            return False
        GLib.timeout_add(max(delay, 20), advance)
        return False

    def advance():
        it.advance(None)
        step()
        return False

    step()


def fit(pixbuf):
    """A GIF frame scaled to fit ART x ART, so a big GIF never makes a big card."""
    w, h = pixbuf.get_width(), pixbuf.get_height()
    if max(w, h) <= ART:
        return pixbuf
    k = ART / max(w, h)
    return pixbuf.scale_simple(max(1, round(w * k)), max(1, round(h * k)), GdkPixbuf.InterpType.BILINEAR)


def click_through(win):
    """An empty input region: every click goes to the window below (INV-1)."""
    win.get_surface().set_input_region(cairo.Region())


def build(app, theme_id):
    t = palette.theme(theme_id)
    gif_path = theme_gif.gif(t["id"])
    art = art_widget(gif_path) if gif_path else None
    if art is None:
        return None
    c = t["colors"]
    win = Gtk.ApplicationWindow(application=app, title="Sticker", decorated=False, focusable=False)
    win.add_css_class("sticker")
    prov = Gtk.CssProvider()
    prov.load_from_string(STYLE.format(bg0=c["bg0"], fg=c["fg"], edge=c.get("edge_deep", c["bg2"]), grey=c["grey"]))
    Gtk.StyleContext.add_provider_for_display(win.get_display(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER, valign=Gtk.Align.START)
    card.add_css_class("card")
    card.append(art)
    name = Gtk.Label(label=t["name"])
    name.add_css_class("name")
    card.append(name)
    if t["character"] not in ("", t["name"]):
        who = Gtk.Label(label=t["character"])
        who.add_css_class("character")
        card.append(who)
    win.set_child(card)

    if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
        LS.init_for_window(win)
        LS.set_namespace(win, "sticker")
        LS.set_layer(win, LS.Layer.OVERLAY)
        LS.set_anchor(win, LS.Edge.TOP, True)
        LS.set_margin(win, LS.Edge.TOP, BAR_HEIGHT + 4)
        LS.set_exclusive_zone(win, -1)
        LS.set_keyboard_mode(win, LS.KeyboardMode.NONE)
        out = popup_backdrop.focused_output()
        monitors = win.get_display().get_monitors()
        for i in range(monitors.get_n_items()):
            if monitors.get_item(i).get_connector() == out:
                LS.set_monitor(win, monitors.get_item(i))
    win.connect("realize", click_through)
    return win


class Sticker(Gtk.Application):
    def __init__(self, theme_id):
        # NON_UNIQUE: no D-Bus name, so a second sticker never waits for the first
        super().__init__(application_id="io.local.sticker", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.theme_id = theme_id

    def do_activate(self):
        GLib.timeout_add(SHOW_MS, self.quit)  # first: a slow GIF decode must not delay the exit
        popup_backdrop.smooth_text()
        win = build(self, self.theme_id)
        if win is None:  # no GIF: nothing pops up (GIFT-8)
            self.quit()
        else:
            win.present()


def main(argv):
    return Sticker(argv[1] if len(argv) > 1 else palette.current()).run([argv[0]])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
