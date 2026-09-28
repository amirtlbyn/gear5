#!/usr/bin/env python3
"""
Minimized windows picker (SUPER+SHIFT+minus, or the bar's minimized counter),
Everforest style — a card with a thumbnail for each hidden window, so two kitty
or two Zen windows are not just two identical text rows.

  minimized-picker.py [THEME] [--hidden]

Newest hidden first. A click, Enter on the selected card, or its number (1-9)
brings that window back onto the desk you're on; arrow keys move the selection;
type to filter by title or app. Delete, middle-click or a card's × closes that
window. Esc or a click on the backdrop closes the picker.
Stays running hidden, so it opens instantly.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if __name__ == "__main__" and not os.environ.get("MINIMIZED_PICKER_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["MINIMIZED_PICKER_PRELOADED"] = "1"
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

import fonts  # noqa: E402
import palette  # noqa: E402
import popup_backdrop  # noqa: E402

# imported by tests through panel.load(): no window, the theme in use
THEME = (
    sys.argv[1]
    if __name__ == "__main__" and len(sys.argv) > 1 and not sys.argv[1].startswith("--")
    else palette.current()
)
COLUMNS = 4
CARD_W = 200
THUMB_H = 110
MAX_NUMBERED = 9
MINIMIZED = "special:minimized"
MINIMIZED_FILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "hypr-minimized")
# captures hold other windows' content: only in the private runtime dir, never a shared /tmp
THUMB_DIR = (
    os.path.join(os.environ["XDG_RUNTIME_DIR"], "minimized-picker")
    if os.environ.get("XDG_RUNTIME_DIR")
    else None
)

ALIASES = {}
P = palette.load(THEME, **ALIASES)

CSS = fonts.swap(
    "".join(f"@define-color {k} {v};\n" for k, v in P.items())
    + """
window.minimized-picker { background: transparent; }
.backdrop { background: alpha(black, 0.6); }
.popup {
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif; font-weight: bold;
}
entry.search {
  background: alpha(@bg0, 0.9); color: @fg; border: none; box-shadow: none; outline: none;
  border-radius: 14px; border-bottom: 3px solid @edge; padding: 6px 14px; min-height: 46px;
  font-size: 16px; min-width: 360px;
}
.empty { color: @fg; font-size: 18px; font-weight: normal; padding: 40px; }
flowbox { background: transparent; }
flowbox > flowboxchild { padding: 0; margin: 8px; }
flowbox > flowboxchild:focus { outline: none; }
.card {
  background: @bg0; border-radius: 16px; border: 1px solid alpha(@fg, 0.07);
  border-bottom: 3px solid @edge; box-shadow: 0 10px 26px alpha(black, 0.35);
  padding: 8px;
}
.card:hover { background: @bg1; }
.card.selected { background: @bg2; box-shadow: inset 0 0 0 2px @green, 0 10px 26px alpha(black, 0.35); }
.card-thumb { background: @bg_dim; border-radius: 10px; min-width: 200px; min-height: 110px; }
.card-placeholder { color: @grey; font-size: 40px; }
.card-title { font-size: 12px; }
.card-cls { color: @grey; font-weight: normal; font-size: 10px; }
.card-num {
  background: alpha(@bg0, 0.85); color: @fg; font-size: 11px; border-radius: 8px;
  padding: 1px 6px; min-width: 0;
}
.card-close {
  background: alpha(@bg0, 0.85); color: @fg; font-size: 11px; border-radius: 8px;
  padding: 0px 6px; min-height: 0; min-width: 0; border: none; box-shadow: none;
}
.card-close:hover { background: @red; color: @on_accent; }
"""
)


# ---------------------------------------------------------------------------
# pure logic (no gi needed): order, filter, number keys, INV-3 — see
# tests/test_minimized_picker.py
# ---------------------------------------------------------------------------
def run(argv, timeout=3):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def spawn(argv):
    try:
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def read_clients():
    try:
        return json.loads(run(["hyprctl", "-j", "clients"]) or "[]")
    except ValueError:
        return []


def is_minimized(c):
    return (c.get("workspace") or {}).get("name") == MINIMIZED


def minimized_windows(clients, order_file=MINIMIZED_FILE):
    """BATPICK-7: the minimized windows, newest hidden first (hyprland.lua keeps
    the order in order_file, oldest to newest)."""
    try:
        with open(order_file) as f:
            order = [line.strip() for line in f if line.strip()]
    except OSError:
        order = []
    rank = {addr: i for i, addr in enumerate(order)}
    return sorted((c for c in clients if is_minimized(c)), key=lambda c: -rank.get(c.get("address"), -1))


def matches(client, words):
    text = f"{client.get('title', '')} {client.get('class', '')}".lower()
    return all(w in text for w in words)


def filter_windows(windows, text):
    """BATPICK-8: typing filters by title and app; every typed word must appear."""
    words = text.lower().split()
    return [c for c in windows if matches(c, words)] if words else list(windows)


def number_target(items, digit):
    """BATPICK-8: the card that number key `digit` (1-9) restores, or None past
    the numbered cards (only the first MAX_NUMBERED cards carry a number)."""
    if not (1 <= digit <= MAX_NUMBERED) or digit > len(items):
        return None
    return items[digit - 1]


def still_minimized(address, clients):
    """INV-3: act on a window only if it is still special:minimized right now.
    Also the one gate before an address goes into a hyprctl eval/dispatch string
    (restore_cmd, close_cmd): anything but hyprctl's own address shape is refused,
    same as launcher.py's window actions."""
    if not re.fullmatch(r"0x[0-9a-f]+", address or ""):
        return False
    return any(c.get("address") == address and is_minimized(c) for c in clients)


def checked(address):
    """The address, if it has hyprctl's shape; it goes into Lua text below."""
    if not re.fullmatch(r"0x[0-9a-f]+", address or ""):
        raise ValueError(f"not a window address: {address!r}")
    return address


def restore_cmd(address):
    return ["hyprctl", "eval", f'restoreMinimized("{checked(address)}")']


def close_cmd(address):
    # closeMinimized checks again inside Hyprland, so a window restored meanwhile stays open (INV-3)
    return ["hyprctl", "eval", f'closeMinimized("{checked(address)}")']


def capture_cmd(stable_id, out_path):
    return ["grim", "-T", stable_id, out_path]


def capture_thumbnail(client, thumb_dir=THUMB_DIR):
    """Run in a worker thread: the captured PNG's path, or None (bad stableId, or
    grim failed — the caller shows the icon placeholder instead)."""
    stable_id = client.get("stableId")
    if not stable_id or not thumb_dir:
        return None
    try:
        os.makedirs(thumb_dir, mode=0o700, exist_ok=True)
        fd, path = tempfile.mkstemp(dir=thumb_dir, suffix=".png")  # one file per capture: no races
        os.close(fd)
    except OSError:
        return None
    try:
        r = subprocess.run(capture_cmd(stable_id, path), capture_output=True, timeout=5)
        if r.returncode == 0 and os.path.getsize(path) > 0:
            return path
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        os.remove(path)
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


class Card(Gtk.FlowBoxChild):
    """One minimized window: a thumbnail (or an icon placeholder), its title,
    app, a number badge (the first MAX_NUMBERED cards only) and a × to close it."""

    def __init__(self, app, client, number):
        super().__init__()
        self.app = app
        self.client = client
        self.address = client.get("address", "")
        self.number = number  # the badge it shows: the key that restores it
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("card")
        self.card_box = box

        overlay = Gtk.Overlay()
        self.thumb = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        self.thumb.add_css_class("card-thumb")
        self.thumb.set_size_request(CARD_W, THUMB_H)
        overlay.set_child(self.thumb)
        self.placeholder = Gtk.Image.new_from_gicon(app.window_icon(client))
        self.placeholder.set_pixel_size(40)
        self.placeholder.add_css_class("card-placeholder")
        self.placeholder.set_halign(Gtk.Align.CENTER)
        self.placeholder.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.placeholder)
        if number is not None:
            num = label(
                str(number),
                "card-num",
                halign=Gtk.Align.START,
                valign=Gtk.Align.START,
                margin_start=6,
                margin_top=6,
            )
            overlay.add_overlay(num)
        close = Gtk.Button(label="✕")
        close.add_css_class("card-close")
        close.set_halign(Gtk.Align.END)
        close.set_valign(Gtk.Align.START)
        close.set_margin_end(6)
        close.set_margin_top(6)
        close.connect("clicked", lambda *_: app.close_window(self))
        overlay.add_overlay(close)
        box.append(overlay)
        if self.address in app.textures:
            self.set_thumbnail(app.textures[self.address])

        title = client.get("title", "")
        cls = client.get("class", "")
        box.append(
            label(title, "card-title", xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=1)
        )
        box.append(label(cls, "card-cls", xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=1))

        self.set_child(box)
        middle = Gtk.GestureClick(button=2)
        middle.connect("pressed", lambda *_: app.close_window(self))
        self.add_controller(middle)

    def set_selected(self, on):
        (self.card_box.add_css_class if on else self.card_box.remove_css_class)("selected")

    def set_thumbnail(self, texture):
        self.thumb.set_paintable(texture)
        self.placeholder.set_visible(False)


class Picker(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.local.minimizedpicker")
        self.win = None
        self.by_class = None
        self.windows = []  # every minimized window, newest first
        self.items = []  # windows kept by the current filter
        self.cards = []  # Card widgets, same order as items
        self.textures = {}  # address -> its captured thumbnail, kept while the picker is open
        self.selected = 0
        self.empty = False
        self.closed_at = 0
        self.start_hidden = "--hidden" in sys.argv

    def do_activate(self):
        if self.win is None:
            self.hold()  # keep running hidden, so the next open is instant
            self.build()
            if self.start_hidden:
                return
        if self.win.get_visible():
            self.leave()
        elif GLib.get_monotonic_time() - self.closed_at > 400_000:
            # the click that just closed it (the bar box, or the SHIFT+minus bind
            # fired twice) also reaches here: ignore it right after a close
            self.show_popup()

    # ----- data ----------------------------------------------------------
    def window_icon(self, client):
        cls = (client.get("class") or "").lower()
        app = (self.by_class or {}).get(cls)
        # a .desktop file with no Icon= gives None, which Gtk.Image refuses
        return (app.get_icon() if app else None) or Gio.ThemedIcon.new(cls or "window")

    def load_apps(self):
        by_class = {}
        for info in Gio.AppInfo.get_all():
            if not isinstance(info, Gio.DesktopAppInfo):
                continue
            wm = (info.get_startup_wm_class() or "").lower()
            aid = (info.get_id() or "").removesuffix(".desktop").lower()
            for key in (wm, aid, aid.rsplit(".", 1)[-1] if aid else ""):
                if key:
                    by_class.setdefault(key, info)
        self.by_class = by_class

    # ----- opening / closing ----------------------------------------------
    def show_popup(self):
        if self.by_class is None:
            self.load_apps()
        self.windows = minimized_windows(read_clients())
        self.textures = {}
        self.search.set_text("")
        self.render(reset=True)
        self.win.present()
        self.search.grab_focus()
        self.start_thumbnails()

    def leave(self, action=None):
        """INV-4: every exit path (restore, Esc, backdrop click, empty state, an
        exception) ends here, so the keyboard is always released."""
        try:
            if action is not None:
                action()
        finally:
            self.closed_at = GLib.get_monotonic_time()
            if self.win is not None:
                self.win.set_visible(False)
            self.drop_cards()

    def drop_cards(self):
        """PH0-4: keep nothing while hidden (the thumbnails took ~150 MB);
        show_popup reads the windows and builds the cards again."""
        self.textures = {}
        while (child := self.flow.get_first_child()) is not None:
            self.flow.remove(child)
        self.cards, self.items, self.windows = [], [], []

    def on_close(self, win):
        self.leave()
        return True

    # ----- rendering -------------------------------------------------------
    def render(self, reset=False):
        text = self.search.get_text()
        self.items = filter_windows(self.windows, text)
        self.empty = not self.windows
        self.empty_box.set_visible(self.empty)
        self.scroll.set_visible(not self.empty)
        self.search.set_visible(not self.empty)
        while (child := self.flow.get_first_child()) is not None:
            self.flow.remove(child)
        self.cards = []
        for i, client in enumerate(self.items):
            # numbers only while the filter is empty: typed digits go to the filter then
            card = Card(self, client, i + 1 if i < MAX_NUMBERED and not text else None)
            self.flow.append(card)
            self.cards.append(card)
        self.fit_columns()
        if reset or self.selected >= len(self.cards):
            self.selected = 0
        self.select(self.selected)

    def fit_columns(self):
        """One row for up to COLUMNS cards, as wide as they are, so the grid stays centered."""
        self.flow.set_min_children_per_line(max(1, min(COLUMNS, len(self.cards))))

    def select(self, index):
        for card in self.cards:
            card.set_selected(False)
        if not self.cards:
            return
        self.selected = max(0, min(len(self.cards) - 1, index))
        self.cards[self.selected].set_selected(True)

    def start_thumbnails(self):
        for card in self.cards:
            client = card.client

            def done(path, address=card.address):
                # the grid may have been drawn again since (a filter, a close):
                # keep the texture for the next draw, and show it on today's card
                try:
                    if path and self.win.get_visible():  # closed meanwhile: keep nothing
                        texture = Gdk.Texture.new_from_filename(path)
                        self.textures[address] = texture
                        for c in self.cards:
                            if c.address == address:
                                c.set_thumbnail(texture)
                except GLib.Error:
                    pass
                finally:
                    if path:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                return False

            def work(client=client, done=done):
                path = capture_thumbnail(client)
                GLib.idle_add(done, path)

            threading.Thread(target=work, daemon=True).start()

    # ----- actions -----------------------------------------------------------
    def restore(self, card):
        address = card.address
        if still_minimized(address, read_clients()):
            self.leave(lambda: spawn(restore_cmd(address)))
        else:
            self.leave()

    def close_window(self, card):
        address = card.address
        if still_minimized(address, read_clients()):
            spawn(close_cmd(address))
        if card in self.cards:
            i = self.cards.index(card)
            self.windows = [c for c in self.windows if c.get("address") != address]
            self.render()  # numbers the cards again, so a number key matches its badge
            self.select(min(i, len(self.cards) - 1))

    # ----- keys / clicks -----------------------------------------------------
    def on_key(self, _ctl, keyval, _code, state):
        try:
            return self._on_key(keyval, state)
        except Exception:
            self.leave()
            raise

    def _on_key(self, keyval, state):
        if self.empty:
            self.leave()
            return True
        if keyval == Gdk.KEY_Escape:
            self.leave()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.cards:
                self.restore(self.cards[self.selected])
            return True
        if keyval == Gdk.KEY_Delete:
            if self.cards:
                self.close_window(self.cards[self.selected])
            return True
        if keyval == Gdk.KEY_Right:
            self.select(self.selected + 1)
            return True
        if keyval == Gdk.KEY_Left:
            self.select(self.selected - 1)
            return True
        if keyval == Gdk.KEY_Down:
            self.select(self.selected + COLUMNS)
            return True
        if keyval == Gdk.KEY_Up:
            self.select(self.selected - COLUMNS)
            return True
        if not self.search.get_text() and Gdk.KEY_1 <= keyval <= Gdk.KEY_9:
            digit = keyval - Gdk.KEY_0
            if number_target(self.items, digit) is not None:
                self.restore(self.cards[digit - 1])
            return True
        if not self.search.has_focus():
            self.search.grab_focus()
        return False

    def on_search(self):
        self.render()

    # ----- layout --------------------------------------------------------
    def build(self):
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )
        win = Gtk.ApplicationWindow(application=self, title="Minimized windows")
        win.add_css_class("minimized-picker")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win

        popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, halign=Gtk.Align.CENTER)
        popup.add_css_class("popup")

        self.search = Gtk.SearchEntry(placeholder_text="Type to filter…")
        self.search.add_css_class("search")
        self.search.set_halign(Gtk.Align.CENTER)
        self.search.connect("search-changed", lambda *_: self.on_search())
        popup.append(self.search)

        self.empty_box = label("Nothing minimized", "empty")
        popup.append(self.empty_box)
        # BATPICK-9: any click closes an empty picker (only the message shows then)
        empty_click = Gtk.GestureClick()
        empty_click.connect("pressed", lambda *_: self.leave() if self.empty else None)
        popup.add_controller(empty_click)

        self.flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            min_children_per_line=1,  # fit_columns sets it to the number of cards
            max_children_per_line=COLUMNS,
            activate_on_single_click=True,
            valign=Gtk.Align.START,
            halign=Gtk.Align.CENTER,
        )
        self.flow.connect("child-activated", lambda _f, card: self.restore(card))
        self.scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            min_content_height=560,
            max_content_height=560,
            min_content_width=CARD_W * COLUMNS + 80,
        )
        self.scroll.set_child(self.flow)
        popup.append(self.scroll)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)

        if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
            LS.init_for_window(win)
            LS.set_namespace(win, "minimized-picker")
            LS.set_layer(win, LS.Layer.OVERLAY)
            for edge in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
                LS.set_anchor(win, edge, True)
            LS.set_exclusive_zone(win, -1)
            LS.set_keyboard_mode(win, LS.KeyboardMode.EXCLUSIVE)
            popup_backdrop.attach(win)  # clicks on the other screens close it too
            backdrop = Gtk.Box(hexpand=True, vexpand=True)
            backdrop.add_css_class("backdrop")
            click = Gtk.GestureClick()
            click.connect("pressed", lambda *_: self.leave())
            backdrop.add_controller(click)
            popup.set_valign(Gtk.Align.CENTER)
            overlay = Gtk.Overlay()
            overlay.set_child(backdrop)
            overlay.add_overlay(popup)
            win.set_child(overlay)
        else:
            win.set_child(popup)
            win.connect("notify::is-active", lambda w, _p: None if w.is_active() else w.close())


if __name__ == "__main__":
    sys.exit(Picker().run([sys.argv[0]]))
