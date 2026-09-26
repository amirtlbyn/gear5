#!/usr/bin/env python3
"""
Display settings (SUPER+P), Everforest style.

  displays.py [THEME] [--hidden]
  displays.py --auto        put back the layout saved for the screens connected now
                            (Hyprland runs this whenever a screen comes or goes)

- Quick modes: Laptop only · Extend · Duplicate · External only.
- Drag the screens on the map to arrange them; they snap edge to edge.
- Per screen: on/off, resolution and refresh rate, scale, rotation, mirror.
- Apply asks "Keep these settings?" and goes back by itself after 15 seconds,
  so a wrong resolution can't leave you stuck.
- What you keep is remembered for that exact set of screens (in
  ~/.config/hypr/displays.json) and comes back whenever you plug them in again.
- The laptop panel stays off while the lid is closed (see hypr/scripts/lid.sh).
"""
import json
import os
import subprocess
import sys

PROFILES = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "hypr",
                        "displays.json")
LID_FLAG = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "hypr-lid-closed")
INTERNAL = ("eDP", "LVDS", "DSI")


# ---------------------------------------------------------------------------
# screens: read, describe, apply (no GTK needed: --auto runs this part only)
# ---------------------------------------------------------------------------
def hyprctl_json(*args):
    try:
        return json.loads(subprocess.run(["hyprctl", "-j", *args], capture_output=True, text=True,
                                         timeout=3).stdout or "[]")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []


def mode_of(m):
    return f"{m['width']}x{m['height']}@{m['refreshRate']:.2f}"


def modes_of(m):
    """Available modes, best first, without duplicates: ["2560x1440@144.00", ...]."""
    seen, out = set(), []
    for s in m.get("availableModes") or []:
        s = s.removesuffix("Hz")
        if s not in seen:
            seen.add(s)
            out.append(s)

    def key(s):
        res, _, hz = s.partition("@")
        w, _, h = res.partition("x")
        return (-int(w) * int(h), -float(hz or 0))
    return sorted(out, key=key) or [mode_of(m)]


class Screen:
    def __init__(self, m):
        self.name = m["name"]
        self.desc = (m.get("description") or "").strip()
        self.ident = self.desc or self.name            # the screen itself, on whatever port
        self.internal = self.name.startswith(INTERNAL)
        self.modes = modes_of(m)
        self.label = "Laptop" if self.internal else \
            " ".join(x for x in ((m.get("make") or "").split()[:1] + [(m.get("model") or "").strip()]) if x) \
            or self.name
        # settings (the popup edits these)
        self.enabled = not m.get("disabled", False)
        self.mode = mode_of(m) if m.get("width") else self.modes[0]
        self.x, self.y = m.get("x", 0), m.get("y", 0)
        self.scale = float(m.get("scale") or 1)
        self.transform = int(m.get("transform") or 0)
        mirror = m.get("mirrorOf") or "none"
        self.mirror = None if mirror in ("none", "") else mirror      # name of the screen it copies

    def size(self):
        """Size on the desktop (after scale and rotation), in logical pixels."""
        res = self.mode.split("@")[0]
        w, _, h = res.partition("x")
        w, h = int(w) / self.scale, int(h) / self.scale
        return (h, w) if self.transform % 2 else (w, h)

    def state(self):
        return dict(enabled=self.enabled, mode=self.mode, x=int(self.x), y=int(self.y),
                    scale=round(self.scale, 3), transform=self.transform, mirror=self.mirror)

    def set_state(self, st):
        self.enabled, self.mode = st["enabled"], st["mode"]
        self.x, self.y, self.scale = st["x"], st["y"], st["scale"]
        self.transform, self.mirror = st["transform"], st.get("mirror")


def read_screens():
    return [Screen(m) for m in hyprctl_json("monitors", "all")
            if not m["name"].startswith(("FALLBACK", "HEADLESS"))]


def lid_closed():
    return os.path.exists(LID_FLAG)


def selector(s):
    # match by description, like hyprland.lua does, so this rule replaces that one
    return f"desc:{s.desc}" if s.desc else s.name


def lua_rules(screens):
    lines = []
    for s in screens:
        on = s.enabled and not (s.internal and lid_closed())
        if not on:
            lines.append(f'hl.monitor({{ output = {json.dumps(selector(s))}, disabled = true }})')
            continue
        spec = (f'output = {json.dumps(selector(s))}, mode = "{s.mode}", position = "{int(s.x)}x{int(s.y)}", '
                f'scale = {s.scale:g}, transform = {s.transform}')
        if s.mirror:
            spec += f', mirror = "{s.mirror}"'
        lines.append(f"hl.monitor({{ {spec} }})")
    return "\n".join(lines)


def apply(screens):
    try:
        subprocess.run(["hyprctl", "eval", lua_rules(screens)], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


# ---- memory ------------------------------------------------------------------
def profile_key(screens):
    return " | ".join(sorted(s.ident for s in screens))


def load_profiles():
    try:
        with open(PROFILES) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_profile(screens):
    profiles = load_profiles()
    by_name = {s.name: s.ident for s in screens}
    entry = {}
    for s in screens:
        st = s.state()
        st["mirror"] = by_name.get(st["mirror"]) if st["mirror"] else None   # remember the screen, not the port
        entry[s.ident] = st
    profiles[profile_key(screens)] = entry
    try:
        os.makedirs(os.path.dirname(PROFILES), exist_ok=True)
        with open(PROFILES + ".tmp", "w") as f:
            json.dump(profiles, f, indent=1)
        os.replace(PROFILES + ".tmp", PROFILES)
    except OSError:
        pass


def saved_layout(screens):
    """The screens with their saved settings, or None if this set is new."""
    entry = load_profiles().get(profile_key(screens))
    if not entry:
        return None
    by_ident = {s.ident: s.name for s in screens}
    for s in screens:
        st = dict(entry.get(s.ident) or s.state())
        if st.get("mirror"):
            st["mirror"] = by_ident.get(st["mirror"])
        if st["mode"] not in s.modes:
            st["mode"] = s.modes[0]
        s.set_state(st)
    return screens


def auto():
    screens = read_screens()
    if not screens:
        return
    now = {s.name: s.state() for s in screens}
    wanted = saved_layout(screens)
    if wanted is None:
        # a set of screens never saved: turn every screen back on, so a rule from
        # another setup (e.g. "External only") can't leave you with a black laptop
        off = [s for s in screens if not s.enabled and not (s.internal and lid_closed())]
        if not off:
            return
        for s in off:
            s.enabled, s.mode, s.mirror = True, s.modes[0], None
            shown = [o for o in screens if o.enabled and o is not s and not o.mirror]
            s.x = max((o.x + o.size()[0] for o in shown), default=0)
            s.y = min((o.y for o in shown), default=0)
        wanted = screens
    if all(s.state() == now[s.name] or (s.internal and lid_closed()) for s in wanted):
        return          # already like that: don't touch anything
    apply(wanted)


if __name__ == "__main__" and "--auto" in sys.argv:
    auto()
    sys.exit(0)


# ---------------------------------------------------------------------------
# the popup
# ---------------------------------------------------------------------------
LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if not os.environ.get("DISPLAYS_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["DISPLAYS_PRELOADED"] = "1"
    if lib:
        old = os.environ.get("LD_PRELOAD", "")
        os.environ["LD_PRELOAD"] = lib + (":" + old if old else "")
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])

import math  # noqa: E402

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LS  # noqa: E402
except (ValueError, ImportError):
    LS = None

import palette  # noqa: E402

import popup_backdrop  # noqa: E402

THEME = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else palette.current()
WIDTH = 520
MAP_H = 230
REVERT_AFTER = 15
SCALES = [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
ROTATIONS = [(0, "Normal"), (1, "Portrait (90°)"), (2, "Upside down"), (3, "Portrait (270°)")]
SNAP = 60          # logical pixels: closer than this to an edge = stick to it

P = palette.load(THEME)

CSS = "".join(f"@define-color {k} {v};\n" for k, v in P.items()) + """
window.displays { background: transparent; }
.backdrop { background: alpha(black, 0.12); }
.popup {
  background: @bg0; color: @fg;
  border-radius: 22px; border: 1px solid alpha(@fg, 0.07);
  box-shadow: 0 22px 50px @shadow, 0 2px 6px alpha(black, 0.25);
  padding: 16px;
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif; font-weight: bold; font-size: 14px;
}
.title { font-size: 19px; }
.title-sub { color: @grey; font-weight: normal; font-size: 12px; }
.section { color: @grey; font-size: 11px; letter-spacing: 2px; margin: 14px 4px 6px 4px; }
.modes button, .chips button {
  background: @bg1; color: @fg; border: none; box-shadow: none; border-radius: 14px;
  border-bottom: 3px solid @edge; padding: 8px 6px; min-height: 0;
}
.modes button:hover, .chips button:hover { background: @bg2; }
.modes button.active, .chips button.active { background: @green; color: @on_accent; border-bottom-color: shade(@green, 0.7); }
.modes .icon { font-size: 22px; }
.modes .mode-name { font-size: 11px; }
.chips button { padding: 4px 12px; border-bottom-width: 2px; font-size: 12px; }
.chips button.off { color: @grey; }
.map { background: @bg1; border-radius: 16px; border-bottom: 3px solid @edge; }
.row { margin: 3px 0; }
.row > label { color: @grey; font-weight: normal; }
.popup dropdown > button {
  background: @bg2; color: @fg; border: none; border-radius: 12px; border-bottom: 3px solid @edge;
  box-shadow: none; padding: 2px 10px; min-height: 30px;
}
popover > contents { background: @bg1; color: @fg; border-radius: 14px; }
popover listview > row:selected, popover listview > row:hover { background: @bg3; }
switch { background: @bg3; border: none; }
switch:checked { background: @green; }
switch slider { background: @fg; border: none; box-shadow: none; }
button.act {
  background: @bg2; color: @fg; border: none; border-radius: 14px; border-bottom: 3px solid @edge;
  box-shadow: none; padding: 8px 18px; min-height: 0;
}
button.act:hover { background: @bg3; }
button.act.primary { background: @green; color: @on_accent; border-bottom-color: shade(@green, 0.7); }
button.act:disabled { opacity: 0.4; }
.confirm { background: alpha(@yellow, 0.15); border-radius: 14px; padding: 10px 12px; margin-top: 12px; }
.confirm .count { color: @yellow; }
.note { color: @grey; font-weight: normal; font-size: 11px; margin: 8px 4px 0 4px; }
"""

I_LAPTOP, I_EXTEND, I_MIRROR, I_MONITOR = "\U000f0322", "\U000f0e27", "\U000f0e2b", "\U000f0379"


def hexcolor(name, alpha=1.0):
    h = P[name].lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (alpha,)


def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


def dropdown(items, on_pick):
    dd = Gtk.DropDown.new_from_strings(items)
    dd.updating, dd.items, dd.value = False, list(items), 0

    def changed(d, _p):
        # a pick refreshes every dropdown, and GTK sends this dropdown's own change
        # again afterwards: without the value check that loops forever and the
        # popup (which holds the keyboard) freezes the whole desktop
        i = d.get_selected()
        if d.updating or i == d.value:
            return
        d.value = i
        on_pick(i)
    dd.connect("notify::selected", changed)
    return dd


def set_dropdown(dd, items, index):
    dd.updating = True
    if items != dd.items:
        dd.items = list(items)
        dd.set_model(Gtk.StringList.new(items))
    dd.value = max(0, index)
    dd.set_selected(dd.value)
    dd.updating = False


def overlaps(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw - 1 and bx < ax + aw - 1 and ay < by + bh - 1 and by < ay + ah - 1


def snap(s, others):
    """Where to drop screen s: touching the nearest other screen, never overlapping."""
    w, h = s.size()
    rects = [(o.x, o.y, *o.size()) for o in others]
    if not rects:
        return 0, 0
    cands = []
    for ox, oy, ow, oh in rects:
        # beside it (left / right), keeping s's height but stuck within reach
        yy = min(max(s.y, oy - h + 1), oy + oh - 1)
        for y in (yy, oy, oy + oh - h, oy + (oh - h) / 2):
            cands += [(ox + ow, y), (ox - w, y)]
        # above / below it
        xx = min(max(s.x, ox - w + 1), ox + ow - 1)
        for x in (xx, ox, ox + ow - w, ox + (ow - w) / 2):
            cands += [(x, oy + oh), (x, oy - h)]
    best = None
    for x, y in cands:
        if any(overlaps((x, y, w, h), r) for r in rects):
            continue
        # small pulls toward aligned edges feel right: prefer them within SNAP
        d = math.hypot(x - s.x, y - s.y)
        if best is None or d < best[0]:
            best = (d, x, y)
    if best is None:
        return s.x, s.y
    _d, x, y = best
    for ox, oy, ow, oh in rects:          # align tops / bottoms / centers when close
        for target in (oy, oy + oh - h, oy + (oh - h) / 2):
            if abs(y - target) < SNAP and not any(overlaps((x, target, w, h), r) for r in rects):
                y = target
                break
        for target in (ox, ox + ow - w, ox + (ow - w) / 2):
            if abs(x - target) < SNAP and not any(overlaps((target, y, w, h), r) for r in rects):
                x = target
                break
    return round(x), round(y)


def normalize(screens):
    """Top-left of the whole desktop at 0,0."""
    shown = [s for s in screens if s.enabled and not s.mirror]
    if not shown:
        return
    dx, dy = min(s.x for s in shown), min(s.y for s in shown)
    for s in screens:
        s.x, s.y = round(s.x - dx), round(s.y - dy)


def extend(screens):
    """The screens that show their own desktop side by side, in their current
    left-to-right order, vertically centered. Copies (mirrors) are left alone."""
    shown = sorted([s for s in screens if s.enabled and not s.mirror], key=lambda s: (s.x, s.y))
    x, tallest = 0, max((s.size()[1] for s in shown), default=0)
    for s in shown:
        w, h = s.size()
        s.x, s.y = x, round((tallest - h) / 2)
        x += round(w)


class Displays(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.local.displays")
        self.win = None
        self.screens = []
        self.before = None          # settings to go back to if you don't keep the new ones
        self.countdown = 0
        self.sel = None
        self.drag = None

    # ----- lifecycle -----------------------------------------------------------
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
        if not self.before:          # not in the middle of "keep these settings?"
            self.reload()
        self.win.present()

    def on_close(self, win):
        self.closed_at = GLib.get_monotonic_time()
        win.set_visible(False)
        return True

    def reload(self):
        self.screens = read_screens()
        self.applied = {s.name: s.state() for s in self.screens}
        if self.sel not in [s.name for s in self.screens]:
            focused = next((m["name"] for m in hyprctl_json("monitors") if m.get("focused")), None)
            self.sel = focused or (self.screens[0].name if self.screens else None)
        self.refresh()

    def screen(self, name):
        return next((s for s in self.screens if s.name == name), None)

    # ----- UI --------------------------------------------------------------------
    def build(self):
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER)
        win = Gtk.ApplicationWindow(application=self, title="Displays")
        win.add_css_class("displays")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("popup")
        box.set_size_request(WIDTH, -1)

        head = Gtk.Box(spacing=10)
        head.append(label(f"{I_MONITOR}  Displays", "title", xalign=0, hexpand=True))
        self.sub = label(css="title-sub", xalign=1)
        head.append(self.sub)
        box.append(head)

        # quick modes
        self.modes_title = label("MODE", "section", xalign=0)
        box.append(self.modes_title)
        self.modes = Gtk.Box(spacing=8, homogeneous=True)
        self.modes.add_css_class("modes")
        self.mode_btns = {}
        for key, icon, name in (("laptop", I_LAPTOP, "Laptop only"), ("extend", I_EXTEND, "Extend"),
                                ("mirror", I_MIRROR, "Duplicate"), ("external", I_MONITOR, "External only")):
            b = Gtk.Button(can_focus=False)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            inner.append(label(icon, "icon"))
            inner.append(label(name, "mode-name"))
            b.set_child(inner)
            b.connect("clicked", lambda _b, k=key: self.quick(k))
            self.mode_btns[key] = b
            self.modes.append(b)
        box.append(self.modes)

        # map
        box.append(label("ARRANGEMENT  ·  drag to move", "section", xalign=0))
        self.map = Gtk.DrawingArea(content_height=MAP_H, hexpand=True)
        self.map.add_css_class("map")
        self.map.set_draw_func(self.draw)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        drag.connect("drag-end", self.on_drag_end)
        self.map.add_controller(drag)
        box.append(self.map)

        # the selected screen
        self.chips = Gtk.Box(spacing=6, margin_top=12)
        self.chips.add_css_class("chips")
        box.append(self.chips)

        grid = Gtk.Grid(column_spacing=12, row_spacing=6, margin_top=10)
        self.sw_on = Gtk.Switch(halign=Gtk.Align.START)
        self.sw_on.connect("notify::active", lambda sw, _p: self.set_on(sw.get_active()))
        self.dd_mode = dropdown([], self.pick_mode)
        self.dd_scale = dropdown([], self.pick_scale)
        self.dd_rot = dropdown([r for _t, r in ROTATIONS], self.pick_rotation)
        self.dd_mirror = dropdown([], self.pick_mirror)
        for i, (name, w) in enumerate((("On", self.sw_on), ("Resolution", self.dd_mode),
                                       ("Scale", self.dd_scale), ("Rotation", self.dd_rot),
                                       ("Mirror", self.dd_mirror))):
            grid.attach(label(name, "row", xalign=0), 0, i, 1, 1)
            w.set_hexpand(True)
            grid.attach(w, 1, i, 1, 1)
        box.append(grid)

        self.note = label("", "note", xalign=0, wrap=True)
        box.append(self.note)

        # apply / keep
        acts = Gtk.Box(spacing=8, margin_top=14, halign=Gtk.Align.END)
        self.btn_reset = Gtk.Button(label="Undo changes")
        self.btn_reset.add_css_class("act")
        self.btn_reset.connect("clicked", lambda *_: self.reload())
        self.btn_apply = Gtk.Button(label="Apply")
        self.btn_apply.add_css_class("act")
        self.btn_apply.add_css_class("primary")
        self.btn_apply.connect("clicked", lambda *_: self.do_apply())
        acts.append(self.btn_reset)
        acts.append(self.btn_apply)
        self.acts = acts
        box.append(acts)

        self.confirm = Gtk.Box(spacing=8)
        self.confirm.add_css_class("confirm")
        self.confirm_text = label("", "count", xalign=0, hexpand=True)
        self.confirm.append(self.confirm_text)
        revert = Gtk.Button(label="Revert")
        revert.add_css_class("act")
        revert.connect("clicked", lambda *_: self.revert())
        keep = Gtk.Button(label="Keep")
        keep.add_css_class("act")
        keep.add_css_class("primary")
        keep.connect("clicked", lambda *_: self.keep())
        self.confirm.append(revert)
        self.confirm.append(keep)
        self.confirm.set_visible(False)
        box.append(self.confirm)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)

        if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
            LS.init_for_window(win)
            LS.set_namespace(win, "displays")
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
            box.set_halign(Gtk.Align.CENTER)
            box.set_valign(Gtk.Align.CENTER)
            overlay = Gtk.Overlay()
            overlay.set_child(backdrop)
            overlay.add_overlay(box)
            win.set_child(overlay)
        else:
            win.set_child(box)

    def refresh(self):
        n = len(self.screens)
        on = sum(1 for s in self.screens if s.enabled)
        self.sub.set_label(f"{n} screen{'s' * (n != 1)}" + (f" · {n - on} off" if on < n else ""))
        has_laptop = any(s.internal for s in self.screens)
        multi = n > 1
        self.modes_title.set_visible(multi)
        self.modes.set_visible(multi)
        self.mode_btns["laptop"].set_visible(has_laptop)
        self.mode_btns["external"].set_visible(has_laptop)
        current = self.current_mode()
        for k, b in self.mode_btns.items():
            (b.add_css_class if k == current else b.remove_css_class)("active")

        while (c := self.chips.get_first_child()) is not None:
            self.chips.remove(c)
        for s in self.screens:
            b = Gtk.Button(label=s.label + ("" if s.enabled else "  (off)"), can_focus=False)
            if s.name == self.sel:
                b.add_css_class("active")
            if not s.enabled:
                b.add_css_class("off")
            b.set_tooltip_text(f"{s.name} · {s.desc}")
            b.connect("clicked", lambda _b, name=s.name: self.select(name))
            self.chips.append(b)

        s = self.screen(self.sel)
        if s:
            self.sw_on.set_active(s.enabled)
            set_dropdown(self.dd_mode, [m.replace("@", " @ ") + " Hz" for m in s.modes],
                         s.modes.index(s.mode) if s.mode in s.modes else 0)
            scales = SCALES if s.scale in SCALES else sorted(SCALES + [s.scale])
            set_dropdown(self.dd_scale, [f"{round(x * 100)}%" for x in scales], scales.index(s.scale))
            self.scales = scales
            set_dropdown(self.dd_rot, [r for _t, r in ROTATIONS], s.transform % 4)
            others = [o for o in self.screens if o.name != s.name and o.enabled and not o.mirror]
            self.mirror_targets = [None] + [o.name for o in others]
            set_dropdown(self.dd_mirror, ["Off"] + [f"Copy {o.label}" for o in others],
                         self.mirror_targets.index(s.mirror) if s.mirror in self.mirror_targets else 0)
            for w in (self.dd_mode, self.dd_scale, self.dd_rot, self.dd_mirror):
                w.set_sensitive(s.enabled)
            self.dd_mirror.set_sensitive(s.enabled and bool(others))

        notes = []
        if lid_closed() and has_laptop:
            notes.append("The lid is closed, so the laptop panel stays off.")
        if not load_profiles().get(profile_key(self.screens)) and multi:
            notes.append("New set of screens: what you keep is remembered for next time.")
        self.note.set_label("\n".join(notes))
        self.note.set_visible(bool(notes))

        changed = any(x.state() != self.applied.get(x.name) for x in self.screens)
        self.btn_apply.set_sensitive(changed)
        self.btn_reset.set_sensitive(changed)
        self.acts.set_visible(not self.before)
        self.map.queue_draw()

    def current_mode(self):
        on = [s for s in self.screens if s.enabled]
        if len(self.screens) < 2:
            return None
        if len(on) == 1 and on[0].internal:
            return "laptop"
        if not any(s.internal and s.enabled for s in self.screens) and on:
            return "external"
        if len(on) > 1 and sum(1 for s in on if not s.mirror) == 1:
            return "mirror"
        if len(on) == len(self.screens):
            return "extend"
        return None

    def select(self, name):
        self.sel = name
        self.refresh()

    # ----- edits -------------------------------------------------------------------
    def edited(self):
        normalize(self.screens)
        self.refresh()

    def set_on(self, on):
        s = self.screen(self.sel)
        if not s or s.enabled == on:
            return
        if not on and sum(1 for x in self.screens if x.enabled) <= 1:
            self.sw_on.set_active(True)            # keep at least one screen on
            return
        s.enabled = on
        if on:
            others = [o for o in self.screens if o is not s and o.enabled and not o.mirror]
            right = max(others, key=lambda o: o.x + o.size()[0], default=None)
            s.x = right.x + right.size()[0] if right else 0
            s.y = right.y if right else 0
        else:
            for o in self.screens:                  # nobody can copy a screen that is off
                if o.mirror == s.name:
                    o.mirror = None
        self.edited()

    def pick_mode(self, i):
        s = self.screen(self.sel)
        if s and 0 <= i < len(s.modes):
            s.mode = s.modes[i]
            self.reflow(s)

    def pick_scale(self, i):
        s = self.screen(self.sel)
        if s and 0 <= i < len(self.scales):
            s.scale = self.scales[i]
            self.reflow(s)

    def pick_rotation(self, i):
        s = self.screen(self.sel)
        if s and 0 <= i < len(ROTATIONS):
            s.transform = ROTATIONS[i][0]
            self.reflow(s)

    def pick_mirror(self, i):
        s = self.screen(self.sel)
        if s and 0 <= i < len(self.mirror_targets):
            s.mirror = self.mirror_targets[i]
            if not s.mirror:
                self.reflow(s)
            else:
                self.edited()

    def reflow(self, s):
        """s changed size: slide it (and keep it from overlapping) next to the others."""
        others = [o for o in self.screens if o is not s and o.enabled and not o.mirror]
        if others and s.enabled and not s.mirror:
            if any(overlaps((s.x, s.y, *s.size()), (o.x, o.y, *o.size())) for o in others):
                s.x, s.y = snap(s, others)
        self.edited()

    def quick(self, mode):
        laptop = [s for s in self.screens if s.internal]
        for s in self.screens:
            s.mirror = None
            s.enabled = {"laptop": s.internal, "external": not s.internal}.get(mode, True)
        if mode == "mirror":
            target = (laptop or self.screens)[0]
            for s in self.screens:
                if s is not target:
                    s.mirror = target.name
        extend(self.screens)
        self.edited()
        self.do_apply()

    # ----- map ---------------------------------------------------------------------
    def layout(self, w, h):
        shown = [s for s in self.screens if s.enabled and not s.mirror]
        if not shown:
            return None
        x0 = min(s.x for s in shown)
        y0 = min(s.y for s in shown)
        x1 = max(s.x + s.size()[0] for s in shown)
        y1 = max(s.y + s.size()[1] for s in shown)
        k = min((w - 40) / max(1, x1 - x0), (h - 40) / max(1, y1 - y0))
        ox = (w - (x1 - x0) * k) / 2 - x0 * k
        oy = (h - (y1 - y0) * k) / 2 - y0 * k
        return k, ox, oy, shown

    def draw(self, _area, cr, w, h):
        lay = self.layout(w, h)
        self.map_geom = lay
        if not lay:
            return
        k, ox, oy, shown = lay
        for s in shown:
            sw, sh = s.size()
            x, y = ox + s.x * k, oy + s.y * k
            if self.drag and self.drag["name"] == s.name:
                x, y = self.drag["x"], self.drag["y"]
            rw, rh, r = sw * k, sh * k, 8
            cr.new_sub_path()
            cr.arc(x + rw - r, y + r, r, -math.pi / 2, 0)
            cr.arc(x + rw - r, y + rh - r, r, 0, math.pi / 2)
            cr.arc(x + r, y + rh - r, r, math.pi / 2, math.pi)
            cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
            cr.close_path()
            selected = s.name == self.sel
            cr.set_source_rgba(*hexcolor("green" if selected else "bg3", 0.35 if selected else 1))
            cr.fill_preserve()
            cr.set_line_width(3 if selected else 1.5)
            cr.set_source_rgba(*hexcolor("green" if selected else "grey"))
            cr.stroke()
            copies = [o.label for o in self.screens if o.mirror == s.name and o.enabled]
            text = f"{s.label}\n{s.mode.split('@')[0]}" + (f"\n+ {', '.join(copies)}" if copies else "")
            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(Pango.FontDescription.from_string("JetBrainsMono Nerd Font Bold 9"))
            layout.set_alignment(Pango.Alignment.CENTER)
            layout.set_width(int(max(10, rw - 8) * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            layout.set_text(text, -1)
            _ink, logical = layout.get_pixel_extents()
            cr.move_to(x + 4, y + (rh - logical.height) / 2)
            cr.set_source_rgba(*hexcolor("fg"))
            PangoCairo.show_layout(cr, layout)

    def screen_at(self, px, py):
        if not getattr(self, "map_geom", None):
            return None
        k, ox, oy, shown = self.map_geom
        for s in shown:
            sw, sh = s.size()
            if ox + s.x * k <= px <= ox + (s.x + sw) * k and oy + s.y * k <= py <= oy + (s.y + sh) * k:
                return s
        return None

    def on_drag_begin(self, _g, x, y):
        s = self.screen_at(x, y)
        if not s:
            self.drag = None
            return
        self.sel = s.name
        k, ox, oy, _shown = self.map_geom
        self.drag = dict(name=s.name, sx=ox + s.x * k, sy=oy + s.y * k, x=ox + s.x * k, y=oy + s.y * k)
        self.refresh()

    def on_drag_update(self, _g, dx, dy):
        if self.drag:
            self.drag["x"], self.drag["y"] = self.drag["sx"] + dx, self.drag["sy"] + dy
            self.map.queue_draw()

    def on_drag_end(self, _g, dx, dy):
        if not self.drag:
            return
        s = self.screen(self.drag["name"])
        k, _ox, _oy, _shown = self.map_geom
        self.drag = None
        if abs(dx) + abs(dy) < 3:                  # a click, not a drag
            self.refresh()
            return
        s.x, s.y = s.x + dx / k, s.y + dy / k
        others = [o for o in self.screens if o is not s and o.enabled and not o.mirror]
        s.x, s.y = snap(s, others)
        self.edited()

    # ----- apply / keep / revert ------------------------------------------------------
    def do_apply(self):
        if not any(s.state() != self.applied.get(s.name) for s in self.screens):
            return
        self.before = {name: dict(st) for name, st in self.applied.items()}
        apply(self.screens)
        self.applied = {s.name: s.state() for s in self.screens}
        self.countdown = REVERT_AFTER
        self.confirm.set_visible(True)
        self.tick()
        GLib.timeout_add_seconds(1, self.tick)
        self.refresh()
        # the screens just changed under the popup: show it again on the one you look at
        self.win.set_visible(False)
        GLib.timeout_add(900, lambda: (self.win.present(), False)[1])

    def tick(self):
        if not self.before:
            return False
        if self.countdown <= 0:
            self.revert()
            return False
        self.confirm_text.set_label(f"Keep these settings?  Going back in {self.countdown} s")
        self.countdown -= 1
        return True

    def keep(self):
        self.before = None
        self.confirm.set_visible(False)
        save_profile(self.screens)
        self.reload()

    def revert(self):
        if not self.before:
            return
        for s in self.screens:
            if s.name in self.before:
                s.set_state(self.before[s.name])
        self.before = None
        apply(self.screens)
        self.confirm.set_visible(False)
        GLib.timeout_add(700, lambda: (self.reload(), False)[1])
        self.win.set_visible(False)
        GLib.timeout_add(900, lambda: (self.win.present(), False)[1])

    def on_key(self, _ctl, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self.win.close()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.before:
                self.keep()
            else:
                self.do_apply()
            return True
        # Tab / Shift+Tab: next / previous screen
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab) and self.screens:
            names = [s.name for s in self.screens]
            step = -1 if keyval == Gdk.KEY_ISO_Left_Tab else 1
            i = names.index(self.sel) if self.sel in names else 0
            self.select(names[(i + step) % len(names)])
            return True
        return False


if __name__ == "__main__":
    sys.exit(Displays().run([sys.argv[0]]))
