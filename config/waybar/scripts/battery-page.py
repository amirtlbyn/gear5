#!/usr/bin/env python3
"""
Battery page of Settings (see panel.py for the host): charge, health, cycles
and power draw (BATPICK-1); the presets, the two thresholds and the charge
speed (BATPICK-2); disabled with a fix-it message when charge_types isn't
writable (BATPICK-5). No popup of its own — Settings is the only place this
page is shown — so it holds a GTK panel class only, no Application/window.

Every read and write goes through battery.py, the module the battery-limits
service also uses, so the page and the service can never disagree.
"""
import os
import subprocess
import threading
import traceback

import gi

gi.require_version("Gtk", "4.0")
import battery  # noqa: E402
import palette  # noqa: E402
import settings_store as store  # noqa: E402
from gi.repository import GLib, Gtk  # noqa: E402

ALIASES = {}
IDLE = os.path.expanduser("~/.config/hypr/scripts/idle.sh")
DIM_NAMES = ["Off" if m == 0 else f"{m} min" for m in store.BATTERY_DIM_MINUTES]
P = palette.load(palette.current(), **ALIASES)

STYLE = """
.battery-card {
  border-radius: 16px; padding: 14px;
  background-image: linear-gradient(135deg, alpha(@green, 0.22), alpha(@aqua, 0.05) 60%, @bg1);
  border: 1px solid alpha(@green, 0.18);
  border-bottom: 3px solid @edge;
}
.battery-card .icon { font-size: 30px; color: @green; }
.battery-card .pct { font-size: 24px; }
.battery-card .sub { color: @grey; font-size: 12px; }
.battery-card .stat { color: @grey; font-size: 11.5px; margin-top: 6px; }
.presets { margin-top: 14px; }
.presets button {
  background: @bg1; color: @fg; border: none; box-shadow: none;
  border-radius: 12px; border-bottom: 3px solid @edge; padding: 8px 4px;
}
.presets button:hover { background: @bg2; }
.presets button.on { background: @green; color: @on_accent; border-bottom-color: @green_edge; }
.slider-row { margin-top: 14px; }
.row-title { font-weight: bold; font-size: 13px; }
.slider-row .val { color: @grey; }
.slider-row scale { padding: 0 4px; }
.slider-row scale trough { min-height: 8px; border-radius: 8px; border: none; background: alpha(@fg, 0.14); }
.slider-row scale highlight {
  border-radius: 8px; border: none; margin: 0; min-height: 8px; min-width: 0;
  background-image: linear-gradient(90deg, @yellow, @green);
}
.slider-row scale slider {
  min-width: 16px; min-height: 16px; margin: -5px 0;
  border-radius: 50%; border: none; background: @fg; box-shadow: 0 1px 4px alpha(black, 0.45);
}
.note { color: @grey; font-size: 11.5px; margin-top: 12px; }
.speed-row { margin-top: 10px; }
.no-perm { color: @red; font-size: 11.5px; margin-top: 12px; }
"""

# (key, name, stop, start, speed): BATPICK-2's three presets
PRESETS = [
    ("full", "Full", 100, 95, "Fast"),
    ("balanced", "Balanced", 90, 80, "Standard"),
    ("desk", "Desk", 80, 75, "Standard"),
]

STATUS_TEXT = {
    "Charging": "Charging",
    "Full": "Fully charged · on charger",
    "Not charging": "On charger, not charging",
    "Discharging": "On battery",
}

# BATPICK-5: the one command that fixes a charge_types that isn't writable. It
# names the udev rule copy install.sh puts next to the scripts, so this text
# does not depend on where the repository was cloned.
NO_PERM = (
    "charge_types isn't writable, so the controls above are off. Run install.sh "
    "again, or run this once:\n"
    "sudo install -m644 ~/.config/waybar/scripts/90-summer-battery.rules /etc/udev/rules.d/ "
    "&& sudo udevadm control --reload "
    "&& sudo udevadm trigger --subsystem-match=power_supply --action=change"
)
UNSUPPORTED = "Charge limits are not supported on this laptop: its battery has no charge modes to switch."


def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


class BatteryLimitsPanel:
    """Battery status, presets, the stop/start sliders and the charge speed.
    Part of Settings' Battery page (see panel.py for the host)."""

    def __init__(self, host):
        self.host = host
        self.updating = False
        s = store.load()
        self.stop_pct, self.start_pct, self.speed = s["battery_stop"], s["battery_start"], s["battery_speed"]
        self.build()
        GLib.timeout_add_seconds(4, self._tick)

    def build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if self.host.embedded:
            root.append(label("\U000f0079  Battery", "title", xalign=0, margin_bottom=6))

        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.card.add_css_class("battery-card")
        top = Gtk.Box(spacing=12)
        top.append(label("\U000f0079", "icon"))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.pct = label(css="pct", xalign=0)
        self.state = label(css="sub", xalign=0)
        text.append(self.pct)
        text.append(self.state)
        top.append(text)
        self.card.append(top)
        self.stat = label(css="stat", xalign=0, wrap=True)
        self.card.append(self.stat)
        root.append(self.card)

        self.presets_box = Gtk.Box(homogeneous=True, spacing=8)
        self.presets_box.add_css_class("presets")
        self.preset_btns = {}
        for key, name, _stop, _start, _speed in PRESETS:
            b = Gtk.Button(label=name)
            b.connect("clicked", lambda _b, k=key: self.pick_preset(k))
            self.presets_box.append(b)
            self.preset_btns[key] = b
        root.append(self.presets_box)

        self.stop_pct_row, self.stop_pct_scale, self.stop_pct_val = self.slider_row(
            "Stop charging at", 80, 100, self.stop_pct
        )
        self.stop_pct_scale.connect("value-changed", self.on_stop)
        root.append(self.stop_pct_row)

        self.start_pct_row, self.start_pct_scale, self.start_pct_val = self.slider_row(
            "Start charging at", 40, self.stop_pct - 5, self.start_pct
        )
        self.start_pct_scale.connect("value-changed", self.on_start)
        root.append(self.start_pct_row)

        speed_row = Gtk.Box(spacing=12)
        speed_row.add_css_class("speed-row")
        speed_row.append(label("Charge speed", "row-title", xalign=0, hexpand=True))
        self.speed_drop = Gtk.DropDown.new_from_strings(list(battery.SPEEDS))
        self.speed_drop.set_selected(list(battery.SPEEDS).index(self.speed))
        self.speed_drop.connect("notify::selected", self.on_speed)
        speed_row.append(self.speed_drop)
        root.append(speed_row)

        root.append(
            label(
                "On the charger, above the stop level the laptop runs from the charger and the "
                "battery rests. At 80% the firmware itself holds the level.",
                "note",
                xalign=0,
                wrap=True,
            )
        )
        self.no_perm = label(NO_PERM, "no-perm", xalign=0, wrap=True, visible=False)
        root.append(self.no_perm)

        # BDIM-1: not one of the charge-limit controls, so it stays on without charge_types
        dim_row = Gtk.Box(spacing=12)
        dim_row.add_css_class("speed-row")
        dim_row.append(label("Dim when idle", "row-title", xalign=0, hexpand=True))
        self.dim_drop = Gtk.DropDown.new_from_strings(DIM_NAMES)
        self.dim_drop.set_selected(store.BATTERY_DIM_MINUTES.index(store.load()["battery_dim"]))
        self.dim_drop.connect("notify::selected", self.on_dim)
        dim_row.append(self.dim_drop)
        root.append(dim_row)
        root.append(label("On battery, the laptop screen dims to 30% after this long with no use.",
                          "note", xalign=0, wrap=True))

        self.root = root
        self.update_presets()

    def slider_row(self, title, low, high, value):
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row.add_css_class("slider-row")
        head = Gtk.Box(spacing=8)
        head.append(label(title, "row-title", xalign=0, hexpand=True))
        val = label(f"{value}%", "val")
        head.append(val)
        row.append(head)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, 1)
        scale.set_value(value)
        scale.set_draw_value(False)
        row.append(scale)
        return row, scale, val

    # ----- lifecycle (see panel.py for the host) --------------------------------
    def on_show(self):
        self.refresh()

    def on_hide(self):
        pass

    def _tick(self):
        if self.host.is_shown():
            self.refresh()
        return True

    # ----- reading the battery ---------------------------------------------------
    def refresh(self):
        self.apply_state(battery.read(), battery.writable())

    def apply_state(self, state, can_write):
        """BATPICK-1: charge, state, health, cycles and power draw. BATPICK-5:
        the controls turn off, and the fix-it message shows, when charge_types
        can't be written, or say that limits are not supported on a battery without
        the IdeaPad's charge modes (state is None only with no battery at all)."""
        self.root.set_visible(state is not None)
        if state is None:
            return
        pct = state["capacity"]
        self.pct.set_label(f"{pct}%" if pct is not None else "—")
        self.state.set_label(STATUS_TEXT.get(state["status"], state["status"]))
        parts = []
        if state["health_pct"] is not None:
            parts.append(f"Health {state['health_pct']}%")
        if state["cycle_count"] is not None:
            parts.append(f"{state['cycle_count']} cycles")
        if state["power_watts"] is not None:
            parts.append(f"{state['power_watts']} W")
        self.stat.set_label("  ·  ".join(parts))
        for w in (self.presets_box, self.stop_pct_scale, self.start_pct_scale, self.speed_drop):
            w.set_sensitive(can_write)
        self.no_perm.set_label(NO_PERM if state["supported"] else UNSUPPORTED)
        self.no_perm.set_visible(not can_write)

    # ----- presets, sliders, speed (BATPICK-2) ------------------------------------
    def update_presets(self):
        for key, btn in self.preset_btns.items():
            stop, start, speed = next((p[2], p[3], p[4]) for p in PRESETS if p[0] == key)
            on = (stop, start, speed) == (self.stop_pct, self.start_pct, self.speed)
            (btn.add_css_class if on else btn.remove_css_class)("on")

    def pick_preset(self, key):
        stop, start, speed = next((p[2], p[3], p[4]) for p in PRESETS if p[0] == key)
        self.stop_pct, self.start_pct, self.speed = stop, start, speed
        self.updating = True
        self.start_pct_scale.get_adjustment().set_upper(stop - 5)
        self.stop_pct_scale.set_value(stop)
        self.start_pct_scale.set_value(start)
        self.stop_pct_val.set_label(f"{stop}%")
        self.start_pct_val.set_label(f"{start}%")
        self.speed_drop.set_selected(list(battery.SPEEDS).index(speed))
        self.updating = False
        self.update_presets()
        self.save()

    def on_stop(self, scale):
        if self.updating:
            return
        self.stop_pct = int(scale.get_value())
        self.stop_pct_val.set_label(f"{self.stop_pct}%")
        self.updating = True
        self.start_pct_scale.get_adjustment().set_upper(self.stop_pct - 5)
        if self.start_pct > self.stop_pct - 5:  # BATPICK-2: clamp start when stop moves
            self.start_pct = self.stop_pct - 5
            self.start_pct_scale.set_value(self.start_pct)
            self.start_pct_val.set_label(f"{self.start_pct}%")
        self.updating = False
        self.update_presets()
        self.save()

    def on_start(self, scale):
        if self.updating:
            return
        self.start_pct = int(scale.get_value())
        self.start_pct_val.set_label(f"{self.start_pct}%")
        self.update_presets()
        self.save()

    def on_speed(self, drop, _pspec):
        if self.updating:
            return
        self.speed = list(battery.SPEEDS)[drop.get_selected()]
        self.update_presets()
        self.save()

    def on_dim(self, drop, _pspec):
        """BDIM-1: save the dim time and rewrite hypridle's config at once."""
        try:
            store.save(dict(store.load(), battery_dim=store.BATTERY_DIM_MINUTES[drop.get_selected()]))
        except ValueError:
            traceback.print_exc()
            return
        subprocess.Popen([IDLE, "apply"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)

    def save(self):
        """BATPICK-2: save at once, then apply the rule right away, so the
        charger reacts without waiting for the service's next check. The
        sliders and presets only ever offer values battery.valid() accepts,
        so a ValueError here would mean a real bug, not a bad user choice."""
        try:
            store.save(
                dict(
                    store.load(),
                    battery_stop=self.stop_pct,
                    battery_start=self.start_pct,
                    battery_speed=self.speed,
                )
            )
        except ValueError:
            traceback.print_exc()
            return
        threading.Thread(target=battery.tick, daemon=True).start()
