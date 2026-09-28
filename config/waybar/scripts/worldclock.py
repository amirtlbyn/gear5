#!/usr/bin/env python3
"""
World clock popup for Waybar (click the clock), Everforest style.

  worldclock.py [THEME] [--hidden]

- Every pinned timezone: time, day, difference from you, a day/night bar, and the
  weather there now (Open-Meteo; see weather_lib.py).
- Click a zone to show it on the bar (scrolling on the bar clock cycles them too).
- ✕ unpins a zone; search at the bottom to pin any city / timezone.
- Pinned zones live in ~/.config/waybar/clock-zones.json (the bar clock reads it).
- Stays running hidden after the first use, so it opens instantly.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import zoneinfo

LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if not os.environ.get("WORLDCLOCK_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["WORLDCLOCK_PRELOADED"] = "1"
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

import fonts  # noqa: E402
import palette  # noqa: E402

import popup_backdrop  # noqa: E402

import weather_lib as wx  # noqa: E402

THEME = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else palette.current()
WIDTH = 440
STATE = os.path.expanduser("~/.config/waybar/clock-zones.json")
DEFAULT = {"active": "local", "pinned": ["local", "Asia/Tehran", "UTC"]}

# common names people search for that aren't in the zone id
ALIASES = {
    "iran": "Asia/Tehran", "dubai": "Asia/Dubai", "uae": "Asia/Dubai", "india": "Asia/Kolkata",
    "delhi": "Asia/Kolkata", "mumbai": "Asia/Kolkata", "bangalore": "Asia/Kolkata",
    "beijing": "Asia/Shanghai", "china": "Asia/Shanghai", "japan": "Asia/Tokyo",
    "korea": "Asia/Seoul", "turkey": "Europe/Istanbul", "germany": "Europe/Berlin",
    "france": "Europe/Paris", "uk": "Europe/London", "england": "Europe/London",
    "netherlands": "Europe/Amsterdam", "spain": "Europe/Madrid", "italy": "Europe/Rome",
    "bulgaria": "Europe/Sofia", "russia": "Europe/Moscow", "canada": "America/Toronto",
    "san francisco": "America/Los_Angeles", "sf": "America/Los_Angeles", "seattle": "America/Los_Angeles",
    "california": "America/Los_Angeles", "texas": "America/Chicago", "boston": "America/New_York",
    "nyc": "America/New_York", "washington": "America/New_York", "miami": "America/New_York",
    "australia": "Australia/Sydney", "brazil": "America/Sao_Paulo", "gmt": "UTC", "utc": "UTC",
    "pst": "America/Los_Angeles", "est": "America/New_York", "cet": "Europe/Berlin",
}

P = palette.load(THEME)

CSS = fonts.swap("".join(f"@define-color {k} {v};\n" for k, v in P.items()) + """
window.worldclock { background: transparent; }
.backdrop { background: transparent; }
.popup {
  background: @bg0; color: @fg;
  border-radius: 20px; border: 1px solid alpha(@fg, 0.07);
  box-shadow: 0 18px 40px @shadow, 0 2px 6px alpha(black, 0.25);
  padding: 16px; margin: 8px 18px 36px 18px;
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif; font-weight: bold; font-size: 14px;
}
.title { font-size: 19px; }
.title-sub { color: @grey; font-weight: normal; font-size: 12px; }
.section { color: @grey; font-size: 11px; letter-spacing: 2px; margin: 14px 6px 4px 6px; }

.zone {
  background: @bg1; border-radius: 16px;
  border: 1px solid alpha(@fg, 0.04); border-bottom: 3px solid @edge;
  padding: 10px 14px; margin: 5px 0;
}
.zone:hover { background: @bg2; }
.zone.day { background-image: linear-gradient(120deg, alpha(@yellow, 0.14), alpha(@bg1, 0) 55%); }
.zone.night { background-image: linear-gradient(120deg, alpha(@blue, 0.16), alpha(@bg1, 0) 55%); }
.zone.active { border-color: alpha(@green, 0.5); box-shadow: inset 4px 0 0 @green; }
.city { font-size: 15px; }
.meta { color: @grey; font-weight: normal; font-size: 12px; }
.clock { font-size: 28px; }
.secs { color: @grey; font-size: 13px; margin-bottom: 5px; }
.sky { font-size: 26px; min-width: 40px; }
.zone.day .sky { color: @yellow; }
.zone.night .sky { color: @blue; }
.zone .sky.wet { color: @aqua; }
.temp { font-size: 13px; }
.wx { color: @fg; font-weight: normal; font-size: 12px; }
.badge {
  font-size: 9px; letter-spacing: 1px; border-radius: 6px; padding: 1px 6px;
  background: @green; color: @on_accent;
}
.ahead { color: @aqua; }
.behind { color: @orange; }

/* 24h strip: where "now" is in that zone's day */
.strip trough { min-height: 4px; border-radius: 4px; border: none; background: alpha(@fg, 0.10); }
.strip progress { min-height: 4px; border-radius: 4px; border: none;
  background-image: linear-gradient(90deg, @blue, @yellow 50%, @orange); }
.zone.night .strip progress { background-image: linear-gradient(90deg, @blue, @purple); }

button.x {
  background: transparent; color: @grey; border: none; box-shadow: none;
  border-radius: 50%; padding: 0 6px; min-height: 0; min-width: 0; font-size: 12px;
}
button.x:hover { color: @red; background: alpha(@red, 0.12); }

entry.search {
  background: @bg1; color: @fg; border: none; box-shadow: none; outline: none;
  border-radius: 14px; border-bottom: 3px solid @edge; padding: 4px 12px; min-height: 36px;
}
list.results { background: transparent; }
list.results > row { background: transparent; border-radius: 10px; padding: 6px 10px; }
list.results > row:hover { background: alpha(@fg, 0.06); }
.res-name { font-size: 13px; }
.res-time { color: @grey; font-size: 12px; }
.plus { color: @green; font-size: 16px; }
.hint { color: alpha(@grey, 0.8); font-weight: normal; font-size: 11px; margin: 8px 4px 0 4px; }
""")

I_CLOCK, I_SUN, I_MOON, I_X, I_PLUS, I_SEARCH = "\U000f0954", "\U000f0599", "\U000f0594", "\U000f0156", "\U000f0415", "\U000f0349"


def local_zone():
    try:
        return os.path.realpath("/etc/localtime").split("/zoneinfo/", 1)[1]
    except IndexError:
        return "UTC"


LOCAL = local_zone()
ALL_ZONES = sorted(z for z in zoneinfo.available_timezones()
                   if "/" in z and not z.startswith(("Etc/", "SystemV/", "US/", "posix", "right"))) + ["UTC"]


def real(z):
    return LOCAL if z == "local" else z


def city(z):
    return real(z).rsplit("/", 1)[-1].replace("_", " ")


def region(z):
    r = real(z)
    return r.split("/", 1)[0].replace("_", " ") if "/" in r else "Coordinated Universal Time"


def load():
    try:
        with open(STATE) as f:
            st = json.load(f)
        st.setdefault("pinned", ["local"])
        st.setdefault("active", "local")
        return st
    except (OSError, ValueError):
        return dict(DEFAULT)


def save(st):
    tmp = STATE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(st, f)
        os.replace(tmp, STATE)
    except OSError:
        pass


def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


def offset_text(z, now_utc):
    here = now_utc.astimezone(zoneinfo.ZoneInfo(LOCAL)).utcoffset()
    there = now_utc.astimezone(zoneinfo.ZoneInfo(real(z))).utcoffset()
    mins = int((there - here).total_seconds() // 60)
    if mins == 0:
        return "same time", ""
    h, m = divmod(abs(mins), 60)
    txt = f"{h}h" + (f"{m:02d}" if m else "")
    return (f"+{txt} ahead", "ahead") if mins > 0 else (f"−{txt} behind", "behind")


def day_text(t, here):
    diff = (t.date() - here.date()).days
    return {0: "Today", 1: "Tomorrow", -1: "Yesterday"}.get(diff, t.strftime("%a"))


class ZoneCard(Gtk.Box):
    def __init__(self, app, z):
        super().__init__(spacing=12)
        self.add_css_class("zone")
        self.z = z
        # weather: icon + temperature (sun / moon until the weather arrives)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.sky = label(css="sky")
        self.temp = label(css="temp")
        left.append(self.sky)
        left.append(self.temp)
        self.append(left)
        self.weather = None

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True, valign=Gtk.Align.CENTER)
        top = Gtk.Box(spacing=8)
        name = "Local · " + city(z) if z == "local" else city(z)
        top.append(label(name, "city", xalign=0, ellipsize=Pango.EllipsizeMode.END))
        self.badge = label("ON BAR", "badge", valign=Gtk.Align.CENTER)
        top.append(self.badge)
        info.append(top)
        self.meta = label(css="meta", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        info.append(self.meta)
        self.wx = label(css="wx", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.wx.set_visible(False)
        info.append(self.wx)
        self.strip = Gtk.ProgressBar()
        self.strip.add_css_class("strip")
        self.strip.set_margin_top(4)
        info.append(self.strip)
        self.append(info)

        t = Gtk.Box(valign=Gtk.Align.CENTER, spacing=2)
        self.clock = label(css="clock")
        self.secs = label(css="secs", valign=Gtk.Align.END)
        t.append(self.clock)
        t.append(self.secs)
        self.append(t)

        if z != "local":
            x = Gtk.Button(label=I_X, valign=Gtk.Align.START, tooltip_text="Unpin")
            x.add_css_class("x")
            x.connect("clicked", lambda *_: app.unpin(z))
            self.append(x)
        else:
            self.append(Gtk.Box(width_request=22))

        click = Gtk.GestureClick()
        click.connect("released", lambda *_: app.set_active(z))
        self.add_controller(click)
        self.set_tooltip_text("Show this one on the bar")
        self.update(dt.datetime.now(dt.timezone.utc))

    def update(self, now_utc):
        t = now_utc.astimezone(zoneinfo.ZoneInfo(real(self.z)))
        here = now_utc.astimezone(zoneinfo.ZoneInfo(LOCAL))
        day = 6 <= t.hour < 18
        (self.add_css_class if day else self.remove_css_class)("day")
        (self.remove_css_class if day else self.add_css_class)("night")
        if self.weather is None:
            self.sky.set_label(I_SUN if day else I_MOON)
        self.clock.set_label(t.strftime("%H:%M"))
        self.secs.set_label(t.strftime(":%S"))
        off, cls = offset_text(self.z, now_utc)
        abbr = t.strftime("%Z")
        abbr = "" if abbr.startswith(("+", "-")) else f" · {abbr}"
        self.meta.set_label(f"{day_text(t, here)}, {t.strftime('%d %b')} · {off}{abbr}")
        self.strip.set_fraction((t.hour * 3600 + t.minute * 60 + t.second) / 86400)

    def set_weather(self, w):
        """w: weather_lib data for this zone, or None."""
        self.weather = w
        if not w:
            self.temp.set_label("")
            self.wx.set_visible(False)
            return
        icon, words = wx.describe(w["code"], w["is_day"])
        self.sky.set_label(icon)
        (self.sky.add_css_class if w["code"] >= 51 else self.sky.remove_css_class)("wet")
        self.temp.set_label(wx.deg(w["temp"]))
        today = w["daily"][0] if w.get("daily") else None
        hl = f"  ·  H {wx.deg(today['max'])}  L {wx.deg(today['min'])}" if today else ""
        self.wx.set_label(f"{words}{hl}")
        self.wx.set_visible(True)

    def set_active(self, on):
        self.badge.set_visible(on)
        (self.add_css_class if on else self.remove_css_class)("active")


class WorldClock(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.local.worldclock")
        self.win = None
        self.cards = {}
        self.st = load()

    def do_activate(self):
        if self.win is not None:
            if self.win.get_visible():
                self.win.close()
            elif GLib.get_monotonic_time() - getattr(self, "closed_at", 0) > 400_000:
                # the click that just closed it (on the bar clock) also reaches the bar: ignore it
                self.show_popup()
            return
        self.hold()
        self.build()
        GLib.timeout_add(1000, self._tick)
        if "--hidden" not in sys.argv:
            self.show_popup()

    def show_popup(self):
        self.st = load()        # the bar may have changed the active zone (scrolling)
        self.render()
        self.search.set_text("")
        self.place()
        self.win.present()
        self.refresh_weather()

    def on_close(self, win):
        self.closed_at = GLib.get_monotonic_time()
        win.set_visible(False)
        return True

    @staticmethod
    def cursor_offset():
        try:
            pos = json.loads(subprocess.run(["hyprctl", "-j", "cursorpos"], capture_output=True,
                                            text=True, timeout=2).stdout)
            mons = json.loads(subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True,
                                             text=True, timeout=2).stdout)
            mon = next(m for m in mons if m.get("focused"))
            width = (mon["height"] if mon.get("transform", 0) % 2 else mon["width"]) / mon["scale"]
            return (pos["x"] - mon["x"]) / (width or 1), width
        except (OSError, ValueError, KeyError, StopIteration, subprocess.TimeoutExpired):
            return None

    def place(self):
        if not self.layered:
            return
        full = WIDTH + 36
        cursor = self.cursor_offset()
        if cursor:
            frac, screen_w = cursor
            self.popup.set_halign(Gtk.Align.START)
            self.popup.set_margin_start(max(0, min(int(frac * screen_w - full / 2), int(screen_w) - full)))
        else:
            self.popup.set_halign(Gtk.Align.START)
            self.popup.set_margin_start(120)

    def build(self):
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER)
        win = Gtk.ApplicationWindow(application=self, title="World clock")
        win.add_css_class("worldclock")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win

        popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.add_css_class("popup")
        popup.set_size_request(WIDTH, -1)
        self.popup = popup

        header = Gtk.Box(spacing=10)
        header.append(label(f"{I_CLOCK}  World clock", "title", xalign=0, hexpand=True))
        self.header_sub = label(css="title-sub", xalign=1)
        header.append(self.header_sub)
        popup.append(header)

        popup.append(label("PINNED", "section", xalign=0))
        self.zones_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.append(self.zones_box)

        popup.append(label("ADD A TIMEZONE", "section", xalign=0))
        self.search = Gtk.SearchEntry(placeholder_text="City, country or zone — Tokyo, Dubai, PST…")
        self.search.add_css_class("search")
        self.search.connect("search-changed", lambda *_: self.find())
        self.search.connect("activate", lambda *_: self.pin_first())
        popup.append(self.search)
        self.results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.results.add_css_class("results")
        self.results.connect("row-activated", lambda _l, r: self.pin(r.zone))
        popup.append(self.results)
        popup.append(label("Click a zone to show it on the bar · scroll the bar clock to switch", "hint", xalign=0))

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)

        self.layered = LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported())
        if self.layered:
            LS.init_for_window(win)
            LS.set_namespace(win, "worldclock")
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
            overlay = Gtk.Overlay()
            overlay.set_child(backdrop)
            overlay.add_overlay(popup)
            win.set_child(overlay)
        else:
            win.set_child(popup)

    # ----- zones ---------------------------------------------------------------
    def render(self):
        while (child := self.zones_box.get_first_child()) is not None:
            self.zones_box.remove(child)
        self.cards = {}
        for z in self.st["pinned"]:
            try:
                card = ZoneCard(self, z)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                continue
            self.cards[z] = card
            self.zones_box.append(card)
            card.set_weather(wx.cached(real(z)))
        self.mark_active()
        self.update_header()

    def mark_active(self):
        for z, card in self.cards.items():
            card.set_active(z == self.st.get("active", "local"))

    def update_header(self):
        now = dt.datetime.now(zoneinfo.ZoneInfo(LOCAL))
        self.header_sub.set_label(now.strftime("%A, %d %B"))

    def _tick(self):
        if self.win.get_visible():
            now = dt.datetime.now(dt.timezone.utc)
            for card in self.cards.values():
                card.update(now)
            if now.timestamp() - getattr(self, "weather_at", 0) > 600:
                self.refresh_weather()
        return True

    def refresh_weather(self):
        self.weather_at = dt.datetime.now(dt.timezone.utc).timestamp()
        zones = [real(z) for z in self.cards]

        def work():
            data = wx.fetch(zones)
            GLib.idle_add(lambda: (self.apply_weather(data), False)[1])
        threading.Thread(target=work, daemon=True).start()

    def apply_weather(self, data):
        for z, card in self.cards.items():
            card.set_weather(data.get(real(z)) or wx.cached(real(z)))

    def set_active(self, z):
        self.st["active"] = z
        save(self.st)
        self.mark_active()

    def unpin(self, z):
        self.st["pinned"] = [p for p in self.st["pinned"] if p != z]
        if self.st.get("active") == z:
            self.st["active"] = "local"
        save(self.st)
        self.render()
        self.find()

    def pin(self, z):
        if z not in self.st["pinned"]:
            self.st["pinned"].append(z)
            save(self.st)
            self.render()
            self.refresh_weather()
        self.search.set_text("")

    def pin_first(self):
        row = self.results.get_row_at_index(0)
        if row is not None:
            self.pin(row.zone)

    def find(self):
        while (child := self.results.get_first_child()) is not None:
            self.results.remove(child)
        q = self.search.get_text().strip().lower()
        if not q:
            return
        matches = []
        if q in ALIASES:
            matches.append(ALIASES[q])
        qn = q.replace(" ", "_")
        starts = [z for z in ALL_ZONES if z.lower().rsplit("/", 1)[-1].startswith(qn)]
        within = [z for z in ALL_ZONES if qn in z.lower() and z not in starts]
        for z in starts + within:
            if z not in matches:
                matches.append(z)
        now = dt.datetime.now(dt.timezone.utc)
        for z in matches[:6]:
            row = Gtk.ListBoxRow()
            row.zone = z
            box = Gtk.Box(spacing=10)
            box.append(label(I_PLUS, "plus"))
            box.append(label(f"{city(z)}  ·  {region(z)}", "res-name", xalign=0, hexpand=True,
                             ellipsize=Pango.EllipsizeMode.END))
            t = now.astimezone(zoneinfo.ZoneInfo(z))
            box.append(label(f"{t.strftime('%H:%M')}  {offset_text(z, now)[0]}", "res-time"))
            row.set_child(box)
            if z in self.st["pinned"]:
                row.set_sensitive(False)
            self.results.append(row)

    def on_key(self, _ctl, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            if self.search.get_text():
                self.search.set_text("")
            else:
                self.win.close()
            return True
        return False


if __name__ == "__main__":
    sys.exit(WorldClock().run([sys.argv[0]]))
