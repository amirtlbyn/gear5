#!/usr/bin/env python3
"""
Emoji picker (SUPER+.), Everforest style.

  emoji-picker.py [THEME] [--hidden]

- Type to search (names and keywords), or browse by category (Tab / Shift+Tab).
- Click an emoji (or Enter for the first match) to put it into the app you were
  using: it is copied and pasted for you. Right-click only copies it.
- Recently used emoji stay on top.
- Stays running hidden after the first use, so it opens instantly.
The emoji list is emoji-data.txt next to this script (Unicode Emoji 18.0).
"""
import json
import os
import subprocess
import sys

LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if not os.environ.get("EMOJI_PICKER_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["EMOJI_PICKER_PRELOADED"] = "1"
    if lib:
        old = os.environ.get("LD_PRELOAD", "")
        os.environ["LD_PRELOAD"] = lib + (":" + old if old else "")
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LS  # noqa: E402
except (ValueError, ImportError):
    LS = None

import palette  # noqa: E402

import popup_backdrop  # noqa: E402

THEME = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else palette.current()
WIDTH = 500
COLUMNS = 9
# Unicode Emoji 18.0 + CLDR keywords (lines: emoji, category, name, search words)
SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emoji-data.txt")
RECENT_FILE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                           "emoji-picker", "recent.json")
RECENT_MAX = 18
# terminals paste with Ctrl+Shift+V
TERMINALS = ("kitty", "ghostty", "foot", "alacritty", "wezterm", "ptyxis", "terminal", "konsole", "tilix")

# the list is in Unicode order: each category starts at its first emoji
CATEGORIES = [("😀", "Smileys"), ("👋", "People"), ("🐵", "Animals & nature"), ("🍇", "Food & drink"),
              ("🌍", "Travel & places"), ("🎃", "Activities"), ("👓", "Objects"), ("🏧", "Symbols"),
              ("🏁", "Flags")]

P = palette.load(THEME)

CSS = "".join(f"@define-color {k} {v};\n" for k, v in P.items()) + """
window.emoji-picker { background: transparent; }
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
  border-radius: 14px; border-bottom: 3px solid @edge; padding: 4px 12px; min-height: 40px; font-size: 15px;
}
.cats { margin: 10px 0 6px 0; }
.cats button {
  background: transparent; border: none; box-shadow: none; border-radius: 12px;
  padding: 4px 0; min-height: 0; font-size: 20px; opacity: 0.55;
}
.cats button:hover { background: alpha(@fg, 0.06); opacity: 0.9; }
.cats button.active { background: alpha(@green, 0.18); opacity: 1; box-shadow: inset 0 -3px 0 @green; }
.section { color: @grey; font-size: 11px; letter-spacing: 2px; margin: 8px 6px 4px 6px; }
flowbox { background: transparent; }
flowbox > flowboxchild {
  border-radius: 12px; padding: 4px 0; min-height: 40px;
  font-family: "Noto Color Emoji", "Twemoji", sans-serif;
}
flowbox > flowboxchild:hover { background: alpha(@fg, 0.08); }
flowbox > flowboxchild:focus, flowbox > flowboxchild:selected { background: alpha(@green, 0.22); outline: none; }
.emoji { font-size: 26px; }
.preview { background: @bg1; border-radius: 16px; border-bottom: 3px solid @edge; padding: 8px 12px; margin-top: 10px; }
.preview-emoji { font-size: 34px; font-family: "Noto Color Emoji", "Twemoji", sans-serif; min-width: 48px; }
.preview-name { font-size: 14px; }
.preview-hint { color: @grey; font-weight: normal; font-size: 11px; }
.empty { color: @grey; font-weight: normal; padding: 30px; }
.toast { color: @green; font-size: 12px; }
"""


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def load_emoji():
    """[(emoji, name, search text, category index)]"""
    try:
        with open(SOURCE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        parts = line.split("\t")
        if line.startswith("# ") or len(parts) != 4:   # "#️⃣" is an emoji, not a comment
            continue
        ch, cat, name, words = parts
        out.append((ch, name, (words + " " + ch).lower(), int(cat)))
    return out


def load_recent():
    try:
        with open(RECENT_FILE) as f:
            return [e for e in json.load(f) if isinstance(e, str)][:RECENT_MAX]
    except (OSError, ValueError):
        return []


def save_recent(items):
    try:
        os.makedirs(os.path.dirname(RECENT_FILE), exist_ok=True)
        with open(RECENT_FILE, "w") as f:
            json.dump(items[:RECENT_MAX], f)
    except OSError:
        pass


def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
class Picker(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.local.emojipicker")
        self.win = None
        self.data = load_emoji()
        self.names = {e: n for e, n, _w, _c in self.data}
        self.recent = load_recent()
        self.cat = None          # None = everything
        self.query = []
        self.search_seq = 0

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
        self.set_cat(None)
        self.render_recent()
        self.toast.set_label("")
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
        win = Gtk.ApplicationWindow(application=self, title="Emoji")
        win.add_css_class("emoji-picker")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win

        popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.add_css_class("popup")
        popup.set_size_request(WIDTH, -1)

        self.search = Gtk.SearchEntry(placeholder_text="Search emoji — heart, cat, party, fire…")
        self.search.add_css_class("search")
        self.search.connect("search-changed", lambda *_: self.on_search())
        self.search.connect("activate", lambda *_: self.pick_first())
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_search_key)
        self.search.add_controller(keys)
        popup.append(self.search)

        cats = Gtk.Box(homogeneous=True)
        cats.add_css_class("cats")
        self.cat_btns = []
        all_btn = Gtk.Button(label="✨", tooltip_text="All")
        all_btn.connect("clicked", lambda *_: self.set_cat(None))
        cats.append(all_btn)
        self.cat_btns.append((None, all_btn))
        for i, (first, name) in enumerate(CATEGORIES):
            b = Gtk.Button(label=first, tooltip_text=name)
            b.connect("clicked", lambda _b, i=i: self.set_cat(i))
            cats.append(b)
            self.cat_btns.append((i, b))
        popup.append(cats)

        # recently used
        self.recent_title = label("RECENTLY USED", "section", xalign=0)
        popup.append(self.recent_title)
        self.recent_box = self.make_flow()
        popup.append(self.recent_box)

        self.grid_title = label("ALL", "section", xalign=0)
        popup.append(self.grid_title)
        self.flow = self.make_flow()
        for e, name, _w, _c in self.data:
            self.flow.append(self.make_child(e, name))
        self.flow.set_filter_func(self.visible)
        self.scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=300,
                                         max_content_height=300, propagate_natural_height=False)
        self.scroll.set_child(self.flow)
        popup.append(self.scroll)
        self.empty = label("No emoji found", "empty")
        self.empty.set_visible(False)
        popup.append(self.empty)

        prev = Gtk.Box(spacing=12)
        prev.add_css_class("preview")
        # fixed widths: a longer name must not widen the popup, or the grid moves
        # under the mouse and hovering flips between two emoji forever
        self.p_emoji = label("😀", "preview-emoji", ellipsize=Pango.EllipsizeMode.END, max_width_chars=1)
        self.p_emoji.set_size_request(56, -1)
        prev.append(self.p_emoji)
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        self.p_name = label("Pick an emoji", "preview-name", xalign=0, ellipsize=Pango.EllipsizeMode.END,
                            max_width_chars=1)
        txt.append(self.p_name)
        txt.append(label("Enter pastes · right-click copies · Tab category", "preview-hint", xalign=0,
                         ellipsize=Pango.EllipsizeMode.END, max_width_chars=1))
        prev.append(txt)
        self.toast = label(css="toast")
        prev.append(self.toast)
        popup.append(prev)

        wkeys = Gtk.EventControllerKey()
        wkeys.connect("key-pressed", self.on_key)
        win.add_controller(wkeys)
        # Esc first (the search box would otherwise swallow it)
        esc = Gtk.EventControllerKey()
        esc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        esc.connect("key-pressed", self.on_escape)
        win.add_controller(esc)
        # arrows in the grid (the FlowBox's own cursor keys don't move here)
        arrows = Gtk.EventControllerKey()
        arrows.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        arrows.connect("key-pressed", self.on_arrow)
        win.add_controller(arrows)

        if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
            LS.init_for_window(win)
            LS.set_namespace(win, "emoji-picker")
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

    def make_flow(self):
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                           min_children_per_line=COLUMNS, max_children_per_line=COLUMNS,
                           activate_on_single_click=True, column_spacing=2, row_spacing=2)
        flow.connect("child-activated", lambda _f, child: self.pick(child.emoji))
        return flow

    def make_child(self, e, name):
        child = Gtk.FlowBoxChild()
        child.emoji = e
        child.set_child(label(e, "emoji"))
        child.set_tooltip_text(name)
        hover = Gtk.EventControllerMotion()
        hover.connect("enter", lambda *_: self.show_preview(e))
        child.add_controller(hover)
        focus = Gtk.EventControllerFocus()
        focus.connect("enter", lambda *_: self.show_preview(e))
        child.add_controller(focus)
        right = Gtk.GestureClick(button=3)
        right.connect("pressed", lambda *_: self.copy_only(e))
        child.add_controller(right)
        return child

    # ----- filtering ---------------------------------------------------------
    def visible(self, child):
        i = child.get_index()
        _e, _n, words, cat = self.data[i]
        if self.query:
            return all(q in words for q in self.query)
        return self.cat is None or cat == self.cat

    def on_search(self):
        self.search_seq += 1
        seq = self.search_seq

        def apply():
            if seq != self.search_seq:
                return False
            self.query = self.search.get_text().lower().split()
            self.refilter()
            return False
        GLib.timeout_add(60, apply)

    def set_cat(self, cat):
        self.cat = cat
        for c, b in self.cat_btns:
            (b.add_css_class if c == cat else b.remove_css_class)("active")
        if self.search.get_text():
            self.search.set_text("")     # a category click leaves the search
            self.query = []
        self.refilter()
        self.scroll.get_vadjustment().set_value(0)

    def refilter(self):
        self.flow.invalidate_filter()
        searching = bool(self.query)
        self.grid_title.set_label("RESULTS" if searching else
                                  (CATEGORIES[self.cat][1].upper() if self.cat is not None else "ALL"))
        show_recent = not searching and self.cat is None and bool(self.recent)
        self.recent_title.set_visible(show_recent)
        self.recent_box.set_visible(show_recent)
        first = self.first_visible()
        self.scroll.set_visible(first is not None)
        self.empty.set_visible(first is None)
        if first is not None and searching:
            self.show_preview(first.emoji)

    def first_visible(self):
        child = self.flow.get_first_child()
        while child is not None:
            if child.get_child_visible() and self.visible(child):
                return child
            child = child.get_next_sibling()
        return None

    def render_recent(self):
        while (child := self.recent_box.get_first_child()) is not None:
            self.recent_box.remove(child)
        for e in self.recent:
            self.recent_box.append(self.make_child(e, self.names.get(e, e)))
        show = bool(self.recent) and not self.query and self.cat is None
        self.recent_title.set_visible(show)
        self.recent_box.set_visible(show)

    def show_preview(self, e):
        self.p_emoji.set_label(e)
        self.p_name.set_label(self.names.get(e, e))

    # ----- picking -----------------------------------------------------------
    def remember(self, e):
        self.recent = [e] + [r for r in self.recent if r != e]
        save_recent(self.recent)
        self.render_recent()

    def copy(self, e):
        try:
            subprocess.Popen(["wl-copy", "--", e], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def copy_only(self, e):
        self.copy(e)
        self.remember(e)
        self.toast.set_label(f"{e} copied")
        GLib.timeout_add(1500, lambda: (self.toast.set_label(""), False)[1])

    def pick(self, e):
        self.copy(e)
        self.remember(e)
        self.win.close()
        # once the app you were in has the keyboard back, paste into it
        GLib.timeout_add(180, self.paste)

    @staticmethod
    def paste():
        try:
            info = json.loads(subprocess.run(["hyprctl", "-j", "activewindow"], capture_output=True,
                                             text=True, timeout=2).stdout or "{}")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return False
        cls = (info.get("class") or "").lower()
        if not cls:
            return False
        mods = "CTRL SHIFT" if any(t in cls for t in TERMINALS) else "CTRL"
        subprocess.Popen(["hyprctl", "dispatch", f'hl.dsp.send_shortcut({{ mods = "{mods}", key = "V" }})'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False

    def pick_first(self):
        first = self.first_visible()
        if first is not None:
            self.pick(first.emoji)

    # ----- keys --------------------------------------------------------------
    def on_search_key(self, _ctl, keyval, _code, _state):
        if keyval == Gdk.KEY_Down:
            first = self.recent_box.get_first_child() if self.recent_box.get_visible() else self.first_visible()
            if first is not None:
                first.grab_focus()
                return True
        return False

    def shown(self, flow):
        """The emoji a grid shows now, in order."""
        out = []
        child = flow.get_first_child()
        while child is not None:
            if flow is not self.flow or self.visible(child):
                out.append(child)
            child = child.get_next_sibling()
        return out

    def on_arrow(self, _ctl, keyval, _code, _state):
        step = {Gdk.KEY_Left: -1, Gdk.KEY_Right: 1, Gdk.KEY_Up: -COLUMNS, Gdk.KEY_Down: COLUMNS}.get(keyval)
        child = self.win.get_focus()
        if step is None or not hasattr(child, "emoji"):
            return False
        # "recently used" and the main grid work as one grid
        grids = [self.shown(b) for b in (self.recent_box, self.flow) if b.get_visible()]
        g = next((k for k, items in enumerate(grids) if child in items), None)
        if g is None:
            return False
        items, i = grids[g], grids[g].index(child)
        prev = grids[g - 1] if g > 0 else []
        after = grids[g + 1] if g + 1 < len(grids) else []
        col, last_row = i % COLUMNS, (len(items) - 1) // COLUMNS
        target = None
        if 0 <= i + step < len(items):
            target = items[i + step]
        elif step == 1:
            target = after[0] if after else None
        elif step == -1:
            target = prev[-1] if prev else None
        elif step > 0:
            if i // COLUMNS < last_row:             # a shorter last row below
                target = items[-1]
            elif after:
                target = after[min(col, len(after) - 1)]
        elif prev:                                  # up, from the top row
            target = prev[min((len(prev) - 1) // COLUMNS * COLUMNS + col, len(prev) - 1)]
        else:
            self.search.grab_focus()
            self.search.set_position(-1)
            return True
        if target is not None:
            target.grab_focus()
        return True

    def on_escape(self, _ctl, keyval, _code, state):
        # Tab / Shift+Tab: next / previous category ("All" first)
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            cats = [c for c, _b in self.cat_btns]
            step = -1 if keyval == Gdk.KEY_ISO_Left_Tab or state & Gdk.ModifierType.SHIFT_MASK else 1
            self.set_cat(cats[(cats.index(self.cat) + step) % len(cats)])
            self.search.grab_focus()
            return True
        if keyval != Gdk.KEY_Escape:
            return False
        if self.search.get_text():       # first Esc clears the search, the next one closes
            self.search.set_text("")
            self.search.grab_focus()
        else:
            self.win.close()
        return True

    def on_key(self, _ctl, keyval, _code, _state):
        # typing anywhere goes to the search box
        ch = Gdk.keyval_to_unicode(keyval)
        if ch and chr(ch).isprintable() and not self.search.has_focus():
            self.search.grab_focus()
            self.search.set_text(self.search.get_text() + chr(ch))
            self.search.set_position(-1)
            return True
        return False


if __name__ == "__main__":
    sys.exit(Picker().run([sys.argv[0]]))
