#!/usr/bin/env python3
"""
Calendar popup for Waybar — Gregorian / Persian (Solar Hijri), Everforest style.

  calendar-popup.py [THEME]

Opens under the date box. Click outside or press Esc to close; clicking the
date box again also closes it.
Keys: ←/→ month, ↑/↓ year, T today, Tab switch calendar.
Below the month: the weather now and for the next days in a city you choose
(click the city name to change it; saved in ~/.config/waybar/weather-place.json).
"""
import datetime as dt
import os
import sys

LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if not os.environ.get("CAL_POPUP_PRELOADED") and __name__ == "__main__":
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["CAL_POPUP_PRELOADED"] = "1"
    if lib:
        old = os.environ.get("LD_PRELOAD", "")
        os.environ["LD_PRELOAD"] = lib + (":" + old if old else "")
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])


# ---------------------------------------------------------------------------
# Calendar maths
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


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def main():
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, GLib, Gtk
    import threading
    import weather_lib as wx
    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LS
    except (ValueError, ImportError):
        LS = None
    import palette
    import popup_backdrop

    try:
        LOCAL_ZONE = os.path.realpath("/etc/localtime").split("/zoneinfo/", 1)[1]
    except IndexError:
        LOCAL_ZONE = "UTC"
    theme = sys.argv[1] if len(sys.argv) > 1 else palette.current()
    pal = palette.load(theme, edge="edge_deep")
    css = "".join(f"@define-color {k} {v};\n" for k, v in pal.items()) + """
window.cal-popup { background: transparent; }
.backdrop { background: transparent; }
.popup {
  background: @bg0; color: @fg;
  border-radius: 14px; border-bottom: 6px solid @edge;
  padding: 14px;
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif;
  font-weight: bold; font-size: 14px;
}
.popup.fa { font-family: "Vazirmatn", "JetBrainsMono Nerd Font", sans-serif; }
.title { font-size: 18px; }

button.nav, button.seg, button.today-btn {
  background: @bg1; color: @fg;
  border: none; border-radius: 8px; border-bottom: 3px solid @edge;
  box-shadow: none; min-height: 0; padding: 2px 10px;
}
button.nav:hover, button.seg:hover, button.today-btn:hover { background: @bg2; }
button.seg.on { background: @green; color: @bg0; border-bottom-color: @green_edge; }
.segbox button.seg:first-child { border-radius: 8px 0 0 8px; }
.segbox button.seg:last-child  { border-radius: 0 8px 8px 0; }

.head { color: @grey; font-size: 12px; margin-bottom: 2px; }
.head.weekend { color: @red; }

button.day {
  background: transparent; color: @fg;
  border: none; border-radius: 8px; box-shadow: none;
  min-width: 42px; min-height: 40px; padding: 2px 0;
}
button.day:hover { background: @bg1; }
button.day .sub { color: @grey; font-size: 10px; font-weight: normal; }
button.day.weekend .main { color: @red; }
button.day.today {
  background: @green; color: @bg0;
  border-bottom: 3px solid @green_edge;
}
button.day.today .main, button.day.today .sub { color: @bg0; }
button.day.selected:not(.today) { background: @bg2; box-shadow: inset 0 -3px 0 @blue; }

.footer { color: @grey; font-weight: normal; margin-top: 10px; }
.footer .primary { color: @fg; font-weight: bold; }

.wx-card {
  background: @bg1; border-radius: 12px; border-bottom: 3px solid @edge;
  padding: 10px 12px; margin-top: 10px;
}
.wx-now-icon { font-size: 26px; color: @blue; min-width: 34px; }
.wx-now { font-size: 15px; }
.wx-now-sub { color: @grey; font-weight: normal; font-size: 12px; }
.wx-col { border-radius: 10px; padding: 4px 0; }
.wx-col.today { background: alpha(@green, 0.12); }
.wx-day { color: @grey; font-size: 11px; }
.wx-col.today .wx-day { color: @green; }
.wx-icon { font-size: 18px; color: @blue; }
.wx-hi { font-size: 12px; }
.wx-lo { color: @grey; font-weight: normal; font-size: 11px; }
button.wx-city {
  background: @bg2; color: @fg; border: none; box-shadow: none; border-radius: 10px;
  padding: 2px 10px; min-height: 0; font-size: 12px;
}
button.wx-city:hover { background: @bg3; }
entry.wx-search {
  background: @bg0; color: @fg; border: none; box-shadow: none; outline: none;
  border-radius: 10px; min-height: 32px; padding: 0 10px;
}
list.wx-results { background: transparent; }
list.wx-results > row { background: transparent; border-radius: 8px; padding: 5px 8px; }
list.wx-results > row:hover { background: alpha(@fg, 0.07); }
.wx-res-sub { color: @grey; font-weight: normal; font-size: 11px; }
"""

    cache = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                         "calendar-popup-mode")

    class Cal(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="io.local.calendarpopup")
            self.win = None
            self.start_hidden = "--hidden" in sys.argv
            self.today = dt.date.today()
            self.selected = self.today
            try:
                self.mode = open(cache).read().strip() or "en"
            except OSError:
                self.mode = "en"
            self.set_view_to(self.today)

        # --- view state ---
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
            self.render()

        def set_mode(self, mode):
            if mode == self.mode:
                return
            # switching calendars always jumps back to today
            self.today = dt.date.today()
            self.selected = self.today
            anchor = self.today
            self.mode = mode
            try:
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                open(cache, "w").write(mode)
            except OSError:
                pass
            self.set_view_to(anchor)
            self.render()
            # the weather day names follow the language too
            self.apply_weather(getattr(self, "last_weather", None))

        # --- app ---
        # stays running hidden after the first use, so clicking the bar opens it instantly
        def do_activate(self):
            if self.win is not None:
                if self.win.get_visible():
                    self.win.close()
                elif GLib.get_monotonic_time() - getattr(self, 'closed_at', 0) > 400_000:
                    # the click that just closed it (outside the popup, on the bar icon)
                    # also reaches the bar, which asks to open it again: ignore that one
                    self.show_popup()
                return
            self.hold()
            self.build()
            if not self.start_hidden:
                self.show_popup()

        def show_popup(self):
            # always open on today
            self.today = dt.date.today()
            self.selected = self.today
            self.set_view_to(self.today)
            self.render()
            self.win.present()
            self.refresh_weather()

        # --- weather ---
        def refresh_weather(self):
            self.home = wx.get_home(LOCAL_ZONE)
            key = self.home["key"]
            self.wx_city.set_label(f"\U000f034e  {self.home['name']}")
            self.apply_weather(wx.cached(key))       # last known, straight away

            def work():
                data = wx.fetch([key]).get(key)
                GLib.idle_add(lambda: (self.apply_weather(data) if key == self.home["key"] else None, False)[1])
            threading.Thread(target=work, daemon=True).start()

        def toggle_city_search(self):
            opening = not self.wx_pick.get_reveal_child()
            self.wx_pick.set_reveal_child(opening)
            self.wx_search.set_text("")
            if opening:
                self.wx_search.grab_focus()

        def find_city(self):
            self.city_seq += 1
            seq, text = self.city_seq, self.wx_search.get_text().strip()
            while (child := self.wx_results.get_first_child()) is not None:
                self.wx_results.remove(child)
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
                    sub.add_css_class("wx-res-sub")
                    row.append(sub)
                self.wx_results.append(row)
            if note:
                lbl = Gtk.Label(label=note, xalign=0)
                lbl.add_css_class("wx-res-sub")
                self.wx_results.append(lbl)

        def pick_city(self, i):
            if 0 <= i < len(self.city_hits):
                wx.set_home(self.city_hits[i])
                self.wx_pick.set_reveal_child(False)
                self.refresh_weather()

        def apply_weather(self, w):
            if not w:
                return
            self.last_weather = w
            icon, words = wx.describe(w["code"], w["is_day"])
            self.wx_icon.set_label(icon)
            self.wx_now.set_label(f"{wx.deg(w['temp'])}  {words}")
            city = self.home.get("sub") or self.home["name"]
            daily = w.get("daily") or []
            today = daily[0] if daily else None
            hl = f"  ·  H {wx.deg(today['max'])}  L {wx.deg(today['min'])}" if today else ""
            self.wx_sub.set_label(f"{city}{hl}")
            while (child := self.wx_days.get_first_child()) is not None:
                self.wx_days.remove(child)
            for i, d in enumerate(daily[:5]):
                day = dt.date.fromisoformat(d["date"])
                col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
                col.add_css_class("wx-col")
                if i == 0:
                    col.add_css_class("today")
                name = ("Today" if i == 0 else day.strftime("%a")) if self.mode != "fa" \
                    else ("امروز" if i == 0 else FA_WEEKDAYS[day.weekday()])
                for text, css in ((name, "wx-day"), (wx.describe(d["code"])[0], "wx-icon"),
                                  (wx.deg(d["max"]), "wx-hi"), (wx.deg(d["min"]), "wx-lo")):
                    lbl = Gtk.Label(label=text)
                    lbl.add_css_class(css)
                    col.append(lbl)
                self.wx_days.append(col)
            self.wx_card.set_visible(True)

        def on_close(self, win):
            self.closed_at = GLib.get_monotonic_time()
            win.set_visible(False)   # hide, don't destroy
            return True

        def build(self):
            prov = Gtk.CssProvider()
            if hasattr(prov, "load_from_string"):
                prov.load_from_string(css)
            else:
                prov.load_from_data(css, -1)
            add = getattr(Gtk, "style_context_add_provider_for_display", None) \
                or Gtk.StyleContext.add_provider_for_display
            add(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)

            win = Gtk.ApplicationWindow(application=self, title="Calendar")
            win.add_css_class("cal-popup")
            win.set_decorated(False)
            win.connect("close-request", self.on_close)
            self.win = win

            self.popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.popup.add_css_class("popup")

            top = Gtk.Box(spacing=8)
            seg = Gtk.Box()
            seg.add_css_class("segbox")
            self.btn_en = Gtk.Button(label="EN")
            self.btn_fa = Gtk.Button(label="FA")
            for b, m in ((self.btn_en, "en"), (self.btn_fa, "fa")):
                b.add_css_class("seg")
                b.connect("clicked", lambda _b, m=m: self.set_mode(m))
                seg.append(b)
            spacer = Gtk.Box(hexpand=True)
            today = Gtk.Button(label="\U000f00f6  Today")
            today.add_css_class("today-btn")
            today.connect("clicked", lambda *_: self.go_today())
            top.append(seg)
            top.append(spacer)
            top.append(today)
            self.popup.append(top)

            nav = Gtk.Box(spacing=8, margin_top=4)
            self.prev = Gtk.Button(label="\U000f0141")
            self.next = Gtk.Button(label="\U000f0142")
            # left/right buttons: in Persian (right-to-left) the left one goes forward
            for b, step in ((self.prev, -1), (self.next, 1)):
                b.add_css_class("nav")
                b.connect("clicked", lambda _b, s=step: self.shift(-s if self.mode == "fa" else s))
            self.title = Gtk.Label(hexpand=True)
            self.title.add_css_class("title")
            nav.append(self.prev)
            nav.append(self.title)
            nav.append(self.next)
            self.popup.append(nav)

            self.grid = Gtk.Grid(column_spacing=4, row_spacing=2, column_homogeneous=True,
                                 margin_top=4)
            self.popup.append(self.grid)

            foot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            foot.add_css_class("footer")
            self.foot1 = Gtk.Label(xalign=0.5)
            self.foot1.add_css_class("primary")
            self.foot2 = Gtk.Label(xalign=0.5)
            foot.append(self.foot1)
            foot.append(self.foot2)
            self.popup.append(foot)

            # weather where you are: now + the next days
            self.wx_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.wx_card.add_css_class("wx-card")
            now_row = Gtk.Box(spacing=10)
            self.wx_icon = Gtk.Label()
            self.wx_icon.add_css_class("wx-now-icon")
            now_txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
            self.wx_now = Gtk.Label(xalign=0)
            self.wx_now.add_css_class("wx-now")
            self.wx_sub = Gtk.Label(xalign=0)
            self.wx_sub.add_css_class("wx-now-sub")
            now_txt.append(self.wx_now)
            now_txt.append(self.wx_sub)
            now_txt.set_hexpand(True)
            now_row.append(self.wx_icon)
            now_row.append(now_txt)
            self.wx_city = Gtk.Button(valign=Gtk.Align.CENTER, tooltip_text="Choose the city")
            self.wx_city.add_css_class("wx-city")
            self.wx_city.connect("clicked", lambda *_: self.toggle_city_search())
            now_row.append(self.wx_city)
            self.wx_card.append(now_row)

            self.wx_pick = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                                        transition_duration=150)
            pick = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            self.wx_search = Gtk.SearchEntry(placeholder_text="Any city — Tehran, Isfahan, Berlin…")
            self.wx_search.add_css_class("wx-search")
            self.wx_search.connect("search-changed", lambda *_: self.find_city())
            self.wx_search.connect("activate", lambda *_: self.pick_city(0))
            pick.append(self.wx_search)
            self.wx_results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            self.wx_results.add_css_class("wx-results")
            self.wx_results.connect("row-activated", lambda _l, r: self.pick_city(r.get_index()))
            pick.append(self.wx_results)
            self.wx_pick.set_child(pick)
            self.wx_card.append(self.wx_pick)
            self.city_hits = []
            self.city_seq = 0
            self.wx_days = Gtk.Box(homogeneous=True, spacing=4)
            self.wx_card.append(self.wx_days)
            self.wx_card.set_visible(False)
            self.popup.append(self.wx_card)

            keys = Gtk.EventControllerKey()
            keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            keys.connect("key-pressed", self.on_key)
            win.add_controller(keys)

            if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
                LS.init_for_window(win)
                LS.set_namespace(win, "calendar-popup")
                LS.set_layer(win, LS.Layer.OVERLAY)
                for e in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
                    LS.set_anchor(win, e, True)
                LS.set_exclusive_zone(win, -1)
                LS.set_keyboard_mode(win, LS.KeyboardMode.EXCLUSIVE)
                popup_backdrop.attach(win)   # clicks on the other screens close it too
                backdrop = Gtk.Box(hexpand=True, vexpand=True)
                backdrop.add_css_class("backdrop")
                click = Gtk.GestureClick()
                click.connect("pressed", lambda *_: win.close())
                backdrop.add_controller(click)
                self.popup.set_halign(Gtk.Align.START)
                self.popup.set_valign(Gtk.Align.START)
                self.popup.set_margin_top(72)
                self.popup.set_margin_start(300)
                overlay = Gtk.Overlay()
                overlay.set_child(backdrop)
                overlay.add_overlay(self.popup)
                win.set_child(overlay)
            else:
                win.set_child(self.popup)
                win.connect("notify::is-active", lambda w, _p: None if w.is_active() else w.close())

            # roll over at midnight if left open
            GLib.timeout_add_seconds(60, self._tick)

        def _tick(self):
            if self.win.get_visible() and dt.date.today() != self.today:
                self.today = dt.date.today()
                self.render()
            return True

        def go_today(self):
            self.selected = self.today
            self.set_view_to(self.today)
            self.render()

        def on_key(self, _c, keyval, _code, _state):
            rtl = self.mode == "fa"
            if self.wx_pick.get_reveal_child():
                if keyval == Gdk.KEY_Escape:
                    self.wx_pick.set_reveal_child(False)
                    return True
                return False             # typing a city: leave the keys to the search box
            if keyval == Gdk.KEY_Escape:
                self.win.close()
            elif keyval in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
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

        def render(self):
            fa_mode = self.mode == "fa"
            direction = Gtk.TextDirection.RTL if fa_mode else Gtk.TextDirection.LTR
            for w in (self.grid, self.title):
                w.set_direction(direction)
            (self.popup.add_css_class if fa_mode else self.popup.remove_css_class)("fa")
            for b, on in ((self.btn_en, not fa_mode), (self.btn_fa, fa_mode)):
                (b.add_css_class if on else b.remove_css_class)("on")

            title, heads, cells = month_cells(self.mode, self.year, self.month)
            self.title.set_label(title)

            while (c := self.grid.get_first_child()) is not None:
                self.grid.remove(c)
            weekend_col = 6 if fa_mode else None
            for i, h in enumerate(heads):
                lbl = Gtk.Label(label=h)
                lbl.add_css_class("head")
                if (fa_mode and i == weekend_col) or (not fa_mode and i >= 5):
                    lbl.add_css_class("weekend")
                self.grid.attach(lbl, i, 0, 1, 1)

            rows = 6 if any(cells[35:]) else 5
            for idx in range(rows * 7):
                cell = cells[idx]
                r, c = idx // 7 + 1, idx % 7
                if cell is None:
                    self.grid.attach(Gtk.Box(), c, r, 1, 1)
                    continue
                d, main_txt, sub_txt, weekend = cell
                btn = Gtk.Button()
                btn.add_css_class("day")
                if weekend:
                    btn.add_css_class("weekend")
                if d == self.today:
                    btn.add_css_class("today")
                if d == self.selected:
                    btn.add_css_class("selected")
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
                m = Gtk.Label(label=main_txt)
                m.add_css_class("main")
                s = Gtk.Label(label=sub_txt)
                s.add_css_class("sub")
                box.append(m)
                box.append(s)
                btn.set_child(box)
                btn.set_tooltip_text(" · ".join(today_line(self.mode, d)))
                btn.connect("clicked", lambda _b, d=d: self.select(d))
                self.grid.attach(btn, c, r, 1, 1)

            a, b = today_line(self.mode, self.selected)
            self.foot1.set_label(a)
            self.foot2.set_label(b)

        def select(self, d):
            self.selected = d
            self.render()

    sys.exit(Cal().run([sys.argv[0]]))


if __name__ == "__main__":
    main()
