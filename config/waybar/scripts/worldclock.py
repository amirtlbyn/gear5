#!/usr/bin/env python3
"""
Clock popup for Waybar (click the clock, either button), Everforest style.

  worldclock.py [THEME] [--hidden]

One page for everything the clock touches:
- A calendar (Gregorian / Persian Solar Hijri, Tab to switch) with the
  weather now and for the next days where you are.
- Up to 4 pinned timezones: time, day, difference from you, a day/night bar,
  and the weather there now (Open-Meteo; see weather_lib.py).
- Click a zone to show it on the bar (scrolling on the bar clock cycles them
  too). ✕ unpins a zone; search at the bottom to pin any city / timezone, up
  to the 4-zone cap.
- Pinned zones live in ~/.config/waybar/clock-zones.json (the bar clock
  reads it).
- Stays running hidden after the first use, so it opens instantly.
"""
import datetime as dt
import json
import os
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
WIDTH = 380
MAX_PINNED = 4
STATE = os.path.expanduser("~/.config/waybar/clock-zones.json")
DEFAULT = {"active": "local", "pinned": ["local", "Asia/Tehran", "UTC"]}
MODE_CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                          "worldclock-calendar-mode")

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
  padding: 12px; margin: 8px 18px 36px 18px;
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif; font-weight: bold; font-size: 13px;
}
.title { font-size: 19px; }
.title-sub { color: @grey; font-weight: normal; font-size: 12px; }
.section { color: @grey; font-size: 10px; letter-spacing: 2px; margin: 6px 6px 2px 6px; }

.zones-grid { margin: 2px 0; }
.zone {
  background: @bg1; border-radius: 12px; min-width: 0;
  border: 1px solid alpha(@fg, 0.04); border-bottom: 3px solid @edge;
  padding: 5px 8px;
}
.zone:hover { background: @bg2; }
.zone.day { background-image: linear-gradient(120deg, alpha(@yellow, 0.14), alpha(@bg1, 0) 55%); }
.zone.night { background-image: linear-gradient(120deg, alpha(@blue, 0.16), alpha(@bg1, 0) 55%); }
.zone.active { border-color: alpha(@green, 0.5); box-shadow: inset 4px 0 0 @green; }
.city { font-size: 13px; }
.meta { color: @grey; font-weight: normal; font-size: 11px; }
.clock { font-size: 19px; }
.secs { color: @grey; font-size: 11px; margin-bottom: 3px; }
.sky { font-size: 17px; min-width: 26px; }
.zone.day .sky { color: @yellow; }
.zone.night .sky { color: @blue; }
.zone .sky.wet { color: @aqua; }
.temp { font-size: 11px; }
.wx { color: @fg; font-weight: normal; font-size: 11px; }
.badge { color: alpha(@grey, 0.4); font-size: 14px; }
.zone.active .badge { color: @green; }
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
entry.search:disabled { opacity: 0.5; }
list.results { background: transparent; }
list.results > row { background: transparent; border-radius: 10px; padding: 6px 10px; }
list.results > row:hover { background: alpha(@fg, 0.06); }
.res-name { font-size: 13px; }
.res-time { color: @grey; font-size: 12px; }
.plus { color: @green; font-size: 16px; }
.hint { color: alpha(@grey, 0.8); font-weight: normal; font-size: 11px; margin: 8px 4px 0 4px; }

/* ----- calendar section, ported from calendar-popup.py, restyled to match ----- */
button.cal-nav, button.cal-seg, button.cal-today {
  background: @bg1; color: @fg;
  border: none; border-radius: 8px; border-bottom: 3px solid @edge;
  box-shadow: none; min-height: 0; padding: 2px 10px;
}
button.cal-nav:hover, button.cal-seg:hover, button.cal-today:hover { background: @bg2; }
button.cal-seg.on { background: @green; color: @bg0; border-bottom-color: @green_edge; }
.cal-segbox button.cal-seg:first-child { border-radius: 8px 0 0 8px; }
.cal-segbox button.cal-seg:last-child  { border-radius: 0 8px 8px 0; }
.cal-title { font-size: 15px; }

.cal-head { color: @grey; font-size: 12px; margin-bottom: 2px; min-height: 21px; }
.cal-head.weekend { color: @red; }

button.cal-day {
  background: transparent; color: @fg;
  border: none; border-radius: 8px; box-shadow: none;
  min-width: 36px; min-height: 35px; padding: 0;
}
button.cal-day:hover { background: @bg1; }
button.cal-day .cal-sub { color: @grey; font-size: 10px; font-weight: normal; }
button.cal-day.weekend .cal-main { color: @red; }
button.cal-day.today {
  background: @green; color: @bg0;
  border-bottom: 3px solid @green_edge;
}
button.cal-day.today .cal-main, button.cal-day.today .cal-sub { color: @bg0; }
button.cal-day.selected:not(.today) { background: @bg2; box-shadow: inset 0 -3px 0 @blue; }

.cal-footer { color: @grey; font-weight: normal; margin-top: 3px; }
.cal-footer .primary { color: @fg; font-weight: bold; }

.cal-wx-card {
  background: @bg1; border-radius: 12px; border-bottom: 3px solid @edge;
  padding: 6px 10px; margin-top: 6px;
}
.cal-wx-now-icon { font-size: 26px; color: @blue; min-width: 34px; }
.cal-wx-now { font-size: 15px; }
.cal-wx-now-sub { color: @grey; font-weight: normal; font-size: 12px; }
.cal-wx-col { border-radius: 10px; padding: 2px 0; }
.cal-wx-col.today { background: alpha(@green, 0.12); }
.cal-wx-day { color: @grey; font-size: 10px; }
.cal-wx-col.today .cal-wx-day { color: @green; }
.cal-wx-icon { font-size: 15px; color: @blue; }
.cal-wx-hi { font-size: 11px; }
.cal-wx-lo { color: @grey; font-weight: normal; font-size: 10px; }
button.cal-wx-city, button.cal-wx-auto {
  background: @bg2; color: @fg; border: none; box-shadow: none; border-radius: 10px;
  padding: 2px 10px; min-height: 0; font-size: 12px;
}
button.cal-wx-city:hover, button.cal-wx-auto:hover { background: @bg3; }
button.cal-wx-auto.on { background: @green; color: @bg0; }
entry.cal-wx-search {
  background: @bg0; color: @fg; border: none; box-shadow: none; outline: none;
  border-radius: 10px; min-height: 32px; padding: 0 10px;
}
list.cal-wx-results { background: transparent; }
list.cal-wx-results > row { background: transparent; border-radius: 8px; padding: 5px 8px; }
list.cal-wx-results > row:hover { background: alpha(@fg, 0.07); }
.cal-wx-res-sub { color: @grey; font-weight: normal; font-size: 11px; }
""")

I_CLOCK, I_SUN, I_MOON, I_X, I_PLUS, I_SEARCH = "\U000f0954", "\U000f0599", "\U000f0594", "\U000f0156", "\U000f0415", "\U000f0349"
I_TODAY, I_CITY = "\U000f00f6", "\U000f034e"


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


# ---------------------------------------------------------------------------
# Calendar maths (Gregorian <-> Persian/Solar Hijri), ported from
# calendar-popup.py verbatim.
# ---------------------------------------------------------------------------
def g2j(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100
            + (gy2 + 399) // 400 + gd + g_d_m[gm - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def j2g(jy, jm, jd):
    jy += 1595
    days = (-355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
            + (31 * (jm - 1) if jm < 7 else (jm - 7) * 30 + 186))
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    months = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gd > months[gm]:
        gd -= months[gm]
        gm += 1
    return gy, gm + 1, gd


def jdate(jy, jm, jd):
    return dt.date(*j2g(jy, jm, jd))


def jmonth_len(jy, jm):
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return (jdate(jy + 1, 1, 1) - jdate(jy, 12, 1)).days


FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
FA_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
FA_WEEK = ["ش", "ی", "د", "س", "چ", "پ", "ج"]            # Saturday first
FA_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]  # by date.weekday()
EN_WEEK = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]      # Monday first


def fa(n):
    return str(n).translate(FA_DIGITS)


def month_cells(mode, year, month):
    """Return (title, weekday headers, list of 42 cells). Cell = None or
    (date, main_label, sub_label, is_weekend)."""
    cells = []
    if mode == "fa":
        first = jdate(year, month, 1)
        lead = (first.weekday() + 2) % 7                     # Saturday = 0
        length = jmonth_len(year, month)
        title = f"{FA_MONTHS[month - 1]} {fa(year)}"
        heads = FA_WEEK
        for i in range(length):
            d = first + dt.timedelta(days=i)
            cells.append((d, fa(i + 1), str(d.day), d.weekday() == 4))     # Friday
    else:
        first = dt.date(year, month, 1)
        lead = first.weekday()                               # Monday = 0
        nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
        length = (nxt - first).days
        title = first.strftime("%B %Y")
        heads = EN_WEEK
        for i in range(length):
            d = first + dt.timedelta(days=i)
            cells.append((d, str(d.day), fa(g2j(d.year, d.month, d.day)[2]), d.weekday() >= 5))
    grid = [None] * lead + cells
    grid += [None] * (42 - len(grid))
    return title, heads, grid


def today_line(mode, d):
    jy, jm, jd = g2j(d.year, d.month, d.day)
    fa_txt = f"{FA_WEEKDAYS[d.weekday()]} {fa(jd)} {FA_MONTHS[jm - 1]} {fa(jy)}"
    en_txt = d.strftime("%A, %d %B %Y")
    return (fa_txt, en_txt) if mode == "fa" else (en_txt, fa_txt)


class ZoneCard(Gtk.Box):
    """A compact, roughly-square card for a 2-column grid (up to MAX_PINNED of
    them): a top row (city + unpin), weather + clock side by side, then the
    offset/weather text and the day/night strip."""

    def __init__(self, app, z):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.add_css_class("zone")
        self.z = z
        self.weather = None

        top = Gtk.Box(spacing=4)
        name = "Local · " + city(z) if z == "local" else city(z)
        top.append(label(name, "city", xalign=0, hexpand=True, max_width_chars=13,
                        ellipsize=Pango.EllipsizeMode.END))
        self.badge = label("●", "badge", valign=Gtk.Align.CENTER, tooltip_text="Shown on the bar")
        top.append(self.badge)
        if z != "local":
            x = Gtk.Button(label=I_X, valign=Gtk.Align.CENTER, tooltip_text="Unpin")
            x.add_css_class("x")
            x.connect("clicked", lambda *_: app.unpin(z))
            top.append(x)
        self.append(top)

        mid = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.sky = label(css="sky")
        self.temp = label(css="temp")
        left.append(self.sky)
        left.append(self.temp)
        mid.append(left)
        t = Gtk.Box(valign=Gtk.Align.CENTER, spacing=2, hexpand=True, halign=Gtk.Align.END)
        self.clock = label(css="clock")
        self.secs = label(css="secs", valign=Gtk.Align.END)
        t.append(self.clock)
        t.append(self.secs)
        mid.append(t)
        self.append(mid)

        self.meta = label(css="meta", xalign=0, max_width_chars=20, ellipsize=Pango.EllipsizeMode.END)
        self.append(self.meta)
        self.wx = label(css="wx", xalign=0, max_width_chars=20, ellipsize=Pango.EllipsizeMode.END)
        self.wx.set_visible(False)
        self.append(self.wx)
        self.strip = Gtk.ProgressBar()
        self.strip.add_css_class("strip")
        self.strip.set_margin_top(2)
        self.append(self.strip)

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
        self.today = dt.date.today()
        self.selected = self.today
        try:
            self.mode = open(MODE_CACHE).read().strip() or "en"
        except OSError:
            self.mode = "en"
        self.set_view_to(self.today)

    # --- calendar view state -----------------------------------------------
    def set_view_to(self, d):
        if self.mode == "fa":
            jy, jm, _ = g2j(d.year, d.month, d.day)
            self.year, self.month = jy, jm
        else:
            self.year, self.month = d.year, d.month

    def shift(self, months):
        m = self.month - 1 + months
        self.year += m // 12
        self.month = m % 12 + 1
        self.render_calendar()

    def set_mode(self, mode):
        if mode == self.mode:
            return
        # switching calendars always jumps back to today
        self.today = dt.date.today()
        self.selected = self.today
        self.mode = mode
        try:
            os.makedirs(os.path.dirname(MODE_CACHE), exist_ok=True)
            open(MODE_CACHE, "w").write(mode)
        except OSError:
            pass
        self.set_view_to(self.today)
        self.render_calendar()
        # the weather day names follow the language too
        self.apply_home_weather(getattr(self, "last_home_weather", None))

    def go_today(self):
        self.selected = self.today
        self.set_view_to(self.today)
        self.render_calendar()

    def select(self, d):
        self.selected = d
        self.render_calendar()

    # --- app -----------------------------------------------------------------
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
        GLib.timeout_add_seconds(60, self._cal_tick)
        if "--hidden" not in sys.argv:
            self.show_popup()

    def show_popup(self):
        self.st = load()        # the bar may have changed the active zone (scrolling)
        self.render()
        self.search.set_text("")
        # the calendar always opens on today
        self.today = dt.date.today()
        self.selected = self.today
        self.set_view_to(self.today)
        self.render_calendar()
        self.place()
        self.win.present()
        self.refresh_weather()
        self.refresh_home_weather()

    def on_close(self, win):
        self.closed_at = GLib.get_monotonic_time()
        win.set_visible(False)
        return True

    def place(self):
        if not self.layered:
            return
        full = WIDTH + 36
        cursor = popup_backdrop.cursor_on_screen()
        if cursor:
            x, _y, screen_w = cursor
            self.popup.set_halign(Gtk.Align.START)
            self.popup.set_margin_start(max(0, min(int(x - full / 2), int(screen_w) - full)))
        else:
            self.popup.set_halign(Gtk.Align.START)
            self.popup.set_margin_start(120)

    def build(self):
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER)
        win = Gtk.ApplicationWindow(application=self, title="Clock")
        win.add_css_class("worldclock")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win

        popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.add_css_class("popup")
        popup.set_size_request(WIDTH, -1)
        self.popup = popup

        header = Gtk.Box(spacing=10)
        header.append(label(f"{I_CLOCK}  Clock", "title", xalign=0, hexpand=True))
        self.header_sub = label(css="title-sub", xalign=1, max_width_chars=24,
                                ellipsize=Pango.EllipsizeMode.END)
        header.append(self.header_sub)
        popup.append(header)

        self.build_calendar_section(popup)

        popup.append(label("PINNED", "section", xalign=0))
        self.zones_box = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        self.zones_box.add_css_class("zones-grid")
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
        self.hint = label("Click a zone to show it on the bar · scroll the bar clock to switch", "hint", xalign=0,
                          wrap=True, max_width_chars=44)
        popup.append(self.hint)

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

    # ----- calendar section ------------------------------------------------
    def build_calendar_section(self, popup):
        popup.append(label("CALENDAR", "section", xalign=0))

        top = Gtk.Box(spacing=8)
        seg = Gtk.Box()
        seg.add_css_class("cal-segbox")
        self.btn_en = Gtk.Button(label="EN")
        self.btn_fa = Gtk.Button(label="FA")
        for b, m in ((self.btn_en, "en"), (self.btn_fa, "fa")):
            b.add_css_class("cal-seg")
            b.connect("clicked", lambda _b, m=m: self.set_mode(m))
            seg.append(b)
        spacer = Gtk.Box(hexpand=True)
        today = Gtk.Button(label=f"{I_TODAY}  Today")
        today.add_css_class("cal-today")
        today.connect("clicked", lambda *_: self.go_today())
        top.append(seg)
        top.append(spacer)
        top.append(today)
        popup.append(top)

        nav = Gtk.Box(spacing=8, margin_top=4)
        self.cal_prev = Gtk.Button(label="\U000f0141")
        self.cal_next = Gtk.Button(label="\U000f0142")
        # left/right buttons: in Persian (right-to-left) the left one goes forward
        for b, step in ((self.cal_prev, -1), (self.cal_next, 1)):
            b.add_css_class("cal-nav")
            b.connect("clicked", lambda _b, s=step: self.shift(-s if self.mode == "fa" else s))
        self.cal_title = Gtk.Label(hexpand=True)
        self.cal_title.add_css_class("cal-title")
        nav.append(self.cal_prev)
        nav.append(self.cal_title)
        nav.append(self.cal_next)
        popup.append(nav)

        self.grid = Gtk.Grid(column_spacing=4, row_spacing=2, column_homogeneous=True, margin_top=4)
        popup.append(self.grid)

        foot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        foot.add_css_class("cal-footer")
        self.cal_foot1 = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER, wrap=True,
                                   wrap_mode=Pango.WrapMode.WORD_CHAR, max_width_chars=34, width_chars=34)
        self.cal_foot1.add_css_class("primary")
        self.cal_foot2 = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER, wrap=True,
                                   wrap_mode=Pango.WrapMode.WORD_CHAR, max_width_chars=34)
        foot.append(self.cal_foot1)
        foot.append(self.cal_foot2)
        popup.append(foot)

        # weather where you are: now + the next days
        self.cal_wx_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.cal_wx_card.add_css_class("cal-wx-card")
        now_row = Gtk.Box(spacing=10)
        self.cal_wx_icon = Gtk.Label()
        self.cal_wx_icon.add_css_class("cal-wx-now-icon")
        now_txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.cal_wx_now = Gtk.Label(xalign=0, max_width_chars=22, ellipsize=Pango.EllipsizeMode.END)
        self.cal_wx_now.add_css_class("cal-wx-now")
        self.cal_wx_sub = Gtk.Label(xalign=0, max_width_chars=26, ellipsize=Pango.EllipsizeMode.END)
        self.cal_wx_sub.add_css_class("cal-wx-now-sub")
        now_txt.append(self.cal_wx_now)
        now_txt.append(self.cal_wx_sub)
        now_txt.set_hexpand(True)
        now_row.append(self.cal_wx_icon)
        now_row.append(now_txt)
        self.cal_wx_auto = Gtk.Button(label="AUTO", valign=Gtk.Align.CENTER,
                                      tooltip_text="Follow the active timezone")
        self.cal_wx_auto.add_css_class("cal-wx-auto")
        self.cal_wx_auto.connect("clicked", lambda *_: (wx.set_home_auto(), self.refresh_home_weather()))
        now_row.append(self.cal_wx_auto)
        self.cal_wx_city = Gtk.Button(valign=Gtk.Align.CENTER, tooltip_text="Choose a fixed city")
        self.cal_wx_city.add_css_class("cal-wx-city")
        self.cal_wx_city.connect("clicked", lambda *_: self.toggle_city_search())
        now_row.append(self.cal_wx_city)
        self.cal_wx_card.append(now_row)

        self.cal_wx_pick = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                                        transition_duration=150)
        pick = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.cal_wx_search = Gtk.SearchEntry(placeholder_text="Any city — Tehran, Isfahan, Berlin…")
        self.cal_wx_search.add_css_class("cal-wx-search")
        self.cal_wx_search.connect("search-changed", lambda *_: self.find_city())
        self.cal_wx_search.connect("activate", lambda *_: self.pick_city(0))
        pick.append(self.cal_wx_search)
        self.cal_wx_results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.cal_wx_results.add_css_class("cal-wx-results")
        self.cal_wx_results.connect("row-activated", lambda _l, r: self.pick_city(r.get_index()))
        pick.append(self.cal_wx_results)
        self.cal_wx_pick.set_child(pick)
        self.cal_wx_card.append(self.cal_wx_pick)
        self.city_hits = []
        self.city_seq = 0
        self.cal_wx_days = Gtk.Box(homogeneous=True, spacing=4)
        self.cal_wx_days.set_size_request(-1, 74)   # same height in English and Persian
        self.cal_wx_card.append(self.cal_wx_days)
        self.cal_wx_card.set_visible(False)
        popup.append(self.cal_wx_card)

    def render_calendar(self):
        fa_mode = self.mode == "fa"
        direction = Gtk.TextDirection.RTL if fa_mode else Gtk.TextDirection.LTR
        for w in (self.grid, self.cal_title):
            w.set_direction(direction)
        (self.popup.add_css_class if fa_mode else self.popup.remove_css_class)("fa")
        for b, on in ((self.btn_en, not fa_mode), (self.btn_fa, fa_mode)):
            (b.add_css_class if on else b.remove_css_class)("on")

        title, heads, cells = month_cells(self.mode, self.year, self.month)
        self.cal_title.set_label(title)

        while (c := self.grid.get_first_child()) is not None:
            self.grid.remove(c)
        weekend_col = 6 if fa_mode else None
        for i, h in enumerate(heads):
            lbl = Gtk.Label(label=h)
            lbl.add_css_class("cal-head")
            if (fa_mode and i == weekend_col) or (not fa_mode and i >= 5):
                lbl.add_css_class("weekend")
            self.grid.attach(lbl, i, 0, 1, 1)

        for idx in range(6 * 7):
            cell = cells[idx] if idx < len(cells) else None
            r, c = idx // 7 + 1, idx % 7
            if cell is None:
                spacer = Gtk.Box()
                spacer.set_size_request(-1, 35)
                self.grid.attach(spacer, c, r, 1, 1)
                continue
            d, main_txt, sub_txt, weekend = cell
            btn = Gtk.Button()
            btn.add_css_class("cal-day")
            if weekend:
                btn.add_css_class("weekend")
            if d == self.today:
                btn.add_css_class("today")
            if d == self.selected:
                btn.add_css_class("selected")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
            m = Gtk.Label(label=main_txt)
            m.add_css_class("cal-main")
            s = Gtk.Label(label=sub_txt)
            s.add_css_class("cal-sub")
            box.append(m)
            box.append(s)
            btn.set_child(box)
            btn.set_tooltip_text(" · ".join(today_line(self.mode, d)))
            btn.connect("clicked", lambda _b, d=d: self.select(d))
            self.grid.attach(btn, c, r, 1, 1)

        a, b = today_line(self.mode, self.selected)
        self.cal_foot1.set_label(a)
        self.cal_foot2.set_label(b)

    def _cal_tick(self):
        if self.win.get_visible() and dt.date.today() != self.today:
            self.today = dt.date.today()
            self.render_calendar()
        return True

    # --- calendar weather (auto: the active pinned zone, or a manual pick) ---
    def refresh_home_weather(self):
        self.home = wx.get_home(real(self.st.get("active", "local")))
        key = self.home["key"]
        self.cal_wx_city.set_label(f"{I_CITY}  {self.home['name']}")
        (self.cal_wx_auto.add_css_class if self.home.get("auto") else self.cal_wx_auto.remove_css_class)("on")
        self.apply_home_weather(wx.cached(key))       # last known, straight away

        def work():
            data = wx.fetch([key]).get(key)
            GLib.idle_add(lambda: (self.apply_home_weather(data) if key == self.home["key"] else None, False)[1])
        threading.Thread(target=work, daemon=True).start()

    def toggle_city_search(self):
        opening = not self.cal_wx_pick.get_reveal_child()
        self.cal_wx_pick.set_reveal_child(opening)
        self.cal_wx_search.set_text("")
        if opening:
            self.cal_wx_search.grab_focus()

    def find_city(self):
        self.city_seq += 1
        seq, text = self.city_seq, self.cal_wx_search.get_text().strip()
        while (child := self.cal_wx_results.get_first_child()) is not None:
            self.cal_wx_results.remove(child)
        self.city_hits = []
        if len(text) < 2:
            return

        def work():
            hits = wx.search(text)
            GLib.idle_add(lambda: (self.show_cities(seq, hits), False)[1])
        GLib.timeout_add(250, lambda: (threading.Thread(target=work, daemon=True).start()
                                       if seq == self.city_seq else None, False)[1])

    def show_cities(self, seq, hits):
        if seq != self.city_seq:
            return
        if hits is None:
            hits, note = [], "Offline — can't search right now"
        else:
            note = "No city found" if not hits else None
        self.city_hits = hits
        for h in hits:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            row.append(Gtk.Label(label=h["name"], xalign=0))
            if h["sub"]:
                sub = Gtk.Label(label=h["sub"], xalign=0)
                sub.add_css_class("cal-wx-res-sub")
                row.append(sub)
            self.cal_wx_results.append(row)
        if note:
            lbl = Gtk.Label(label=note, xalign=0)
            lbl.add_css_class("cal-wx-res-sub")
            self.cal_wx_results.append(lbl)

    def pick_city(self, i):
        if 0 <= i < len(self.city_hits):
            wx.set_home(self.city_hits[i])
            self.cal_wx_pick.set_reveal_child(False)
            self.refresh_home_weather()

    def apply_home_weather(self, w):
        if not w:
            return
        self.last_home_weather = w
        icon, words = wx.describe(w["code"], w["is_day"])
        self.cal_wx_icon.set_label(icon)
        self.cal_wx_now.set_label(f"{wx.deg(w['temp'])}  {words}")
        home_city = self.home.get("sub") or self.home["name"]
        daily = w.get("daily") or []
        today = daily[0] if daily else None
        hl = f"  ·  H {wx.deg(today['max'])}  L {wx.deg(today['min'])}" if today else ""
        self.cal_wx_sub.set_label(f"{home_city}{hl}")
        while (child := self.cal_wx_days.get_first_child()) is not None:
            self.cal_wx_days.remove(child)
        for i, d in enumerate(daily[:5]):
            day = dt.date.fromisoformat(d["date"])
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            col.add_css_class("cal-wx-col")
            if i == 0:
                col.add_css_class("today")
            name = ("Today" if i == 0 else day.strftime("%a")) if self.mode != "fa" \
                else ("امروز" if i == 0 else FA_WEEKDAYS[day.weekday()])
            for text, css in ((name, "cal-wx-day"), (wx.describe(d["code"])[0], "cal-wx-icon"),
                              (wx.deg(d["max"]), "cal-wx-hi"), (wx.deg(d["min"]), "cal-wx-lo")):
                lbl = Gtk.Label(label=text, max_width_chars=6, ellipsize=Pango.EllipsizeMode.END)
                lbl.add_css_class(css)
                col.append(lbl)
            self.cal_wx_days.append(col)
        self.cal_wx_card.set_visible(True)

    # ----- zones -------------------------------------------------------------
    def render(self):
        while (child := self.zones_box.get_first_child()) is not None:
            self.zones_box.remove(child)
        self.cards = {}
        col = row = 0
        for z in self.st["pinned"]:
            try:
                card = ZoneCard(self, z)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                continue
            self.cards[z] = card
            self.zones_box.attach(card, col, row, 1, 1)
            card.set_weather(wx.cached(real(z)))
            col += 1
            if col == 2:
                col, row = 0, row + 1
        self.mark_active()
        self.update_header()
        at_cap = len(self.st["pinned"]) >= MAX_PINNED
        self.search.set_sensitive(not at_cap)
        self.hint.set_label(
            "4 timezones pinned — unpin one to add another" if at_cap
            else "Click a zone to show it on the bar · scroll the bar clock to switch")

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
        self.refresh_home_weather()

    def unpin(self, z):
        self.st["pinned"] = [p for p in self.st["pinned"] if p != z]
        was_active = self.st.get("active") == z
        if was_active:
            self.st["active"] = "local"
        save(self.st)
        self.render()
        self.find()
        if was_active:
            self.refresh_home_weather()

    def pin(self, z):
        if z not in self.st["pinned"] and len(self.st["pinned"]) < MAX_PINNED:
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
        at_cap = len(self.st["pinned"]) >= MAX_PINNED
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
            if z in self.st["pinned"] or at_cap:
                row.set_sensitive(False)
            self.results.append(row)

    def on_key(self, _ctl, keyval, _code, _state):
        if self.cal_wx_pick.get_reveal_child():
            if keyval == Gdk.KEY_Escape:
                self.cal_wx_pick.set_reveal_child(False)
                return True
            return False             # typing a city: leave the keys to the search box
        if self.search.has_focus() and keyval != Gdk.KEY_Escape:
            return False             # typing a zone: leave the keys (incl. arrows) to the search box
        if keyval == Gdk.KEY_Escape:
            if self.search.get_text():
                self.search.set_text("")
            else:
                self.win.close()
            return True
        rtl = self.mode == "fa"
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
            self.shift(1 if rtl and keyval == Gdk.KEY_Left else -1)
        elif keyval in (Gdk.KEY_Right, Gdk.KEY_Page_Down):
            self.shift(-1 if rtl and keyval == Gdk.KEY_Right else 1)
        elif keyval == Gdk.KEY_Up:
            self.shift(-12)
        elif keyval == Gdk.KEY_Down:
            self.shift(12)
        elif keyval in (Gdk.KEY_t, Gdk.KEY_T):
            self.go_today()
        elif keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            self.set_mode("en" if self.mode == "fa" else "fa")
        else:
            return False
        return True


if __name__ == "__main__":
    sys.exit(WorldClock().run([sys.argv[0]]))
