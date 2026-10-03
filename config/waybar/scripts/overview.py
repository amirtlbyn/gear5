#!/usr/bin/env python3
"""
Overview (SUPER+Tab): every desk that has windows, one row each, with a
thumbnail card for each window; then the minimized windows.

  overview.py [THEME] [--hidden]

A click or Enter on a card goes to that window's desk (every screen switches)
and focuses it; a minimized one comes back. 1-9 and 0 go to desk 1-10. Type to
filter by title or app; arrows move the selection. Esc or a click on the
backdrop closes it. Stays running hidden, so it opens instantly.
"""
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
if __name__ == "__main__" and not os.environ.get("OVERVIEW_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["OVERVIEW_PRELOADED"] = "1"
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
import scrolling  # noqa: E402
import thumbs  # noqa: E402

THEME = (
    sys.argv[1]
    if __name__ == "__main__" and len(sys.argv) > 1 and not sys.argv[1].startswith("--")
    else palette.current()
)
DESKS = 10  # as hyprland.lua: each screen owns 10 workspaces, desk = (id - 1) % 10 + 1
COLUMNS = 5
CARD_W = 200
THUMB_H = 110
MINIMIZED = "special:minimized"
THUMB_DIR = thumbs.thumb_dir("overview")
# live_overview.sh times the open with 20 windows without opening 20 real ones
FAKE_CLIENTS = os.environ.get("OVERVIEW_CLIENTS")

P = palette.load(THEME)
OPENING_MS = 300  # cards drawn this soon after an open scale in (as the picker's)

CSS = fonts.swap(
    "".join(f"@define-color {k} {v};\n" for k, v in P.items())
    + """
window.overview { background: transparent; }
.backdrop { background: alpha(black, 0.6); }
.popup {
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif; font-weight: bold;
}
entry.search {
  background: alpha(@bg0, 0.9); color: @fg; border: none; box-shadow: none; outline: none;
  border-radius: 14px; border-bottom: 3px solid @edge; padding: 6px 14px; min-height: 46px;
  font-size: 16px; min-width: 360px;
}
.desk-name {
  color: @grey; font-size: 22px; min-width: 56px; margin-top: 8px;
}
.desk-name.current { color: @green; }
.desk-name.minimized { font-size: 13px; }
flowbox { background: transparent; }
flowbox > flowboxchild { padding: 0; margin: 8px; }
flowbox > flowboxchild:focus { outline: none; }
/* no drop shadow, unlike the picker's cards: 20 blurred shadows made the first
   frame up to 2x slower (OVERVIEW-6) */
.card {
  background: @bg0; border-radius: 16px; border: 1px solid alpha(@fg, 0.07);
  border-bottom: 3px solid @edge; padding: 8px;
}
.card:hover { background: @bg1; }
.card.selected { background: @bg2; box-shadow: inset 0 0 0 2px @green; }
.card-thumb { background: @bg_dim; border-radius: 10px; min-width: 200px; min-height: 110px; }
.card-placeholder { color: @grey; font-size: 40px; }
.card-title { font-size: 12px; }
.card-cls { color: @grey; font-weight: normal; font-size: 10px; }
.empty-desk { color: @grey; font-weight: normal; font-size: 12px; margin: 8px; }
@keyframes card-in { from { opacity: 0; transform: scale(0.94); } to { opacity: 1; transform: none; } }
.opening .card { animation: card-in 160ms ease-out; }
"""
)


# ---------------------------------------------------------------------------
# pure logic (no display needed) — see tests/test_overview.py
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


def read_json(argv, fake=None):
    try:
        if fake:
            with open(fake) as f:
                return json.load(f)
        return json.loads(run(argv) or "[]")
    except (OSError, ValueError):
        return []


def read_clients():
    return read_json(["hyprctl", "-j", "clients"], FAKE_CLIENTS)


def read_monitors():
    return read_json(["hyprctl", "-j", "monitors"])


def desk_of(workspace_id):
    """The desk (1-10) of a workspace id, as hyprland.lua's deskOf; None for special ones."""
    return (workspace_id - 1) % DESKS + 1 if workspace_id >= 1 else None


def current_desk(monitors):
    focused = next((m for m in monitors if m.get("focused")), monitors[0] if monitors else None)
    ws = ((focused or {}).get("activeWorkspace") or {}).get("id", 0)
    return desk_of(ws) or 1


def desk_rows(clients, monitors, current):
    """OVERVIEW-2: [(desk, windows)] — desk is 1-10, or "min" for the minimized row.
    One row per desk with windows, plus the current desk (maybe empty), in desk
    order, then the minimized windows. In a row: by screen (left to right), then
    top to bottom, then left to right. Windows on other special desks (a
    scratchpad) and unmapped ones are left out."""
    screen_x = {m.get("id"): m.get("x", 0) for m in monitors}

    def place(c):
        x, y = (c.get("at") or [0, 0])[:2]
        return (screen_x.get(c.get("monitor"), 0), y, x)

    by_desk, minimized = {}, []
    for c in clients:
        ws = c.get("workspace") or {}
        if ws.get("name") == MINIMIZED:
            minimized.append(c)
        elif c.get("mapped", True) and (d := desk_of(ws.get("id", 0))):
            by_desk.setdefault(d, []).append(c)
    by_desk.setdefault(current, [])
    rows = [(d, sorted(by_desk[d], key=place)) for d in sorted(by_desk)]
    if minimized:
        rows.append(("min", sorted(minimized, key=place)))
    return rows


def matches(client, words):
    text = f"{client.get('title', '')} {client.get('class', '')}".lower()
    return all(w in text for w in words)


def filter_rows(rows, text):
    """OVERVIEW-4: with a filter, only the windows that have every typed word in
    their title or app, and only the rows that still have one."""
    words = text.lower().split()
    if not words:
        return rows
    kept = [(d, [c for c in wins if matches(c, words)]) for d, wins in rows]
    return [(d, wins) for d, wins in kept if wins]


def desk_for_digit(digit):
    """OVERVIEW-4: keys 1-9 are desks 1-9, and 0 is desk 10."""
    return DESKS if digit == 0 else digit


def next_line(positions, index, step):
    """NAV-2: Down (step 1) / Up (step -1) from card `index`: the card nearest in x
    on the next / previous line, where a line is the cards with the same top (y) —
    a desk's wrapped second line is a line too. At the last / first line: index."""
    x, y = positions[index]
    tops = sorted({top for _, top in positions})
    to = tops.index(y) + step
    if not 0 <= to < len(tops):
        return index
    line = [i for i, (_, top) in enumerate(positions) if top == tops[to]]
    return min(line, key=lambda i: abs(positions[i][0] - x))


def checked(address):
    """INV-1: the address, if it has hyprctl's shape; it goes into Lua text below."""
    if not re.fullmatch(r"0x[0-9a-f]+", address or ""):
        raise ValueError(f"not a window address: {address!r}")
    return address


def go_cmd(address):
    return ["hyprctl", "eval", f'goToWindow("{checked(address)}")']


def desk_cmd(n):
    if not 1 <= n <= DESKS:
        raise ValueError(f"no desk {n!r}")
    return ["hyprctl", "eval", f"desk({n})"]


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


class Card(Gtk.FlowBoxChild):
    """One window: a thumbnail (or its app icon until the capture arrives), its
    title and its app."""

    def __init__(self, app, client):
        super().__init__()
        self.client = client
        self.address = client.get("address", "")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("card")
        self.card_box = box
        # the card's size comes from this fixed box, not from the capture: a
        # Picture asks for its image's size, so wide windows made wide cards
        overlay = Gtk.Overlay()
        frame = Gtk.Box()
        frame.add_css_class("card-thumb")
        frame.set_size_request(CARD_W, THUMB_H)
        overlay.set_child(frame)
        self.thumb = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        self.thumb.add_css_class("card-thumb")
        overlay.add_overlay(self.thumb)
        overlay.set_clip_overlay(self.thumb, True)
        self.placeholder = Gtk.Image.new_from_gicon(app.window_icon(client))
        self.placeholder.set_pixel_size(40)
        self.placeholder.add_css_class("card-placeholder")
        self.placeholder.set_halign(Gtk.Align.CENTER)
        self.placeholder.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.placeholder)
        box.append(overlay)
        if self.address in app.textures:
            self.set_thumbnail(app.textures[self.address])
        box.append(
            label(client.get("title", ""), "card-title", xalign=0,
                  ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=1)
        )
        box.append(
            label(client.get("class", ""), "card-cls", xalign=0,
                  ellipsize=Pango.EllipsizeMode.END, max_width_chars=1)
        )
        self.set_child(box)

    def set_selected(self, on):
        (self.card_box.add_css_class if on else self.card_box.remove_css_class)("selected")

    def set_thumbnail(self, texture):
        self.thumb.set_paintable(texture)
        self.placeholder.set_visible(False)


class Overview(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.local.overview")
        self.win = None
        self.by_class = None
        self.rows = []  # every desk row: [(desk, windows)]
        self.grid = []  # the drawn rows: a list of Card lists, top to bottom
        self.cards = []  # the same cards, one flat list (selection order)
        self.textures = {}  # address -> its captured thumbnail, kept while open
        self.current = 1
        self.selected = 0
        self.closed_at = 0
        self.opening_timer = 0
        self.paint_hook = None  # (frame clock, handler) until the first frame of an open
        self.start_hidden = "--hidden" in sys.argv

    def do_activate(self):
        if self.win is None:
            self.hold()  # keep running hidden, so the next open is instant
            self.build()
            self.load_apps()  # now, not on the first open: that one must be fast too
            if self.start_hidden:
                return
        if self.win.get_visible():
            self.leave()
        elif GLib.get_monotonic_time() - self.closed_at > 400_000:
            # the key press that just closed it also reaches here: ignore it
            self.show_popup()

    # ----- data ----------------------------------------------------------
    def window_icon(self, client):
        cls = (client.get("class") or "").lower()
        app = (self.by_class or {}).get(cls)
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
        monitors = read_monitors()
        self.current = current_desk(monitors)
        self.rows = desk_rows(read_clients(), monitors, self.current)
        self.textures = {}
        self.search.set_text("")
        self.mark_opening()
        self.render()
        self.win.present()
        self.search.grab_focus()
        self.after_first_frame(self.start_thumbnails)

    def after_first_frame(self, then):
        """Run then() once the open is on the screen: 20 captures started with the
        open kept Hyprland busy copying windows while it should map this one
        (OVERVIEW-6). Without a frame clock (not realized, as in the tests): now."""
        clock = self.win.get_frame_clock()
        if self.paint_hook:  # an open that closed before its first frame
            self.paint_hook[0].disconnect(self.paint_hook[1])
            self.paint_hook = None
        if clock is None:
            then()
            return

        def painted(clock):
            clock.disconnect(self.paint_hook[1])
            self.paint_hook = None
            if self.win.get_visible():
                then()

        self.paint_hook = (clock, clock.connect("after-paint", painted))

    def mark_opening(self):
        if self.opening_timer:
            GLib.source_remove(self.opening_timer)
        self.list_box.add_css_class("opening")

        def done():
            self.opening_timer = 0
            self.list_box.remove_css_class("opening")
            return False

        self.opening_timer = GLib.timeout_add(OPENING_MS, done)

    def leave(self, action=None):
        """INV-2: every way out ends here, so the keyboard is always released."""
        try:
            if action is not None:
                action()
        finally:
            self.closed_at = GLib.get_monotonic_time()
            if self.win is not None:
                self.win.set_visible(False)
            self.drop_cards()

    def drop_cards(self):
        """OVERVIEW-5: keep nothing while hidden; show_popup reads and builds again."""
        self.textures = {}
        self.clear_rows()
        self.rows = []

    def clear_rows(self):
        while (child := self.list_box.get_first_child()) is not None:
            self.list_box.remove(child)
        self.grid, self.cards = [], []

    def on_close(self, win):
        self.leave()
        return True

    # ----- rendering -------------------------------------------------------
    def render(self):
        text = self.search.get_text()
        self.clear_rows()
        for desk, windows in filter_rows(self.rows, text):
            row = Gtk.Box(spacing=8)
            name = label("Minimized" if desk == "min" else str(desk), "desk-name",
                         valign=Gtk.Align.START, xalign=1)
            if desk == "min":
                name.add_css_class("minimized")
            if desk == self.current:
                name.add_css_class("current")
            row.append(name)
            if not windows:
                row.append(label("Nothing on this desk", "empty-desk", valign=Gtk.Align.CENTER))
                self.list_box.append(row)
                continue
            flow = Gtk.FlowBox(
                selection_mode=Gtk.SelectionMode.NONE,
                homogeneous=True,
                # as wide as its cards (up to COLUMNS), as the picker's fit_columns
                min_children_per_line=min(COLUMNS, len(windows)),
                max_children_per_line=COLUMNS,
                activate_on_single_click=True,
                valign=Gtk.Align.START,
                halign=Gtk.Align.START,  # every card the same size, in every row
            )
            flow.connect("child-activated", lambda _f, card: self.pick(card))
            cards = []
            for client in windows:
                card = Card(self, client)
                flow.append(card)
                cards.append(card)
            row.append(flow)
            self.list_box.append(row)
            self.grid.append(cards)
            self.cards += cards
        self.select(0)

    def select(self, index):
        for card in self.cards:
            card.set_selected(False)
        if not self.cards:
            return
        self.selected = max(0, min(len(self.cards) - 1, index))
        self.cards[self.selected].set_selected(True)
        self.reveal(self.cards[self.selected])

    def card_place(self, card):
        """(x, y, height) of a card in the list, or None before GTK has laid it out."""
        ok, rect = card.compute_bounds(self.list_box)
        return (round(rect.get_x()), round(rect.get_y()), rect.get_height()) if ok else None

    def reveal(self, card):
        """NAV-1: scroll the list so the selected card is in view."""
        scrolling.reveal(self.scroll, self.list_box, card)

    def select_row(self, step):
        """Up/Down: the nearest card on the next / previous line on the screen (NAV-2)."""
        if not self.cards:
            return
        places = [self.card_place(c) for c in self.cards]
        if None not in places:
            self.select(next_line([(x, y) for x, y, _ in places], self.selected, step))
            return
        # not laid out yet: by desk rows
        card = self.cards[self.selected]
        r = next(i for i, row in enumerate(self.grid) if card in row)
        col = self.grid[r].index(card)
        to = max(0, min(len(self.grid) - 1, r + step))
        target = self.grid[to][min(col, len(self.grid[to]) - 1)]
        self.select(self.cards.index(target))

    def start_thumbnails(self):
        app = weakref.ref(self)
        for card in self.cards:

            def done(path, address=card.address):
                me = app()
                try:
                    if me and path and me.win.get_visible():  # closed meanwhile: keep nothing
                        texture = Gdk.Texture.new_from_filename(path)
                        me.textures[address] = texture
                        for c in me.cards:
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

            def work(client=card.client, done=done):
                GLib.idle_add(done, thumbs.capture(client, THUMB_DIR))

            threading.Thread(target=work, daemon=True).start()

    # ----- actions -----------------------------------------------------------
    def pick(self, card):
        address = card.address
        self.leave(lambda: spawn(go_cmd(address)))

    def go_to_desk(self, n):
        self.leave(lambda: spawn(desk_cmd(n)))

    # ----- keys --------------------------------------------------------------
    def on_key(self, _ctl, keyval, _code, state):
        try:
            return self._on_key(keyval, state)
        except Exception:
            self.leave()
            raise

    def _on_key(self, keyval, state):
        if keyval == Gdk.KEY_Escape:
            self.leave()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.cards:
                self.pick(self.cards[self.selected])
            return True
        if keyval == Gdk.KEY_Right:
            self.select(self.selected + 1)
            return True
        if keyval == Gdk.KEY_Left:
            self.select(self.selected - 1)
            return True
        if keyval == Gdk.KEY_Down:
            self.select_row(1)
            return True
        if keyval == Gdk.KEY_Up:
            self.select_row(-1)
            return True
        if not self.search.get_text() and Gdk.KEY_0 <= keyval <= Gdk.KEY_9:
            self.go_to_desk(desk_for_digit(keyval - Gdk.KEY_0))
            return True
        if not self.search.has_focus():
            self.search.grab_focus()
        return False

    # ----- layout --------------------------------------------------------
    def build(self):
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )
        win = Gtk.ApplicationWindow(application=self, title="Overview")
        win.add_css_class("overview")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win

        popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, halign=Gtk.Align.CENTER)
        popup.add_css_class("popup")
        self.search = Gtk.SearchEntry(placeholder_text="Type to filter…")
        self.search.add_css_class("search")
        self.search.set_halign(Gtk.Align.CENTER)
        self.search.connect("search-changed", lambda *_: self.render())
        popup.append(self.search)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.scroll = scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            min_content_height=640,
            max_content_height=640,
            min_content_width=(CARD_W + 36) * COLUMNS + 80,
        )
        scroll.set_child(self.list_box)
        popup.append(scroll)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)

        if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
            LS.init_for_window(win)
            LS.set_namespace(win, "overview")
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
    sys.exit(Overview().run([sys.argv[0]]))
