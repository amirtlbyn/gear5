#!/usr/bin/env python3
"""
Clipboard history (SUPER+V), Everforest style, on top of cliphist.

  clipboard.py [THEME] [--hidden]

- Type to search; filter by text, links, code, images or pinned (Tab / Shift+Tab
  or Alt+1..6 switch the filter).
- Click (or Enter) pastes the item into the app you were using; right-click only copies.
- ⭐ (or Ctrl+P on the selected item) pins it: pinned items stay on top and
  survive "Clear all". Press it again to unpin. Images can be pinned too: a copy of
  the picture is kept in ~/.local/share/clipboard-pins/.
- ✕ deletes one item; "Clear all" asks once more before wiping the history.
- Images show as thumbnails.
- Stays running hidden after the first use, so it opens instantly.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import weakref

LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if __name__ == "__main__" and not os.environ.get("CLIPBOARD_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["CLIPBOARD_PRELOADED"] = "1"
    if lib:
        old = os.environ.get("LD_PRELOAD", "")
        os.environ["LD_PRELOAD"] = lib + (":" + old if old else "")
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LS  # noqa: E402
except (ValueError, ImportError):
    LS = None

import fonts  # noqa: E402
import palette  # noqa: E402

import popup_backdrop  # noqa: E402

THEME = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else palette.current()
WIDTH = 540
# a thumbnail is 90 px tall: decode pictures to at most twice that (a 2x screen),
# not at their full size
THUMB_MAX_H, THUMB_MAX_W = 180, 2 * WIDTH
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "clipboard-popup")
PINS = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "clipboard-pins.json")
PIN_IMAGES = os.path.join(os.path.dirname(PINS), "clipboard-pins")   # pinned pictures
TERMINALS = ("kitty", "ghostty", "foot", "alacritty", "wezterm", "ptyxis", "terminal", "konsole", "tilix")

P = palette.load(THEME)

CSS = fonts.swap("".join(f"@define-color {k} {v};\n" for k, v in P.items()) + """
window.clipboard { background: transparent; }
.backdrop { background: alpha(black, 0.12); }
.popup {
  background: @bg0; color: @fg;
  border-radius: 22px; border: 1px solid alpha(@fg, 0.07);
  box-shadow: 0 22px 50px @shadow, 0 2px 6px alpha(black, 0.25);
  padding: 14px;
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif; font-weight: bold; font-size: 14px;
}
.title { font-size: 19px; }
.count { color: @grey; font-weight: normal; font-size: 12px; }
button.clear-all {
  background: transparent; color: @grey; border: none; box-shadow: none;
  border-radius: 10px; padding: 3px 10px; min-height: 0; font-size: 12px;
}
button.clear-all:hover { color: @red; background: alpha(@red, 0.1); }
button.clear-all.confirm { background: @red; color: @on_accent; }
entry.search {
  background: @bg1; color: @fg; border: none; box-shadow: none; outline: none;
  border-radius: 14px; border-bottom: 3px solid @edge; padding: 4px 12px; min-height: 40px; font-size: 15px;
  margin-top: 10px;
}
.chips { margin: 10px 0 4px 0; }
.chips button {
  background: @bg1; color: @fg; border: none; box-shadow: none;
  border-radius: 10px; padding: 4px 10px; min-height: 0; font-size: 12px; border-bottom: 2px solid @edge;
}
.chips button:hover { background: @bg2; }
.chips button.active { background: @green; color: @on_accent; }

list.items { background: transparent; }
list.items > row {
  background: @bg1; border-radius: 14px; margin: 3px 0; padding: 8px 10px;
  border: 1px solid alpha(@fg, 0.03); border-bottom: 3px solid @edge; outline: none;
}
list.items > row:hover { background: @bg2; }
list.items > row:selected, list.items > row:focus {
  background: @bg2; box-shadow: inset 4px 0 0 @green; color: @fg;
}
list.items > row.pinned { box-shadow: inset 4px 0 0 @yellow; }
.kind { font-size: 18px; min-width: 28px; color: @blue; }
.kind.link { color: @aqua; }
.kind.code { color: @purple; }
.kind.number { color: @orange; }
.kind.image { color: @yellow; }
.text { font-size: 13px; }
.mono { font-family: "JetBrainsMono Nerd Font", monospace; font-weight: normal; font-size: 12px; }
.meta { color: @grey; font-weight: normal; font-size: 11px; }
.thumb { border-radius: 10px; }
.swatch { border-radius: 6px; min-width: 18px; min-height: 18px; border: 1px solid alpha(@fg, 0.2); }
button.act {
  background: transparent; color: @grey; border: none; box-shadow: none;
  border-radius: 8px; padding: 2px 6px; min-height: 0; min-width: 0; font-size: 14px; opacity: 0.35;
}
list.items > row:hover button.act { opacity: 1; }
button.act:hover { background: alpha(@fg, 0.08); color: @fg; }
button.act.pin.on { color: @yellow; opacity: 1; }
button.act.del:hover { color: @red; }
.empty { color: @grey; font-weight: normal; padding: 40px; }
.footer { color: @grey; font-weight: normal; font-size: 11px; margin: 8px 4px 0 4px; }
""")

I_CLIP, I_TEXT, I_LINK, I_CODE, I_NUM, I_IMG, I_COLOR = (
    "\U000f014c", "\U000f09ed", "\U000f0337", "\U000f0169", "\U000f03a0", "\U000f02e9", "\U000f0266")
I_PIN, I_X, I_TRASH = "\U000f04ce", "\U000f0156", "\U000f0a7a"

IMG_RE = re.compile(r"^\[\[ binary data (.+?) \]\]$")
COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?([0-9a-fA-F]{2})?|rgba?\([^)]*\))$")
NUM_RE = re.compile(r"^[-+]?[\d,._ ]*\d[\d,._ ]*(e[-+]?\d+)?%?$", re.I)
CODE_HINT = re.compile(r"[{};=<>]|^\s*(def|class|import|from|const|let|var|function|SELECT|sudo|git|cd|\$) ", re.M)


def kind_of(text):
    t = text.strip()
    if IMG_RE.match(t):
        return "image"
    if re.match(r"^(https?|ftp)://\S+$", t) or re.match(r"^www\.\S+$", t):
        return "link"
    if COLOR_RE.match(t):
        return "color"
    if NUM_RE.match(t) or re.match(r"^0x[0-9a-f]+$", t, re.I):
        return "number"
    if CODE_HINT.search(t) or "\t" in t:
        return "code"
    return "text"


ICONS = {"image": I_IMG, "link": I_LINK, "color": I_COLOR, "number": I_NUM, "code": I_CODE, "text": I_TEXT}


def history():
    """[(line, id, preview)] newest first."""
    try:
        out = subprocess.run(["cliphist", "list"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    items = []
    for line in out.splitlines():
        cid, _, preview = line.partition("\t")
        if cid.isdigit():
            items.append((line, cid, preview))
    return items


def decode(line):
    try:
        return subprocess.run(["cliphist", "decode"], input=line.encode(), capture_output=True,
                              timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return b""


def thumb_file(line, cid):
    path = os.path.join(CACHE, f"{cid}.img")
    if not os.path.exists(path):
        data = decode(line)
        if not data:
            return None
        os.makedirs(CACHE, exist_ok=True)
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    return path


def thumbnail(path):
    """The picture as a texture no bigger than THUMB_MAX_W x THUMB_MAX_H, with its
    aspect ratio (LEAK-3). A small picture keeps its own size."""
    _fmt, w, h = GdkPixbuf.Pixbuf.get_file_info(path)
    scale = min(1.0, THUMB_MAX_H / h, THUMB_MAX_W / w) if w and h else 1.0
    if scale >= 1.0:
        return Gdk.Texture.new_from_filename(path)
    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, max(1, round(w * scale)), max(1, round(h * scale)), True)
    fmt = Gdk.MemoryFormat.R8G8B8A8 if pb.get_has_alpha() else Gdk.MemoryFormat.R8G8B8
    return Gdk.MemoryTexture.new(pb.get_width(), pb.get_height(), fmt, pb.read_pixel_bytes(), pb.get_rowstride())


def load_pins():
    """Texts are strings; pictures are {"image": file in PIN_IMAGES, "preview": cliphist line}."""
    try:
        with open(PINS) as f:
            pins = json.load(f)
    except (OSError, ValueError):
        return []
    return [p for p in pins if isinstance(p, str) or
            (isinstance(p, dict) and os.path.exists(os.path.join(PIN_IMAGES, str(p.get("image")))))]


def pin_key(pin):
    return pin if isinstance(pin, str) else pin["preview"]


def pin_image(data, preview):
    """Keep our own copy of a picture, so it survives the history being cleared."""
    m = IMG_RE.match(preview.strip())
    ext = next((w for w in (m.group(1).lower().split() if m else []) if w in IMG_TYPES), "png")
    name = hashlib.sha1(data).hexdigest()[:16] + "." + ext
    os.makedirs(PIN_IMAGES, exist_ok=True)
    with open(os.path.join(PIN_IMAGES, name), "wb") as f:
        f.write(data)
    return dict(image=name, preview=preview)


IMG_TYPES = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "gif": "image/gif",
             "webp": "image/webp", "bmp": "image/bmp"}


def save_pins(pins):
    try:
        os.makedirs(os.path.dirname(PINS), exist_ok=True)
        with open(PINS, "w") as f:
            json.dump(pins, f)
    except OSError:
        pass


def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


def run_bg(work, done):
    def target():
        result = work()
        GLib.idle_add(lambda: (done(result), False)[1])
    threading.Thread(target=target, daemon=True).start()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
class Item(Gtk.ListBoxRow):
    def __init__(self, app, text, line=None, cid=None, pinned=False, image=None):
        super().__init__()
        self.app, self.text, self.line, self.cid, self.pinned = app, text, line, cid, pinned
        self.image = image          # file of a pinned picture
        self.kind = kind_of(text)
        # the handlers reach this row through a weak reference: a lambda that holds
        # the row itself is a cycle PyGObject never frees, so every row removed by
        # fill() stayed in memory with its picture (LEAK-1)
        me = weakref.ref(self)
        if pinned:
            self.add_css_class("pinned")
        box = Gtk.Box(spacing=10)
        k = label(ICONS[self.kind], f"kind {self.kind}", valign=Gtk.Align.START)
        box.append(k)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        if self.kind == "image":
            info = IMG_RE.match(text.strip()).group(1)
            self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True,
                                       halign=Gtk.Align.START)
            self.picture.add_css_class("thumb")
            self.picture.set_size_request(-1, 90)
            body.append(self.picture)
            body.append(label(info, "meta", xalign=0))
            if image:
                self.set_thumb(image)
            else:
                run_bg(lambda: thumb_file(line, cid), self.set_thumb)
        else:
            shown = text.strip()
            lines = shown.splitlines()
            short = "\n".join(lines[:3]) + ("…" if len(lines) > 3 else "")
            row = Gtk.Box(spacing=8)
            if self.kind == "color":
                sw = Gtk.Box(valign=Gtk.Align.CENTER)
                sw.add_css_class("swatch")
                prov = Gtk.CssProvider()
                prov.load_from_string(f"box {{ background: {shown}; }}")
                sw.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
                row.append(sw)
            txt = label(short, "text mono" if self.kind == "code" else "text", xalign=0, hexpand=True,
                        wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, lines=3,
                        ellipsize=Pango.EllipsizeMode.END)
            row.append(txt)
            body.append(row)
            extra = [f"{len(lines)} lines"] if len(lines) > 1 else []
            if len(shown) > 60:
                extra.append(f"{len(shown)} chars")
            if extra:
                body.append(label(" · ".join(extra), "meta", xalign=0))
        box.append(body)

        acts = Gtk.Box(spacing=2, valign=Gtk.Align.START)
        if True:                    # texts and pictures can both be pinned
            pin = Gtk.Button(label=I_PIN, tooltip_text="Unpin" if pinned else "Pin (kept on top, survives Clear all)")
            pin.add_css_class("act")
            pin.add_css_class("pin")
            if pinned:
                pin.add_css_class("on")
            pin.connect("clicked", lambda *_: app.toggle_pin(me()))
            acts.append(pin)
        dele = Gtk.Button(label=I_X, tooltip_text="Delete")
        dele.add_css_class("act")
        dele.add_css_class("del")
        dele.connect("clicked", lambda *_: app.delete(me()))
        acts.append(dele)
        box.append(acts)
        self.set_child(box)

        right = Gtk.GestureClick(button=3)
        right.connect("pressed", lambda *_: app.copy_only(me()))
        self.add_controller(right)

    def set_thumb(self, path):
        if path:
            try:
                self.picture.set_paintable(thumbnail(path))
            except GLib.Error:
                pass


class Clipboard(Gtk.Application):
    FILTERS = [("all", "All"), ("text", "Text"), ("link", "Links"), ("code", "Code"), ("image", "Images"),
               ("pinned", "Pinned")]

    def __init__(self):
        super().__init__(application_id="io.local.clipboard")
        self.win = None
        self.filter = "all"
        self.query = ""
        self.pins = load_pins()
        self.confirm_clear = False

    def do_activate(self):
        if self.win is not None:
            if self.win.get_visible():
                self.win.close()
            elif GLib.get_monotonic_time() - getattr(self, "closed_at", 0) > 400_000:
                self.show_popup()
            return
        self.hold()
        self.build()
        if "--hidden" not in sys.argv:
            self.show_popup()

    def show_popup(self):
        self.search.set_text("")
        self.query = ""
        self.set_filter("all", reload=False)
        self.reset_clear()
        self.reload()
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
        win = Gtk.ApplicationWindow(application=self, title="Clipboard")
        win.add_css_class("clipboard")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win

        popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.add_css_class("popup")
        popup.set_size_request(WIDTH, -1)

        head = Gtk.Box(spacing=10)
        head.append(label(f"{I_CLIP}  Clipboard", "title", xalign=0))
        self.count = label(css="count", xalign=0, hexpand=True, valign=Gtk.Align.CENTER)
        head.append(self.count)
        self.clear_btn = Gtk.Button(label=f"{I_TRASH}  Clear all")
        self.clear_btn.add_css_class("clear-all")
        self.clear_btn.connect("clicked", lambda *_: self.clear_all())
        head.append(self.clear_btn)
        popup.append(head)

        self.search = Gtk.SearchEntry(placeholder_text="Search your clipboard…")
        self.search.add_css_class("search")
        self.search.connect("search-changed", lambda *_: self.on_search())
        self.search.connect("activate", lambda *_: self.paste_row(self.first_row()))
        k = Gtk.EventControllerKey()
        k.connect("key-pressed", self.on_search_key)
        self.search.add_controller(k)
        popup.append(self.search)

        chips = Gtk.Box(spacing=6)
        chips.add_css_class("chips")
        self.chip_btns = {}
        for key, name in self.FILTERS:
            b = Gtk.Button(label=name)
            b.connect("clicked", lambda _b, k=key: self.set_filter(k))
            self.chip_btns[key] = b
            chips.append(b)
        popup.append(chips)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=True)
        self.list.add_css_class("items")
        self.list.connect("row-activated", lambda _l, row: self.paste_row(row))
        self.list.set_filter_func(self.visible)
        self.scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                         min_content_height=420, max_content_height=420)
        self.scroll.set_child(self.list)
        popup.append(self.scroll)
        self.empty = label("Nothing here yet — copy something!", "empty")
        self.empty.set_visible(False)
        popup.append(self.empty)
        popup.append(label("Enter pastes · Tab filter · Ctrl+P pin · right-click copies · Del deletes",
                           "footer", xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=1))

        esc = Gtk.EventControllerKey()
        esc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        esc.connect("key-pressed", self.on_key)
        win.add_controller(esc)

        if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
            LS.init_for_window(win)
            LS.set_namespace(win, "clipboard")
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
            popup.set_halign(Gtk.Align.CENTER)
            popup.set_valign(Gtk.Align.CENTER)
            overlay = Gtk.Overlay()
            overlay.set_child(backdrop)
            overlay.add_overlay(popup)
            win.set_child(overlay)
        else:
            win.set_child(popup)

    # ----- data ----------------------------------------------------------------
    def reload(self):
        run_bg(history, self.fill)

    def fill(self, items):
        while (child := self.list.get_first_child()) is not None:
            self.list.remove(child)
        for pin in self.pins:
            if isinstance(pin, str):
                self.list.append(Item(self, pin, pinned=True))
            else:
                self.list.append(Item(self, pin["preview"], pinned=True,
                                      image=os.path.join(PIN_IMAGES, pin["image"])))
        pinned = {pin_key(p) for p in self.pins}
        for line, cid, preview in items:
            if preview in pinned:
                continue
            self.list.append(Item(self, preview, line, cid))
        self.total = len(items)
        self.count.set_label(f"{self.total} items" + (f" · {len(self.pins)} pinned" if self.pins else ""))
        self.refilter()

    def visible(self, row):
        if self.filter == "pinned" and not row.pinned:
            return False
        if self.filter == "text" and row.kind in ("image", "link"):
            return False
        if self.filter in ("link", "code", "image") and row.kind != self.filter:
            return False
        if self.query:
            return row.kind != "image" and self.query in row.text.lower() or \
                (row.kind == "image" and self.query in "image picture screenshot png")
        return True

    def on_search(self):
        self.query = self.search.get_text().strip().lower()
        self.refilter()

    def set_filter(self, key, reload=False):
        self.filter = key
        for k, b in self.chip_btns.items():
            (b.add_css_class if k == key else b.remove_css_class)("active")
        self.refilter()

    def refilter(self):
        self.list.invalidate_filter()
        first = self.first_row()
        self.scroll.set_visible(first is not None)
        self.empty.set_visible(first is None)
        self.empty.set_label("No match" if self.query else "Nothing here yet — copy something!")
        if first is not None:
            self.list.select_row(first)
            self.scroll.get_vadjustment().set_value(0)

    def first_row(self):
        row = self.list.get_first_child()
        while row is not None:
            if isinstance(row, Item) and row.get_child_visible() and self.visible(row):
                return row
            row = row.get_next_sibling()
        return None

    # ----- actions ---------------------------------------------------------------
    def put_on_clipboard(self, row):
        mime = []
        if row.image:                           # a pinned picture
            try:
                with open(row.image, "rb") as f:
                    data = f.read()
            except OSError:
                return False
            ext = row.image.rsplit(".", 1)[-1]
            mime = ["--type", IMG_TYPES.get(ext, "image/png")]
        elif row.line is None:                  # a pinned text
            data = row.text.encode()
        else:
            data = decode(row.line)
        if not data:
            return False
        try:
            p = subprocess.Popen(["wl-copy", *mime], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            p.communicate(data, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return True

    def paste_row(self, row):
        if row is None:
            return
        if self.put_on_clipboard(row):
            self.win.close()
            GLib.timeout_add(180, self.paste)

    def copy_only(self, row):
        if self.put_on_clipboard(row):
            self.count.set_label("copied ✓")
            GLib.timeout_add(1200, lambda: (self.count.set_label(
                f"{self.total} items" + (f" · {len(self.pins)} pinned" if self.pins else "")), False)[1])

    @staticmethod
    def paste():
        """Press the paste keys in the app that has the keyboard again."""
        try:
            info = json.loads(subprocess.run(["hyprctl", "-j", "activewindow"], capture_output=True,
                                             text=True, timeout=2).stdout or "{}")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return False
        cls = (info.get("class") or "").lower()
        if cls:
            mods = "CTRL SHIFT" if any(t in cls for t in TERMINALS) else "CTRL"
            subprocess.Popen(["hyprctl", "dispatch", f'hl.dsp.send_shortcut({{ mods = "{mods}", key = "V" }})'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False

    def unpin(self, row):
        for p in self.pins:
            if pin_key(p) == row.text and not isinstance(p, str):
                try:
                    os.remove(os.path.join(PIN_IMAGES, p["image"]))
                except OSError:
                    pass
        self.pins = [p for p in self.pins if pin_key(p) != row.text]
        save_pins(self.pins)

    def toggle_pin(self, row):
        if row.pinned:
            self.unpin(row)
        elif row.kind == "image":
            data = decode(row.line) if row.line else b""
            if not data:
                return
            try:
                pin = pin_image(data, row.text)
            except OSError:
                return
            self.pins = [pin] + [p for p in self.pins if pin_key(p) != row.text]
            save_pins(self.pins)
        else:
            full = row.text if row.line is None else decode(row.line).decode("utf-8", "replace")
            self.pins = [full] + [p for p in self.pins if pin_key(p) != full]
            save_pins(self.pins)
        self.reload()

    def delete(self, row):
        if row.pinned:
            self.unpin(row)
        elif row.line:
            try:
                subprocess.run(["cliphist", "delete"], input=row.line.encode(), timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            if row.cid:
                try:
                    os.remove(os.path.join(CACHE, f"{row.cid}.img"))
                except OSError:
                    pass
        nxt = row.get_next_sibling()
        self.list.remove(row)
        self.total = max(0, getattr(self, "total", 1) - (0 if row.pinned else 1))
        self.count.set_label(f"{self.total} items" + (f" · {len(self.pins)} pinned" if self.pins else ""))
        if nxt is not None:
            self.list.select_row(nxt)
        self.refilter() if nxt is None else None

    def clear_all(self):
        if not self.confirm_clear:
            self.confirm_clear = True
            self.clear_btn.set_label(f"{I_TRASH}  Click again to clear")
            self.clear_btn.add_css_class("confirm")
            GLib.timeout_add(3000, lambda: (self.reset_clear(), False)[1])
            return
        try:
            subprocess.run(["cliphist", "wipe"], timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for f in os.listdir(CACHE) if os.path.isdir(CACHE) else []:
            try:
                os.remove(os.path.join(CACHE, f))
            except OSError:
                pass
        self.reset_clear()
        self.reload()

    def reset_clear(self):
        self.confirm_clear = False
        self.clear_btn.set_label(f"{I_TRASH}  Clear all")
        self.clear_btn.remove_css_class("confirm")

    # ----- keys ------------------------------------------------------------------
    def on_search_key(self, _ctl, keyval, _code, _state):
        if keyval == Gdk.KEY_Down:
            row = self.list.get_selected_row() or self.first_row()
            if row is not None:
                row.grab_focus()
                return True
        return False

    def on_key(self, _ctl, keyval, _code, state):
        if keyval == Gdk.KEY_Escape:
            if self.search.get_text():
                self.search.set_text("")
                self.search.grab_focus()
            else:
                self.win.close()
            return True
        focus = self.win.get_focus()
        in_list = focus is not None and (focus is self.list or focus.is_ancestor(self.list))
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        # Tab / Shift+Tab: next / previous filter; Alt+1..6: straight to one
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab) and not ctrl:
            keys = [k for k, _ in self.FILTERS]
            step = -1 if keyval == Gdk.KEY_ISO_Left_Tab or state & Gdk.ModifierType.SHIFT_MASK else 1
            self.set_filter(keys[(keys.index(self.filter) + step) % len(keys)])
            return True
        if state & Gdk.ModifierType.ALT_MASK and Gdk.KEY_1 <= keyval < Gdk.KEY_1 + len(self.FILTERS):
            self.set_filter(self.FILTERS[keyval - Gdk.KEY_1][0])
            return True
        # Ctrl+P: pin / unpin the selected item (the first one while typing)
        if ctrl and keyval in (Gdk.KEY_p, Gdk.KEY_P):
            row = (self.list.get_selected_row() if in_list else None) or self.first_row()
            if row is not None:
                self.toggle_pin(row)
            return True
        if keyval == Gdk.KEY_Delete and in_list:
            row = self.list.get_selected_row()
            if row is not None:
                self.delete(row)
            return True
        if in_list and keyval == Gdk.KEY_Up:
            row = self.list.get_selected_row()
            if row is not None and row is self.first_row():
                self.search.grab_focus()
                return True
        # typing while the list has focus goes to the search box
        ch = Gdk.keyval_to_unicode(keyval)
        if in_list and ch and chr(ch).isprintable() and not (state & Gdk.ModifierType.CONTROL_MASK):
            self.search.grab_focus()
            self.search.set_text(self.search.get_text() + chr(ch))
            self.search.set_position(-1)
            return True
        return False


if __name__ == "__main__":
    sys.exit(Clipboard().run([sys.argv[0]]))
