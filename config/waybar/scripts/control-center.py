#!/usr/bin/env python3
"""
Quick settings popup for Waybar (opens from the battery box), Everforest style.

  control-center.py [THEME]

- Battery: charge, time left, and power mode (saver / balanced / performance).
- Tiles: Wi-Fi (opens the Wi-Fi menu), Bluetooth on/off, Do Not Disturb, Stay awake.
- Brightness of the laptop screen.
- Bluetooth devices: connect, disconnect, forget; "Add device" scans and pairs new ones.
- Click anywhere outside or press Esc to close; clicking the bar box again also closes it.
"""
import os
import re
import subprocess
import sys
import threading

# ---------------------------------------------------------------------------
# gtk4-layer-shell has to be loaded before libwayland-client, so restart
# ourselves once with LD_PRELOAD set (this is how the library is meant to be
# used from Python).
# ---------------------------------------------------------------------------
LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if __name__ == "__main__" and not os.environ.get("CONTROL_CENTER_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["CONTROL_CENTER_PRELOADED"] = "1"
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

import brightness  # noqa: E402
import fonts  # noqa: E402
import palette  # noqa: E402
import power_mode  # noqa: E402

import empty_state  # noqa: E402
import popup_backdrop  # noqa: E402

# imported by Settings (panel.py): no window, the theme in use
THEME = sys.argv[1] if __name__ == "__main__" and len(sys.argv) > 1 else palette.current()
WIDTH = 440
HERE = os.path.dirname(os.path.abspath(__file__))
IDLE = os.path.expanduser("~/.config/hypr/scripts/idle.sh")
IDLE_PREV = os.path.expanduser("~/.config/hypr/idle-state.before-awake")
PROFILES = power_mode.PROFILES

ALIASES = {}
P = palette.load(THEME, **ALIASES)

STYLE = """
window.control-center { background: transparent; }
.backdrop { background: transparent; }

.popup {
  background: @bg0;
  color: @fg;
  border-radius: 20px;
  border: 1px solid alpha(@fg, 0.07);
  box-shadow: 0 18px 40px @shadow, 0 2px 6px alpha(black, 0.25);
  padding: 16px;
  margin: 8px 18px 36px 18px;
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif;
  font-weight: bold;
  font-size: 14px;
}
.section { color: @grey; font-size: 11px; letter-spacing: 2px; margin: 14px 6px 4px 6px; }
.sub { color: @grey; font-weight: normal; font-size: 12px; }
.status { color: @grey; font-weight: normal; font-size: 12px; margin: 4px 6px; }
.status.error { color: @red; }
.placeholder { color: @grey; font-weight: normal; padding: 6px; }

/* battery */
.battery {
  border-radius: 16px; padding: 14px;
  background-image: linear-gradient(135deg, alpha(@green, 0.22), alpha(@aqua, 0.05) 60%, @bg1);
  border: 1px solid alpha(@green, 0.18);
  border-bottom: 3px solid @edge;
}
.battery.low { background-image: linear-gradient(135deg, alpha(@red, 0.28), alpha(@red, 0.05) 60%, @bg1); }
.bat-icon { font-size: 34px; color: @green; }
.battery.low .bat-icon { color: @red; }
.bat-pct { font-size: 26px; }

.segment { background: alpha(@fg, 0.08); border-radius: 12px; padding: 3px; margin-top: 12px; }
.segment button {
  background: transparent; color: @fg; border: none; box-shadow: none;
  border-radius: 10px; padding: 5px 6px; min-height: 0; font-size: 12px;
}
.segment button:hover { background: alpha(@fg, 0.08); }
.segment button.active { background: @green; color: @on_accent; }

/* tiles */
button.tile {
  background: @bg1; color: @fg;
  border: 1px solid alpha(@fg, 0.04); border-bottom: 3px solid @edge;
  border-radius: 16px; box-shadow: none;
  padding: 10px 12px; min-height: 0;
}
button.tile:hover { background: @bg2; }
button.tile.on { background-image: linear-gradient(135deg, @aqua, @green); color: @on_accent; }
button.tile.on .sub { color: alpha(@on_accent, 0.75); }
.tile-icon { font-size: 22px; min-width: 30px; }

/* brightness */
.card {
  background: @bg1; border-radius: 16px;
  border: 1px solid alpha(@fg, 0.04); border-bottom: 3px solid @edge;
  padding: 10px 14px; margin: 5px 0;
}
.slider-icon { font-size: 20px; min-width: 26px; }
.bright-icon { font-size: 22px; color: @yellow; min-width: 28px; }
.bright-pct, .screen-pct { color: @grey; font-size: 12px; min-width: 40px; }
button.chevron {
  background: alpha(@fg, 0.08); color: @fg; border: none; box-shadow: none;
  border-radius: 10px; padding: 3px 10px; min-height: 0; font-size: 11px;
}
button.chevron:hover { background: alpha(@fg, 0.15); }
button.chevron.open { background: @yellow; color: @on_accent; }
.screen-row { background: alpha(@fg, 0.05); border-radius: 12px; padding: 8px 10px; }
.screen-icon { font-size: 18px; color: @blue; min-width: 22px; }
.screen-name { font-size: 12px; }
.tag {
  font-size: 9px; letter-spacing: 1px; border-radius: 6px; padding: 1px 6px;
  background: alpha(@green, 0.18); color: @green;
}
.tag.soft { background: alpha(@yellow, 0.18); color: @yellow; }
.screen-row scale trough, .screen-row scale highlight { min-height: 6px; }
.screen-row scale slider { min-width: 14px; min-height: 14px; margin: -4px 0; }
.popup scale { padding: 0 4px; }
.popup scale trough { min-height: 8px; border-radius: 8px; border: none; background: alpha(@fg, 0.14); }
.popup scale highlight {
  border-radius: 8px; border: none; margin: 0; min-height: 8px; min-width: 0;
  background-image: linear-gradient(90deg, @yellow, @green);
}
.popup scale slider {
  min-width: 16px; min-height: 16px; margin: -5px 0;
  border-radius: 50%; border: none; background: @fg; box-shadow: 0 1px 4px alpha(black, 0.45);
}

/* bluetooth */
list.devs { background: transparent; }
list.devs > row {
  background: @bg1; color: @fg;
  border-radius: 14px; border: 1px solid alpha(@fg, 0.04); border-bottom: 3px solid @edge;
  margin: 4px 0; padding: 8px 12px; outline: none;
}
list.devs > row:hover { background: @bg2; }
list.devs > row.connected { box-shadow: inset 4px 0 0 @blue; }
.dev-icon { font-size: 20px; min-width: 28px; color: @blue; }
.dev-bat { color: @grey; font-size: 12px; }
.dev-bat.low { color: @red; }

button.pill, button.icon-btn, button.footer {
  border: none; box-shadow: none; min-height: 0;
  border-radius: 10px; border-bottom: 3px solid @edge;
}
button.pill { background: @green; color: @on_accent; padding: 4px 14px; }
button.pill:hover { background: shade(@green, 1.08); }
button.pill.ghost { background: @bg3; color: @fg; }
button.pill.danger { background: @red; color: @on_accent; }
button.icon-btn { background: @bg1; color: @fg; padding: 2px 10px; font-size: 12px; }
button.icon-btn:hover { background: @bg2; }
button.icon-btn.scanning { background: @blue; color: @on_accent; }
button.footer { background: @bg1; color: @fg; margin-top: 12px; padding: 8px 10px; border-radius: 14px; }
button.footer:hover { background: @bg2; }
.popup spinner { color: @blue; }
.bt-head { margin-bottom: 4px; }
.popup switch { background: @bg3; border: none; border-radius: 14px; box-shadow: none; }
.popup switch:checked { background: @green; }
.popup switch slider { background: @fg; border: none; border-radius: 12px; box-shadow: none; }
"""
STYLE += empty_state.CSS
CSS = fonts.swap("".join(f"@define-color {k} {v};\n" for k, v in P.items()) + STYLE)

I_WIFI, I_WIFI_OFF = "\U000f05a9", "\U000f05aa"
I_BT, I_BT_OFF, I_BT_ON = "\U000f00af", "\U000f00b2", "\U000f00b1"
I_DND, I_BELL = "\U000f009b", "\U000f009a"
I_COFFEE, I_SLEEP = "\U000f0176", "\U000f04b2"
I_SUN = "\U000f00e0"
I_LAPTOP, I_MONITOR = "\U000f0322", "\U000f0379"
I_DOWN, I_UP = "\U000f0140", "\U000f0143"


def sun_icon(value):
    return "\U000f00de" if value < 34 else "\U000f00df" if value < 67 else "\U000f00e0"
I_PLUS, I_CHECK = "\U000f0415", "\U000f012c"
I_POWER = "\U000f0425"
I_SETTINGS = "\U000f0493"
DEV_ICONS = {
    "audio-headset": "\U000f02ce", "audio-headphones": "\U000f02cb", "audio-card": "\U000f04c3",
    "input-keyboard": "\U000f030c", "input-mouse": "\U000f037d", "input-gaming": "\U000f0297",
    "input-tablet": "\U000f04f7", "phone": "\U000f011c", "computer": "\U000f0379",
}


# ---------------------------------------------------------------------------
# system helpers
# ---------------------------------------------------------------------------
def run(*cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def spawn(*cmd):
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def run_bg(work, done):
    def target():
        result = work()
        GLib.idle_add(lambda: (done(result), False)[1])
    threading.Thread(target=target, daemon=True).start()


def battery_icon(pct, charging):
    if charging:
        return "\U000f0084"
    icons = ["\U000f008e", "\U000f007a", "\U000f007b", "\U000f007c", "\U000f007d",
             "\U000f007e", "\U000f007f", "\U000f0080", "\U000f0081", "\U000f0082", "\U000f0079"]
    return icons[max(0, min(10, round(pct / 10)))]


def read_battery():
    _, out, _ = run("upower", "-e")
    path = next((line for line in out.split() if "BAT" in line), None)
    if not path:
        return None
    _, info, _ = run("upower", "-i", path)
    f = dict(re.findall(r"^\s+([\w -]+?):\s+(.+)$", info, re.M))
    try:
        pct = int(round(float(f.get("percentage", "0").rstrip("%").replace(",", "."))))
    except ValueError:
        pct = 0
    state = f.get("state", "")
    if state == "fully-charged" or (state == "pending-charge" and pct >= 95):
        text = "Fully charged · on power"
    elif state == "charging":
        text = f"Charging · full in {f['time to full']}" if "time to full" in f else "Charging"
    elif state == "pending-charge":
        text = "Plugged in · not charging"
    elif "time to empty" in f:
        text = f"{f['time to empty']} left"
    else:
        text = "On battery"
    return dict(pct=pct, charging=state in ("charging", "fully-charged", "pending-charge"), text=text)


def read_profile():
    return power_mode.read()


def read_wifi():
    _, out, _ = run("nmcli", "-t", "-f", "WIFI", "general", timeout=3)
    on = out.strip() == "enabled"
    _, out, _ = run("nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active", timeout=3)
    ssid = next((line.rsplit(":", 1)[0].replace("\\:", ":") for line in out.splitlines()
                 if line.endswith(":802-11-wireless")), None)
    return on, ssid


# the brightness itself (backlight, DDC/CI, the software dimmer) lives in
# brightness.py, shared with Settings' Displays page


def read_idle():
    _, out, _ = run(IDLE, "get", timeout=3)
    return out.split()[0] if out.split() else "sleep"


MAC_NAME = re.compile(r"^([0-9A-F]{2}[-:]){5}[0-9A-F]{2}$", re.I)


def bt_devices(which=None):
    args = ["bluetoothctl", "devices"] + ([which] if which else [])
    _, out, _ = run(*args, timeout=5)
    devs = {}
    for line in out.splitlines():
        m = re.match(r"^Device\s+(\S+)\s+(.*)$", line.strip())
        if m:
            devs[m.group(1)] = m.group(2)
    return devs


def bt_info(mac):
    _, out, _ = run("bluetoothctl", "info", mac, timeout=5)
    f = dict(re.findall(r"^\s+([\w ]+):\s+(.+)$", out, re.M))
    bat = re.search(r"\((\d+)\)", f.get("Battery Percentage", ""))
    battery = int(bat.group(1)) if bat else None
    if battery is None:
        battery = hid_battery(mac)
    return dict(icon=f.get("Icon", ""), connected=f.get("Connected") == "yes", battery=battery)


def hid_battery(mac):
    """Keyboards and mice that report their charge to the kernel, not to BlueZ."""
    try:
        with open(f"/sys/class/power_supply/hid-{mac.lower()}-battery/capacity") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def read_bluetooth(scanning):
    _, out, _ = run("bluetoothctl", "show", timeout=5)
    present = "Controller" in out
    powered = "Powered: yes" in out
    paired, found = [], []
    if present and powered:
        paired_names = bt_devices("Paired")
        for mac, name in paired_names.items():
            info = bt_info(mac)
            paired.append(dict(mac=mac, name=name, **info))
        paired.sort(key=lambda d: (not d["connected"], d["name"].lower()))
        if scanning:
            for mac, name in bt_devices().items():
                if mac not in paired_names and name and not MAC_NAME.match(name):
                    found.append(dict(mac=mac, name=name, icon="", connected=False, battery=None))
            found.sort(key=lambda d: d["name"].lower())
    return dict(present=present, powered=powered, paired=paired, found=found)


def read_state(scanning, screens):
    return dict(battery=read_battery(), profile=read_profile(), wifi=read_wifi(),
                bt=read_bluetooth(scanning), screens=brightness.read_screens() if screens else None,
                dnd=run("swaync-client", "-D", timeout=3)[1].strip() == "true",
                idle=read_idle())


def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
class Tile(Gtk.Button):
    def __init__(self, on_click):
        super().__init__(hexpand=True)
        self.add_css_class("tile")
        box = Gtk.Box(spacing=10)
        self.icon = label(css="tile-icon")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        self.title = label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.sub = label(css="sub", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        text.append(self.title)
        text.append(self.sub)
        box.append(self.icon)
        box.append(text)
        self.set_child(box)
        self.connect("clicked", lambda *_: on_click())

    def set(self, icon, title, sub, on):
        self.icon.set_label(icon)
        self.title.set_label(title)
        self.sub.set_label(sub)
        (self.add_css_class if on else self.remove_css_class)("on")


class DevRow(Gtk.ListBoxRow):
    def __init__(self, dev, new=False):
        super().__init__()
        self.dev, self.new = dev, new
        if dev["connected"]:
            self.add_css_class("connected")
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        top = Gtk.Box(spacing=10)
        top.append(label(DEV_ICONS.get(dev["icon"], I_BT), "dev-icon"))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        text.append(label(dev["name"], xalign=0, ellipsize=Pango.EllipsizeMode.END))
        sub = "Tap to pair" if new else ("Connected" if dev["connected"] else "Not connected")
        text.append(label(sub, "sub", xalign=0))
        top.append(text)
        if dev["battery"] is not None:
            low = " low" if dev["battery"] <= 20 else ""
            top.append(label(f"{battery_icon(dev['battery'], False)} {dev['battery']}%", "dev-bat" + low))
        outer.append(top)
        self.revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                                     transition_duration=150)
        outer.append(self.revealer)
        self.set_child(outer)

    def show_actions(self, menu):
        box = Gtk.Box(spacing=8, margin_top=10, halign=Gtk.Align.END)
        if self.dev["connected"]:
            btn = Gtk.Button(label="Disconnect")
            btn.add_css_class("pill")
            btn.add_css_class("ghost")
            btn.connect("clicked", lambda *_: menu.bt_action("disconnect", self.dev))
        else:
            btn = Gtk.Button(label="Connect")
            btn.add_css_class("pill")
            btn.connect("clicked", lambda *_: menu.bt_action("connect", self.dev))
        forget = Gtk.Button(label="Forget")
        forget.add_css_class("pill")
        forget.add_css_class("danger")
        forget.connect("clicked", lambda *_: menu.bt_action("remove", self.dev))
        box.append(btn)
        box.append(forget)
        self.revealer.set_child(box)
        self.revealer.set_reveal_child(True)


def bt_empty(present, powered):
    """EMPTY-2: (sentence, button) of the empty device list; no button when there
    is no adapter (nothing could help)."""
    if not present:
        return "No Bluetooth adapter found.", ""
    if not powered:
        return "Bluetooth is off.", "Turn on Bluetooth"
    return "No devices yet.", "Add device"


class BluetoothPanel:
    """Paired devices (connect, disconnect, forget) and Add device (scan and pair).
    Part of the quick settings popup below, and a page of Settings (see panel.py for
    the host), where it also has a title and an on/off switch and reads the state
    itself; in the popup, the popup reads everything at once (host.refresh)."""

    def __init__(self, host):
        self.host = host
        self.busy = False
        self.scanner = None
        self.open_mac = None
        self.dev_key = None
        self.updating_switch = False
        self.build()
        if host.embedded:
            GLib.timeout_add_seconds(3, self._tick)

    def build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if self.host.embedded:
            root.add_css_class("popup")
            title = Gtk.Box(spacing=10)
            title.add_css_class("bt-head")
            title.append(label(f"{I_BT}  Bluetooth", "title", xalign=0, hexpand=True))
            self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
            self.switch.connect("state-set", self.on_switch)
            title.append(self.switch)
            root.append(title)

        head = Gtk.Box(spacing=8, margin_top=6)
        head.append(label("DEVICES" if self.host.embedded else "BLUETOOTH", "section", xalign=0, hexpand=True))
        self.spinner = Gtk.Spinner(valign=Gtk.Align.CENTER)
        head.append(self.spinner)
        self.scan_btn = Gtk.Button(label=f"{I_PLUS}  Add device", valign=Gtk.Align.CENTER)
        self.scan_btn.add_css_class("icon-btn")
        self.scan_btn.connect("clicked", lambda *_: self.toggle_scan())
        head.append(self.scan_btn)
        root.append(head)

        self.status = label(css="status", xalign=0, wrap=True)
        self.status.set_visible(False)
        root.append(self.status)

        self.devs = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.devs.add_css_class("devs")
        self.devs.connect("row-activated", self.on_dev)
        self.dev_placeholder = empty_state.EmptyState()
        self.show_empty(True, True)
        self.devs.set_placeholder(self.dev_placeholder)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                    propagate_natural_height=True, max_content_height=340)
        scroll.set_child(self.devs)
        root.append(scroll)
        self.root = root

    def on_show(self):
        self.set_status("")
        self.refresh()

    def on_hide(self):
        self.stop_scan()
        self.open_mac = None
        self.dev_key = None

    def stop(self):
        self.stop_scan()

    def _tick(self):
        if self.host.is_shown() and not self.busy:
            self.refresh()
        return True

    def refresh(self):
        if not self.host.embedded:
            self.host.refresh()   # the popup reads everything at once
            return
        scanning = self.scanner is not None
        run_bg(lambda: read_bluetooth(scanning), self.apply)

    def set_status(self, text="", error=False):
        self.status.set_label(text)
        self.status.set_visible(bool(text))
        (self.status.add_css_class if error else self.status.remove_css_class)("error")

    def apply(self, bt):
        if self.host.embedded:
            self.updating_switch = True
            self.switch.set_active(bt["powered"])
            self.switch.set_state(bt["powered"])
            self.switch.set_sensitive(bt["present"])
            self.updating_switch = False
        self.scan_btn.set_sensitive(bt["powered"])
        self.apply_devices(bt)

    def on_switch(self, _sw, state):
        if not self.updating_switch:
            self.set_power(state)
        return False

    def show_empty(self, present, powered):
        """What the device list says when it has no device, and its one action."""
        text, button = bt_empty(present, powered)
        actions = {"Turn on Bluetooth": lambda: self.set_power(True), "Add device": self.toggle_scan}
        self.dev_placeholder.update(text, button=button, action=actions.get(button))

    def set_power(self, on):
        def work():
            if on:
                run("rfkill", "unblock", "bluetooth", timeout=5)
            return run("bluetoothctl", "power", "on" if on else "off", timeout=10)
        if not on:
            self.stop_scan()
        run_bg(work, lambda _r: self.refresh())

    def apply_devices(self, bt):
        key = repr((bt["powered"], bt["paired"], bt["found"], self.scanner is not None))
        if key == self.dev_key:        # nothing changed: keep open rows as they are
            return
        self.dev_key = key
        while (child := self.devs.get_first_child()) is not None:
            self.devs.remove(child)
        self.show_empty(bt["present"], bt["powered"])
        if not (bt["present"] and bt["powered"]):
            return
        for d in bt["paired"]:
            row = DevRow(d)
            self.devs.append(row)
            if d["mac"] == self.open_mac:
                row.show_actions(self)
        if self.scanner is not None:
            if not bt["found"]:
                self.devs.append(self.found_hint())
            for d in bt["found"]:
                self.devs.append(DevRow(d, new=True))

    @staticmethod
    def found_hint():
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        row.set_child(label("Searching… put the device in pairing mode", "placeholder", xalign=0))
        return row

    def toggle_scan(self):
        if self.scanner is not None:
            self.stop_scan()
            self.refresh()
            return
        try:
            run("bluetoothctl", "pairable", "on", timeout=3)
            self.scanner = subprocess.Popen(["bluetoothctl", "--timeout", "60", "scan", "on"],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.set_status("Couldn't start searching", error=True)
            return
        self.scan_btn.set_label(f"{I_CHECK}  Done")
        self.scan_btn.add_css_class("scanning")
        self.spinner.set_spinning(True)
        self.set_status("")
        GLib.timeout_add_seconds(60, lambda: (self.stop_scan(), self.refresh(), False)[2])
        self.dev_key = None
        self.refresh()

    def stop_scan(self):
        if self.scanner is not None:
            self.scanner.terminate()
            self.scanner = None
        self.scan_btn.set_label(f"{I_PLUS}  Add device")
        self.scan_btn.remove_css_class("scanning")
        self.spinner.set_spinning(self.busy)
        self.dev_key = None

    def on_dev(self, _lb, row):
        if not isinstance(row, DevRow) or self.busy:
            return
        if row.new:
            self.pair(row.dev)
            return
        if row.revealer.get_reveal_child():
            row.revealer.set_reveal_child(False)
            self.open_mac = None
            return
        child = self.devs.get_first_child()
        while child is not None:
            if isinstance(child, DevRow):
                child.revealer.set_reveal_child(False)
            child = child.get_next_sibling()
        self.open_mac = row.dev["mac"]
        row.show_actions(self)

    def set_busy(self, busy):
        self.busy = busy
        self.spinner.set_spinning(busy or self.scanner is not None)

    def bt_action(self, action, dev):
        words = {"connect": ("Connecting to", "Connected"), "disconnect": ("Disconnecting", "Disconnected"),
                 "remove": ("Forgetting", "Forgot")}[action]
        self.set_busy(True)
        self.set_status(f"{words[0]} {dev['name']}…")

        def done(res):
            code, out, err = res
            self.set_busy(False)
            ok = code == 0 and not re.search(r"Failed|Error|not available", out + err)
            if ok:
                self.set_status(f"{words[1]} {dev['name']}")
                self.open_mac = None
            else:
                msg = (re.findall(r"(?:Failed|Error)[^\n]*", out + err) or ["Didn't work — is it turned on and near?"])[-1]
                self.set_status(msg, error=True)
            self.dev_key = None
            self.refresh()
        run_bg(lambda: run("bluetoothctl", "--timeout", "20", action, dev["mac"], timeout=30), done)

    def pair(self, dev):
        """Pair, trust and connect. Keyboards may show a code to type: it appears in the status line."""
        self.set_busy(True)
        self.set_status(f"Pairing with {dev['name']}…")
        mac, name = dev["mac"], dev["name"]

        def show(text, error=False):
            GLib.idle_add(lambda: (self.set_status(text, error), False)[1])

        def work():
            try:
                p = subprocess.Popen(["bluetoothctl", "--timeout", "40", "pair", mac], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            except OSError as e:
                return False, str(e)
            out = []
            for line in p.stdout:
                out.append(line)
                code = re.search(r"Passkey:\s*(\d+)", line)
                if code:
                    show(f"Type {code.group(1)} on {name}, then press Enter")
                if re.search(r"Confirm passkey|Authorize service|\(yes/no\)", line):
                    p.stdin.write("yes\n")
                    p.stdin.flush()
            p.wait()
            text = "".join(out)
            if "Pairing successful" not in text and "AlreadyExists" not in text:
                err = re.findall(r"Failed to pair:?[^\n]*", text)
                return False, err[-1] if err else "Pairing didn't finish"
            run("bluetoothctl", "trust", mac, timeout=10)
            _, cout, _ = run("bluetoothctl", "--timeout", "20", "connect", mac, timeout=30)
            return True, "Connected" if "Connection successful" in cout else "Paired"

        def done(res):
            ok, msg = res
            self.set_busy(False)
            if ok:
                self.stop_scan()
                self.set_status(f"{msg}: {name}")
                spawn("notify-send", "-a", "Bluetooth", "-i", "bluetooth", f"{msg}", name)
            else:
                self.set_status(msg, error=True)
            self.dev_key = None
            self.refresh()
        run_bg(work, done)


class BatteryPanel:
    """Battery charge and power mode (saver / balanced / speed). Part of the
    quick settings popup below (see panel.py for the host): the popup reads
    everything at once through host.refresh. Settings does not embed this panel:
    its Battery page and its Power & sleep page show these things themselves."""

    def __init__(self, host):
        self.host = host
        self.build()
        if host.embedded:
            GLib.timeout_add_seconds(3, self._tick)

    def build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if self.host.embedded:
            root.add_css_class("popup")
            title = Gtk.Box(spacing=10, margin_bottom=6)
            title.append(label("\U000f0079  Battery", "title", xalign=0, hexpand=True))
            root.append(title)

        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.card.add_css_class("battery")
        top = Gtk.Box(spacing=12)
        self.bat_icon = label(css="bat-icon")
        top.append(self.bat_icon)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.bat_pct = label(css="bat-pct", xalign=0)
        self.bat_text = label(css="sub", xalign=0)
        text.append(self.bat_pct)
        text.append(self.bat_text)
        top.append(text)
        self.card.append(top)
        self.segment = Gtk.Box(homogeneous=True)
        self.segment.add_css_class("segment")
        self.profile_btns = {}
        for key, text_ in PROFILES:
            b = Gtk.Button(label=text_)
            b.connect("clicked", lambda _b, k=key: self.set_profile(k))
            self.profile_btns[key] = b
            self.segment.append(b)
        self.card.append(self.segment)
        self.status = label(css="status", xalign=0, wrap=True)
        self.status.set_visible(False)
        self.card.append(self.status)
        root.append(self.card)
        self.root = root

    def on_show(self):
        self.set_status()
        self.refresh()

    def on_hide(self):
        pass

    def _tick(self):
        if self.host.is_shown():
            self.refresh()
        return True

    def refresh(self):
        if not self.host.embedded:
            self.host.refresh()  # the popup reads everything at once
            return
        run_bg(lambda: (read_battery(), read_profile()), lambda r: self.apply(*r))

    def set_status(self, text="", error=False):
        self.status.set_label(text)
        self.status.set_visible(bool(text))
        (self.status.add_css_class if error else self.status.remove_css_class)("error")

    def apply(self, battery, profile):
        self.root.set_visible(battery is not None or profile is not None)
        if battery:
            self.bat_icon.set_label(battery_icon(battery["pct"], battery["charging"]))
            self.bat_pct.set_label(f"{battery['pct']}%")
            self.bat_text.set_label(battery["text"])
            (self.card.add_css_class if battery["pct"] <= 20 and not battery["charging"]
             else self.card.remove_css_class)("low")
        self.segment.set_visible(profile is not None)
        for key, btn in self.profile_btns.items():
            (btn.add_css_class if key == profile else btn.remove_css_class)("active")

    def set_profile(self, key):
        def done(res):
            if res[0] != 0:
                self.set_status(res[2].strip() or "Couldn't change power mode", error=True)
            self.refresh()
        for k, btn in self.profile_btns.items():
            (btn.add_css_class if k == key else btn.remove_css_class)("active")
        run_bg(lambda: power_mode.set_profile(key), done)


class BrightnessPanel:
    """One brightness slider per screen: the laptop backlight, external screens
    over DDC/CI, and a software dimmer for screens that can't change their own.
    Part of the quick settings popup below (see panel.py for the host); Settings
    shows brightness on its Displays page instead. Reading the screens is slow,
    so it happens on each showing, not on a timer; in the popup, the popup reads
    them once per opening and pushes them in (host.refresh). The read and the
    write go through brightness.py, shared with the Displays page."""

    def __init__(self, host):
        self.host = host
        self.updating = False
        self.bright_open = False
        self.screen_scales = []
        self.build()

    def build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if self.host.embedded:
            root.add_css_class("popup")  # so ".popup scale …" styles its sliders
        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.card.add_css_class("card")
        self.card.set_margin_top(8)
        self.card.set_visible(False)
        root.append(self.card)
        self.root = root

    def on_show(self):
        self.refresh()

    def on_hide(self):
        pass

    def refresh(self):
        if not self.host.embedded:
            self.host.refresh()  # the popup reads everything at once
            return
        run_bg(brightness.read_screens, self.apply_screens)

    def apply_screens(self, screens):
        """One main slider for every screen, and a drawer with a slider per screen."""
        while (child := self.card.get_first_child()) is not None:
            self.card.remove(child)
        self.card.set_visible(bool(screens))
        self.screen_scales = []
        if not screens:
            return

        head = Gtk.Box(spacing=10)
        self.bright_icon = label(sun_icon(100), "bright-icon")
        head.append(self.bright_icon)
        head.append(label("Brightness", "bright-title", xalign=0, hexpand=True))
        self.bright_pct = label(css="bright-pct", xalign=1)
        head.append(self.bright_pct)
        if len(screens) > 1:
            self.chevron = Gtk.Button(valign=Gtk.Align.CENTER)
            self.chevron.add_css_class("chevron")
            self.chevron.set_tooltip_text("Each screen on its own")
            self.chevron.connect("clicked", lambda *_: self.toggle_drawer())
            head.append(self.chevron)
        self.card.append(head)

        self.master = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.master.set_hexpand(True)
        self.master.set_draw_value(False)
        self.master.set_tooltip_text("All screens")
        self.master.connect("value-changed", self.on_master)
        self.card.append(self.master)

        self.drawer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                                   transition_duration=220)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6)
        for sc in screens:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            row.add_css_class("screen-row")
            top = Gtk.Box(spacing=8)
            top.append(label(I_LAPTOP if sc["key"] == "laptop" else I_MONITOR, "screen-icon"))
            top.append(label(sc["name"], "screen-name", xalign=0, hexpand=True,
                             ellipsize=Pango.EllipsizeMode.END))
            tag = label({"hardware": "DDC", "backlight": "BACKLIGHT", "dimmed": "SOFTWARE"}[sc["how"]], "tag")
            tag.set_tooltip_text({"hardware": "The monitor itself changes brightness",
                                  "backlight": "Laptop backlight",
                                  "dimmed": "This screen can't change its own brightness (no DDC/CI, "
                                            "e.g. behind a dock), so it is dimmed in software"}[sc["how"]])
            if sc["how"] == "dimmed":
                tag.add_css_class("soft")
            top.append(tag)
            pct = label(f"{sc['value']}%", "screen-pct", xalign=1)
            top.append(pct)
            row.append(top)
            low = 10 if sc["how"] == "dimmed" else 1
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, 100, 1)
            scale.set_hexpand(True)
            scale.set_draw_value(False)
            scale.set_value(sc["value"])
            scale.connect("value-changed", self.on_screen, sc, pct)
            row.append(scale)
            rows.append(row)
            self.screen_scales.append((sc, scale, pct, low))
        self.drawer.set_child(rows)
        self.drawer.set_reveal_child(self.bright_open and len(screens) > 1)
        self.card.append(self.drawer)
        self.sync_master()
        self.update_chevron()

    def update_chevron(self):
        if len(self.screen_scales) < 2:
            return
        n = len(self.screen_scales)
        self.chevron.set_label(f"{n} screens  {I_UP if self.bright_open else I_DOWN}")
        (self.chevron.add_css_class if self.bright_open else self.chevron.remove_css_class)("open")

    def toggle_drawer(self):
        self.bright_open = not self.bright_open
        self.drawer.set_reveal_child(self.bright_open)
        self.update_chevron()

    def sync_master(self):
        """Main slider shows the average of all screens."""
        values = [scale.get_value() for _sc, scale, _pct, _low in self.screen_scales]
        avg = round(sum(values) / len(values)) if values else 100
        self.updating = True
        self.master.set_value(avg)
        self.updating = False
        self.bright_pct.set_label(f"{avg}%")
        self.bright_icon.set_label(sun_icon(avg))

    def on_master(self, scale):
        if self.updating:
            return
        value = int(scale.get_value())
        self.bright_pct.set_label(f"{value}%")
        self.bright_icon.set_label(sun_icon(value))
        self.updating = True
        for sc, s, pct, low in self.screen_scales:
            v = max(low, value)
            s.set_value(v)
            pct.set_label(f"{v}%")
            self.on_brightness(sc, v)
        self.updating = False

    def on_screen(self, scale, sc, pct):
        if self.updating:
            return
        value = int(scale.get_value())
        pct.set_label(f"{value}%")
        self.on_brightness(sc, value)
        self.sync_master()

    def on_brightness(self, sc, value):
        brightness.set(sc, value)


class ControlCenter(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.local.controlcenter")
        self.win = None
        self.st = None
        self.bt = None
        self.screens_read = False
        self.start_hidden = "--hidden" in sys.argv

    # ----- host of the Bluetooth panel (see panel.py) ------------------------------
    embedded = False

    def close(self):
        self.win.close()

    def is_shown(self):
        return self.win is not None and self.win.get_visible()

    # every later launch (clicking the bar box) opens or closes the same window
    def do_activate(self):
        if self.win is None:
            self.hold()   # keep running while hidden, so the next open is instant
            self.build()
            GLib.timeout_add_seconds(3, self._tick)
            if self.start_hidden:
                self.refresh()
                return
        if self.win.get_visible():
            self.win.close()
        elif GLib.get_monotonic_time() - getattr(self, 'closed_at', 0) > 400_000:
            # the click that just closed it (outside the popup, on the bar icon)
            # also reaches the bar, which asks to open it again: ignore that one
            self.show_popup()

    def show_popup(self):
        self.place()
        self.screens_read = False    # screens may have changed since last time
        self.win.present()
        self.bt.on_show()            # clears its status line and refreshes everything
        self.bat.set_status()        # the battery card's error line from last time

    def on_close(self, win):
        self.bt.on_hide()
        self.closed_at = GLib.get_monotonic_time()
        win.set_visible(False)   # hide, don't destroy
        return True

    def place(self):
        """Put the popup right under the mouse, on whichever screen it is."""
        if not self.layered:
            return
        popup, full = self.popup, WIDTH + 36
        cursor = self.cursor_offset()
        if cursor:
            frac, screen_w = cursor
            popup.set_halign(Gtk.Align.START)
            popup.set_margin_end(0)
            popup.set_margin_start(max(0, min(int(frac * screen_w - full / 2), int(screen_w) - full)))
        else:
            popup.set_halign(Gtk.Align.END)
            popup.set_margin_end(100)

    def do_shutdown(self):
        if self.bt:
            self.bt.stop()
        Gtk.Application.do_shutdown(self)

    @staticmethod
    def cursor_offset():
        import json
        try:
            pos = json.loads(run("hyprctl", "-j", "cursorpos", timeout=2)[1])
            mon = next(m for m in json.loads(run("hyprctl", "-j", "monitors", timeout=2)[1]) if m.get("focused"))
            width = (mon["height"] if mon.get("transform", 0) % 2 else mon["width"]) / mon["scale"]
            return (pos["x"] - mon["x"]) / (width or 1), width
        except (ValueError, KeyError, StopIteration):
            return None

    # ----- layout ------------------------------------------------------------
    def build(self):
        prov = Gtk.CssProvider()
        if hasattr(prov, "load_from_string"):
            prov.load_from_string(CSS)
        else:
            prov.load_from_data(CSS, -1)
        add = getattr(Gtk, "style_context_add_provider_for_display", None) \
            or Gtk.StyleContext.add_provider_for_display
        add(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)

        win = Gtk.ApplicationWindow(application=self, title="Quick settings")
        win.connect("close-request", self.on_close)
        win.add_css_class("control-center")
        win.set_decorated(False)
        self.win = win

        popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.add_css_class("popup")
        self.popup = popup
        popup.set_size_request(WIDTH, -1)

        # battery + power mode
        self.bat = BatteryPanel(self)
        popup.append(self.bat.root)

        # tiles
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True, margin_top=12)
        self.t_wifi = Tile(self.open_wifi)
        self.t_bt = Tile(self.toggle_bt)
        self.t_dnd = Tile(self.toggle_dnd)
        self.t_awake = Tile(self.toggle_awake)
        grid.attach(self.t_wifi, 0, 0, 1, 1)
        grid.attach(self.t_bt, 1, 0, 1, 1)
        grid.attach(self.t_dnd, 0, 1, 1, 1)
        grid.attach(self.t_awake, 1, 1, 1, 1)
        popup.append(grid)

        # brightness, one slider per screen (filled in once the screens are read)
        self.bright = BrightnessPanel(self)
        popup.append(self.bright.root)

        # bluetooth
        self.bt = BluetoothPanel(self)
        popup.append(self.bt.root)

        footer = Gtk.Box(spacing=8, homogeneous=True)
        for text_, action in ((f"{I_SETTINGS}   Settings", self.open_settings),
                              (f"{I_POWER}   Power menu", self.open_power)):
            b = Gtk.Button(label=text_)
            b.add_css_class("footer")
            b.connect("clicked", action)
            footer.append(b)
        popup.append(footer)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)

        if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
            LS.init_for_window(win)
            LS.set_namespace(win, "control-center")
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

            popup.set_valign(Gtk.Align.START)
            popup.set_margin_top(64)
            self.layered = True
            overlay = Gtk.Overlay()
            overlay.set_child(backdrop)
            overlay.add_overlay(popup)
            win.set_child(overlay)
        else:
            win.set_child(popup)
            win.connect("notify::is-active", lambda w, _p: None if w.is_active() else w.close())
            self.layered = False

    # ----- state -------------------------------------------------------------
    def _tick(self):
        if self.win.get_visible() and not self.bt.busy:
            self.refresh()
        return True

    def refresh(self):
        scanning = self.bt.scanner is not None
        screens = not self.screens_read   # talking to monitors is slow: once per opening
        self.screens_read = True
        run_bg(lambda: read_state(scanning, screens), self.apply)

    def apply(self, st):
        if self.win is None:
            return
        self.st = st
        self.bat.apply(st["battery"], st["profile"])

        wifi_on, ssid = st["wifi"]
        self.t_wifi.set(I_WIFI if wifi_on else I_WIFI_OFF, "Wi-Fi",
                        ssid or ("Not connected" if wifi_on else "Off"), wifi_on and bool(ssid))
        bt = st["bt"]
        connected = [d for d in bt["paired"] if d["connected"]]
        n = len(connected)
        charges = [f"{d['battery']}%" for d in connected if d["battery"] is not None]
        if n == 1:
            bt_sub = connected[0]["name"] + (f" · {charges[0]}" if charges else "")
        elif n:
            bt_sub = f"{n} connected" + (f" · {' '.join(charges)}" if charges else "")
        else:
            bt_sub = "On" if bt["powered"] else "Off"
        self.t_bt.set(I_BT_ON if n else I_BT if bt["powered"] else I_BT_OFF, "Bluetooth",
                      bt_sub, bt["powered"])
        self.t_dnd.set(I_DND if st["dnd"] else I_BELL, "Do Not Disturb",
                       "On" if st["dnd"] else "Off", st["dnd"])
        awake = st["idle"] == "awake"
        self.t_awake.set(I_COFFEE if awake else I_SLEEP, "Stay awake",
                         "On" if awake else "Off", awake)

        if st["screens"] is not None:
            self.bright.apply_screens(st["screens"])

        self.bt.apply(bt)

    # ----- actions -----------------------------------------------------------
    def open_wifi(self):
        spawn(os.path.join(HERE, "popup.sh"), "wifi-menu", THEME)
        self.win.close()

    def toggle_bt(self):
        self.bt.set_power(not (self.st and self.st["bt"]["powered"]))

    def toggle_dnd(self):
        on = not (self.st and self.st["dnd"])
        run_bg(lambda: run("swaync-client", "-dn" if on else "-df", timeout=3), lambda _r: self.refresh())

    def toggle_awake(self):
        awake = self.st and self.st["idle"] == "awake"

        def work():
            if awake:
                prev = "sleep 5"
                try:
                    with open(IDLE_PREV) as f:
                        prev = f.read().strip() or prev
                except OSError:
                    pass
                return run(IDLE, "set", *prev.split(), timeout=10)
            _, cur, _ = run(IDLE, "get", timeout=3)
            try:
                with open(IDLE_PREV, "w") as f:
                    f.write(cur.strip())
            except OSError:
                pass
            return run(IDLE, "set", "awake", timeout=10)
        run_bg(work, lambda _r: self.refresh())

    def on_key(self, _ctl, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self.win.close()
            return True
        return False

    def open_settings(self, *_):
        self.win.close()
        spawn(os.path.expanduser("~/.config/waybar/scripts/settings.py"))

    def open_power(self, *_):
        self.win.close()
        # once this popup is gone, so popup.sh doesn't close the new one right away
        GLib.timeout_add(120, lambda: (spawn(os.path.expanduser("~/.config/waybar/scripts/popup.sh"),
                                             "power-popup", THEME), False)[1])


if __name__ == "__main__":
    sys.exit(ControlCenter().run([sys.argv[0]]))
