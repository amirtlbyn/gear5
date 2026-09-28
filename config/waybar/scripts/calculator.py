#!/usr/bin/env python3
"""
Calculator popup (SUPER+C), Everforest style, powered by qalc (Qalculate).

  calculator.py [THEME] [--hidden]

Tabs (Tab / Shift+Tab, or Alt+1..5):
- Standard / Scientific: type anything qalc understands, with a live answer as you
  type: 12*(3+4), 15% * 240, sqrt(2), sin(30), 5 km to mi, 100 USD to EUR,
  solve(x^2 - 5x + 6 = 0), today + 90 days, 0xFF to bin, integrate(x^2, 0, 3) ...
  Enter keeps the answer and adds it to the history; click the answer to copy it.
- Programmer: HEX / DEC / OCT / BIN side by side, AND OR XOR NOT << >>.
- Converter: pick a kind (length, weight, temperature, currency, data ...) and see
  the amount in every unit at once; click a unit to make it the target.
- Date: days between two dates, and a date plus/minus days, weeks, months, years
  (with the Persian date too).

Stays running hidden after the first use, so it opens instantly; Esc or a click
outside closes it.
"""
import ast
import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading

LAYER_LIBS = [
    "/usr/lib64/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so.0",
]
if not os.environ.get("CALCULATOR_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["CALCULATOR_PRELOADED"] = "1"
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

THEME = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else palette.current()
WIDTH = 480
HISTORY_FILE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                            "calculator", "history.json")
HISTORY_MAX = 50

P = palette.load(THEME)

CSS = fonts.swap("".join(f"@define-color {k} {v};\n" for k, v in P.items()) + """
window.calculator { background: transparent; }
.backdrop { background: alpha(black, 0.18); }

.popup {
  background: @bg0; color: @fg;
  border-radius: 22px;
  border: 1px solid alpha(@fg, 0.07);
  box-shadow: 0 22px 50px @shadow, 0 2px 6px alpha(black, 0.25);
  padding: 16px;
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif;
  font-weight: bold; font-size: 14px;
}

/* tabs */
.tabs { background: alpha(@fg, 0.07); border-radius: 14px; padding: 4px; margin-bottom: 12px; }
.tabs button {
  background: transparent; color: @grey; border: none; box-shadow: none;
  border-radius: 10px; padding: 6px 4px; min-height: 0; font-size: 12px;
}
.tabs button:hover { color: @fg; background: alpha(@fg, 0.06); }
.tabs button.active { background: @bg2; color: @fg; box-shadow: 0 2px 6px alpha(black, 0.25); }

/* display */
.display {
  background-image: linear-gradient(160deg, alpha(@aqua, 0.10), alpha(@bg1, 0.0) 60%), linear-gradient(@bg1, @bg1);
  border-radius: 18px; border: 1px solid alpha(@fg, 0.05); border-bottom: 3px solid @edge;
  padding: 12px 16px;
}
.display entry, .field entry, entry.field {
  background: transparent; color: @fg; border: none; box-shadow: none; outline: none;
  font-size: 22px; min-height: 36px; padding: 0; caret-color: @green;
}
.prev { color: @grey; font-weight: normal; font-size: 12px; }
.answer { font-size: 30px; color: @green; }
.answer.preview { color: alpha(@fg, 0.45); }
.answer.error { color: @red; font-size: 14px; }
.hint { color: alpha(@grey, 0.8); font-weight: normal; font-size: 11px; margin: 6px 4px 0 4px; }
.badge {
  font-size: 10px; letter-spacing: 1px; border-radius: 6px; padding: 1px 7px;
  background: alpha(@yellow, 0.18); color: @yellow;
}
.toast { color: @green; font-size: 11px; }

/* keypad */
.keys { margin-top: 12px; }
.keys button {
  background: @bg1; color: @fg;
  border: none; border-bottom: 3px solid @edge; border-radius: 14px; box-shadow: none;
  min-height: 44px; padding: 0; font-size: 17px;
}
.keys button:hover { background: @bg2; }
.keys button:active { margin-top: 2px; border-bottom-width: 1px; }
.keys button.fn { background: @bg2; color: @blue; font-size: 14px; }
.keys button.fn:hover { background: @bg3; }
.keys button.op { background: alpha(@orange, 0.16); color: @orange; font-size: 19px; }
.keys button.op:hover { background: alpha(@orange, 0.26); }
.keys button.clear { background: alpha(@red, 0.16); color: @red; }
.keys button.eq { background-image: linear-gradient(135deg, @aqua, @green); color: @on_accent; font-size: 20px; }
.keys button.toggle.on { background: @purple; color: @on_accent; }
.keys button:disabled { color: alpha(@fg, 0.2); background: alpha(@bg1, 0.5); }
.sci button { min-height: 36px; font-size: 13px; }

/* history */
.section { color: @grey; font-size: 11px; letter-spacing: 2px; margin: 12px 4px 4px 4px; }
list.hist { background: transparent; }
list.hist > row { background: transparent; border-radius: 10px; padding: 4px 8px; }
list.hist > row:hover { background: alpha(@fg, 0.06); }
.hist-expr { color: @grey; font-weight: normal; font-size: 12px; }
.hist-res { color: @fg; font-size: 13px; }
button.link {
  background: transparent; color: @grey; border: none; box-shadow: none;
  padding: 0 6px; min-height: 0; font-size: 11px;
}
button.link:hover { color: @red; }

/* programmer */
.bases { margin-top: 10px; }
.base-row { background: @bg1; border-radius: 12px; padding: 7px 12px; border-bottom: 3px solid @edge; }
.base-row:hover { background: @bg2; }
.base-row.active { background-image: linear-gradient(90deg, alpha(@blue, 0.25), @bg1); }
.base-name { color: @blue; font-size: 11px; letter-spacing: 1px; min-width: 38px; }
.base-val { font-size: 13px; }

/* converter + date */
.chips { margin-bottom: 8px; }
.chips button {
  background: @bg1; color: @fg; border: none; box-shadow: none;
  border-radius: 10px; padding: 4px 8px; min-height: 0; font-size: 11px;
  border-bottom: 2px solid @edge;
}
.chips button:hover { background: @bg2; }
.chips button.active { background: @green; color: @on_accent; }
.field {
  background: @bg1; border-radius: 14px; border-bottom: 3px solid @edge; padding: 6px 12px;
}
.field-label { color: @grey; font-size: 11px; letter-spacing: 1px; }
.popup dropdown > button {
  background: @bg2; color: @fg; border: none; border-radius: 10px; box-shadow: none;
  padding: 2px 10px; min-height: 0;
}
popover > contents { background: @bg1; color: @fg; border-radius: 12px; }
popover listview > row:selected, popover listview > row:hover { background: @bg3; }
button.swap {
  background: @bg2; color: @green; border: none; box-shadow: none; border-radius: 50%;
  min-width: 34px; min-height: 34px; padding: 0; font-size: 16px;
}
button.swap:hover { background: @bg3; }
list.units { background: transparent; }
list.units > row { background: transparent; border-radius: 10px; padding: 5px 10px; }
list.units > row:hover { background: alpha(@fg, 0.06); }
list.units > row.target { background: alpha(@green, 0.14); }
.unit-name { color: @grey; font-size: 12px; }
.unit-val { font-size: 13px; }
.big { font-size: 26px; color: @green; }
.small { color: @grey; font-weight: normal; font-size: 12px; }
button.pill {
  background: @bg2; color: @fg; border: none; box-shadow: none; border-radius: 10px;
  padding: 4px 10px; min-height: 0; font-size: 12px; border-bottom: 2px solid @edge;
}
button.pill:hover { background: @bg3; }
button.pill.active { background: @blue; color: @on_accent; }
""")

I_COPY, I_SWAP, I_BACK, I_CAL, I_REFRESH = "\U000f018f", "\U000f04e1", "\U000f006e", "\U000f00f0", "\U000f0450"


# ---------------------------------------------------------------------------
# qalc
# ---------------------------------------------------------------------------
BASE_WORDS = {"hex", "hexadecimal", "bin", "binary", "oct", "octal", "dec", "decimal", "base",
              "optimal", "mixed", "fraction", "factors", "partial", "roman", "time", "utc",
              "calendars", "bijective", "sexagesimal", "duo", "duodecimal", "polar", "rectangular",
              "exponential", "cis", "angle", "prefix", "sci", "eng", "si", "cgs", "bases", "unicode"}
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def prepare(expr, deg):
    """Friendlier input for qalc: calculator symbols, 'x% of y', and single-unit conversions."""
    e = expr.strip()
    for a, b in (("×", "*"), ("÷", "/"), ("−", "-"), ("π", "pi"), ("√", "sqrt")):
        e = e.replace(a, b)
    e = re.sub(r"([\d.]+)\s*%\s*of\s+", r"(\1/100)*", e, flags=re.I)
    # "25 C to F" → degrees, not coulombs and farads
    e = re.sub(r"(?<=[\d\s])([CFcf])(?=\s+(?:to|in|->|→)\s)", lambda m: "°" + m.group(1).upper(), e)
    e = re.sub(r"\b(to|in|->|→)(\s+)-?([CFcf])$", lambda m: f"{m.group(1)}{m.group(2)}°{m.group(3).upper()}", e)
    # "5 km to mi" → one unit (3.1 mi), not "3 mi + 188 yd"
    e = re.sub(r"\b(to|->|→|in)\s+(?![-+])([^\s,]+)",
               lambda m: m.group(0) if m.group(2).lower() in BASE_WORDS or m.group(2).isdigit()
               else f"{m.group(1)} -{m.group(2)}", e)
    return e


def qalc_many(exprs, deg=True):
    """Evaluate several expressions with one qalc run. Returns a list of answers (or None)."""
    if not exprs:
        return []
    args = ["qalc", "-t", "-set", f"angle {2 if deg else 1}"]
    try:
        r = subprocess.run(args, input="\n".join(e.replace("\n", " ") for e in exprs) + "\n",
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return [None] * len(exprs)
    out = ANSI.sub("", r.stdout)
    answers = []
    for block in re.split(r"^> ", out, flags=re.M)[1:]:
        lines = [ln.strip() for ln in block.splitlines()[1:] if ln.strip()]
        answers.append(nice(lines[-1]) if lines else None)
    answers += [None] * (len(exprs) - len(answers))
    return answers[: len(exprs)]


def qalc_one(expr, deg=True):
    """One expression; returns (answer, error)."""
    try:
        r = subprocess.run(["qalc", "-t", "-set", f"angle {2 if deg else 1}", expr],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None, "Took too long"
    lines = [ANSI.sub("", ln).strip() for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]
    errs = [ln for ln in lines if ln.lower().startswith("error")]
    if errs:
        return None, errs[-1].split(":", 1)[-1].strip()
    ans = next((ln for ln in reversed(lines) if not ln.lower().startswith("warning")), None)
    return nice(ans), None


NICE_UNITS = [("a_j", "yr"), ("kcal_th", "kcal"), ("cal_th", "cal"), ("fl_oz", "fl oz")]


def nice(answer):
    if answer and len(answer) > 1 and answer[0] == answer[-1] == '"':
        answer = answer[1:-1]       # dates come back quoted
    if answer:
        for a, b in NICE_UNITS:
            answer = re.sub(rf"\b{a}\b", b, answer)
    return answer


def run_bg(work, done):
    def target():
        result = work()
        GLib.idle_add(lambda: (done(result), False)[1])
    threading.Thread(target=target, daemon=True).start()


def copy(text):
    try:
        subprocess.Popen(["wl-copy", "--", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


def button(text, css=None, cb=None, tooltip=None):
    b = Gtk.Button(label=text)
    for c in (css or "").split():
        b.add_css_class(c)
    if tooltip:
        b.set_tooltip_text(tooltip)
    if cb:
        b.connect("clicked", lambda *_: cb())
    return b


# ---------------------------------------------------------------------------
# programmer mode: exact integer maths in any base
# ---------------------------------------------------------------------------
BASES = {"HEX": 16, "DEC": 10, "OCT": 8, "BIN": 2}
PROG_OPS = (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod, ast.BitAnd, ast.BitOr, ast.BitXor,
            ast.LShift, ast.RShift, ast.Pow)


def prog_eval(text, base):
    """Integer expression in the given base; words AND OR XOR NOT MOD work too."""
    t = text.strip()
    if not t:
        return None
    t = re.sub(r"\bAND\b", "&", t, flags=re.I)
    t = re.sub(r"\bXOR\b", "^", t, flags=re.I)
    t = re.sub(r"\bOR\b", "|", t, flags=re.I)
    t = re.sub(r"\bNOT\b", "~", t, flags=re.I)
    t = re.sub(r"\bMOD\b", "%", t, flags=re.I)
    t = t.replace("÷", "/").replace("×", "*").replace("−", "-")
    t = re.sub(r"(?<![/])/(?!/)", "//", t)
    t = t.replace("^", "#XOR#").replace("**", "#POW#")
    digits = "0-9A-Fa-f" if base == 16 else "0-9"

    def num(m):
        return str(int(m.group(0), base))
    try:
        t = re.sub(rf"\b[{digits}]+\b", num, t)
    except ValueError:
        raise ValueError("digit not allowed in this base")
    t = t.replace("#XOR#", "^").replace("#POW#", "**")
    tree = ast.parse(t, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Load)):
            continue
        if isinstance(node, ast.BinOp) and isinstance(node.op, PROG_OPS):
            continue
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Invert)):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            continue
        if isinstance(node, (ast.operator, ast.unaryop)):
            continue
        raise ValueError("not an integer expression")
    return int(eval(compile(tree, "<prog>", "eval"), {"__builtins__": {}}))


def fmt_base(n, base, bits=64):
    if n < 0:
        n &= (1 << bits) - 1     # two's complement view
    if base == 16:
        s, groups = format(n, "X"), []
        while s:
            groups.insert(0, s[-4:])
            s = s[:-4]
        return " ".join(groups)
    if base == 2:
        s = format(n, "b")
        s = s.zfill((len(s) + 3) // 4 * 4)
        return " ".join(s[i:i + 4] for i in range(0, len(s), 4))
    if base == 8:
        return format(n, "o")
    return f"{n:,}"


# ---------------------------------------------------------------------------
# converter
# ---------------------------------------------------------------------------
UNITS = {
    "Length":      [("m", "metre"), ("km", "kilometre"), ("cm", "centimetre"), ("mm", "millimetre"),
                    ("mi", "mile"), ("yd", "yard"), ("ft", "foot"), ("in", "inch"), ("nmi", "nautical mile")],
    "Weight":      [("kg", "kilogram"), ("g", "gram"), ("mg", "milligram"), ("t", "tonne"),
                    ("lb", "pound"), ("oz", "ounce"), ("stone", "stone")],
    "Temperature": [("°C", "celsius"), ("°F", "fahrenheit"), ("K", "kelvin")],
    "Volume":      [("L", "litre"), ("mL", "millilitre"), ("m^3", "cubic metre"), ("gal", "US gallon"),
                    ("cup", "US cup"), ("fl_oz", "US fluid ounce"), ("tablespoon", "tablespoon"),
                    ("teaspoon", "teaspoon")],
    "Area":        [("m^2", "square metre"), ("km^2", "square km"), ("ha", "hectare"), ("acre", "acre"),
                    ("ft^2", "square foot"), ("mi^2", "square mile")],
    "Speed":       [("km/h", "km per hour"), ("m/s", "metre per second"), ("mph", "mile per hour"),
                    ("knot", "knot"), ("ft/s", "foot per second")],
    "Time":        [("s", "second"), ("min", "minute"), ("h", "hour"), ("d", "day"), ("week", "week"),
                    ("month", "month"), ("year", "year"), ("ms", "millisecond")],
    "Data":        [("B", "byte"), ("kB", "kilobyte"), ("MB", "megabyte"), ("GB", "gigabyte"),
                    ("TB", "terabyte"), ("KiB", "kibibyte"), ("MiB", "mebibyte"), ("GiB", "gibibyte"),
                    ("bit", "bit"), ("Mbit", "megabit")],
    "Energy":      [("J", "joule"), ("kJ", "kilojoule"), ("cal", "calorie"), ("kcal", "kilocalorie"),
                    ("Wh", "watt hour"), ("kWh", "kilowatt hour"), ("eV", "electronvolt"), ("Btu", "BTU")],
    "Pressure":    [("Pa", "pascal"), ("kPa", "kilopascal"), ("bar", "bar"), ("atm", "atmosphere"),
                    ("psi", "psi"), ("mmHg", "mm of mercury")],
    "Currency":    [("USD", "US dollar"), ("EUR", "euro"), ("GBP", "British pound"), ("AED", "UAE dirham"),
                    ("TRY", "Turkish lira"), ("CNY", "Chinese yuan"), ("JPY", "Japanese yen"),
                    ("CAD", "Canadian dollar"), ("AUD", "Australian dollar"), ("CHF", "Swiss franc"),
                    ("INR", "Indian rupee"), ("RUB", "Russian rouble"), ("BTC", "bitcoin")],
}


# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------
def g2j(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    jm = 1 + days // 31 if days < 186 else 7 + (days - 186) // 30
    jd = 1 + (days % 31 if days < 186 else (days - 186) % 30)
    return jy, jm, jd


JMONTHS = ["Farvardin", "Ordibehesht", "Khordad", "Tir", "Mordad", "Shahrivar",
           "Mehr", "Aban", "Azar", "Dey", "Bahman", "Esfand"]


def parse_date(text):
    t = text.strip().lower()
    today = dt.date.today()
    if t in ("", "today", "now"):
        return today
    if t == "tomorrow":
        return today + dt.timedelta(days=1)
    if t == "yesterday":
        return today - dt.timedelta(days=1)
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", t)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    raise ValueError("Use YYYY-MM-DD, today, tomorrow or yesterday")


def add_months(d, months):
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    last = [31, 29 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.date(y, m, min(d.day, last))


def describe(d):
    jy, jm, jd = g2j(d.year, d.month, d.day)
    return f"{d.strftime('%A, %d %B %Y')}", f"{jd} {JMONTHS[jm - 1]} {jy}"


def span(a, b):
    """Years, months, days between two dates (a <= b)."""
    y, m = b.year - a.year, b.month - a.month
    if b.day < a.day:
        m -= 1
    if m < 0:
        y, m = y - 1, m + 12
    d = (b - add_months(a, y * 12 + m)).days
    return y, m, d


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
class Calculator(Gtk.Application):
    TABS = [("std", "Standard"), ("sci", "Scientific"), ("prog", "Programmer"),
            ("conv", "Converter"), ("date", "Date")]

    def __init__(self):
        super().__init__(application_id="io.local.calculator")
        self.win = None
        self.deg = True
        self.tab = "std"
        self.answer = None       # last shown answer (for copy / Enter)
        self.calc_seq = 0
        self.history = self.load_history()
        self.prog_base = "DEC"
        self.conv_kind = "Length"
        self.conv_target = 1
        self.conv_seq = 0

    # ----- life cycle ----------------------------------------------------------
    def do_activate(self):
        if self.win is not None:
            if self.win.get_visible():
                self.win.close()
            elif GLib.get_monotonic_time() - getattr(self, "closed_at", 0) > 400_000:
                self.show_popup()
            return
        self.hold()   # keep running hidden, so the next open is instant
        self.build()
        if "--hidden" not in sys.argv:
            self.show_popup()

    def show_popup(self):
        self.win.present()
        self.focus_tab()

    def on_close(self, win):
        self.closed_at = GLib.get_monotonic_time()
        win.set_visible(False)
        return True

    # ----- layout ---------------------------------------------------------------
    def build(self):
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER)
        win = Gtk.ApplicationWindow(application=self, title="Calculator")
        win.add_css_class("calculator")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win

        popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.add_css_class("popup")
        popup.set_size_request(WIDTH, -1)

        tabs = Gtk.Box(homogeneous=True)
        tabs.add_css_class("tabs")
        self.tab_btns = {}
        for key, name in self.TABS:
            b = button(name, cb=lambda k=key: self.set_tab(k))
            self.tab_btns[key] = b
            tabs.append(b)
        popup.append(tabs)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=120,
                               vhomogeneous=False, interpolate_size=True)
        self.stack.add_named(self.build_calc(), "calc")
        self.stack.add_named(self.build_prog(), "prog")
        self.stack.add_named(self.build_conv(), "conv")
        self.stack.add_named(self.build_date(), "date")
        popup.append(self.stack)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)

        if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
            LS.init_for_window(win)
            LS.set_namespace(win, "calculator")
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
        self.set_tab("std")

    # ----- standard / scientific ----------------------------------------------------
    def build_calc(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        disp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        disp.add_css_class("display")
        top = Gtk.Box(spacing=8)
        self.prev = label(css="prev", xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.START)
        top.append(self.prev)
        self.angle_badge = label("DEG", "badge")
        top.append(self.angle_badge)
        disp.append(top)
        self.entry = Gtk.Entry(placeholder_text="Type anything… 5 km to mi, 20% of 80", hexpand=True)
        self.entry.connect("changed", lambda *_: self.preview())
        self.entry.connect("activate", lambda *_: self.equals())
        disp.append(self.entry)
        ans_row = Gtk.Box(spacing=8)
        self.ans = label(css="answer preview", xalign=1, hexpand=True, selectable=False,
                         ellipsize=Pango.EllipsizeMode.START)
        self.ans.set_tooltip_text("Click to copy")
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self.copy_answer())
        self.ans.add_controller(click)
        self.toast = label(css="toast")
        ans_row.append(self.toast)
        ans_row.append(self.ans)
        disp.append(ans_row)
        page.append(disp)
        page.append(label("Enter keeps the answer · click it to copy · Tab switches tabs", "hint", xalign=0))

        # scientific keys
        self.sci = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN, transition_duration=150)
        sg = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True, row_homogeneous=True)
        sg.add_css_class("keys")
        sg.add_css_class("sci")
        self.deg_btn = button("DEG", "fn toggle on", self.toggle_deg, "Degrees / radians")
        sci_keys = [
            [("sin", "sin("), ("cos", "cos("), ("tan", "tan("), ("π", "π"), ("e", "e"), (None, self.deg_btn)],
            [("asin", "asin("), ("acos", "acos("), ("atan", "atan("), ("ln", "ln("), ("log", "log10("), ("log₂", "log2(")],
            [("x²", "^2"), ("xʸ", "^"), ("√", "√("), ("∛", "cbrt("), ("eˣ", "exp("), ("10ˣ", "10^")],
            [("(", "("), (")", ")"), ("n!", "!"), ("1/x", "INV"), ("|x|", "abs("), ("ans", "ANS")],
        ]
        for r, row in enumerate(sci_keys):
            for c, (text, ins) in enumerate(row):
                w = ins if text is None else button(text, "fn", lambda i=ins: self.press(i))
                sg.attach(w, c, r, 1, 1)
        self.sci.set_child(sg)
        page.append(self.sci)

        grid = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True, row_homogeneous=True)
        grid.add_css_class("keys")
        layout = [
            [("C", "CLEAR", "clear"), (I_BACK, "BACK", "fn"), ("%", "%", "fn"), ("÷", "÷", "op")],
            [("7", "7", ""), ("8", "8", ""), ("9", "9", ""), ("×", "×", "op")],
            [("4", "4", ""), ("5", "5", ""), ("6", "6", ""), ("−", "−", "op")],
            [("1", "1", ""), ("2", "2", ""), ("3", "3", ""), ("+", "+", "op")],
            [("±", "NEG", "fn"), ("0", "0", ""), (".", ".", ""), ("=", "EQ", "eq")],
        ]
        for r, row in enumerate(layout):
            for c, (text, ins, css) in enumerate(row):
                grid.attach(button(text, css, lambda i=ins: self.press(i)), c, r, 1, 1)
        page.append(grid)

        head = Gtk.Box(spacing=6)
        head.append(label("HISTORY", "section", xalign=0, hexpand=True))
        head.append(button("clear", "link", self.clear_history))
        page.append(head)
        self.hist = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.hist.add_css_class("hist")
        self.hist.connect("row-activated", lambda _l, row: self.use_history(row))
        self.hist_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                              propagate_natural_height=True, max_content_height=150)
        self.hist_scroll.set_child(self.hist)
        page.append(self.hist_scroll)
        self.render_history()
        return page

    def press(self, key):
        e = self.entry
        text = e.get_text()
        if key == "CLEAR":
            e.set_text("")
            self.prev.set_label("")
        elif key == "BACK":
            pos = e.get_position()
            if pos > 0:
                e.delete_text(pos - 1, pos)
        elif key == "EQ":
            self.equals()
        elif key == "NEG":
            e.set_text(f"-({text})" if text and not text.startswith("-(") else text[2:-1] if text.startswith("-(") else "-")
            e.set_position(-1)
        elif key == "INV":
            e.set_text(f"1/({text})" if text else "1/")
            e.set_position(-1)
        elif key == "ANS":
            self.insert(self.history[0]["res"] if self.history else "")
        else:
            self.insert(key)
        e.grab_focus_without_selecting()

    def insert(self, s):
        e = self.entry
        start, end = e.get_selection_bounds() or (e.get_position(), e.get_position())
        if start != end:
            e.delete_text(start, end)
        pos = e.get_position()
        e.insert_text(s, pos)
        e.set_position(pos + len(s))

    def preview(self):
        text = self.entry.get_text()
        self.calc_seq += 1
        seq = self.calc_seq
        if not text.strip():
            self.show_answer("", preview=True)
            return
        expr = prepare(text, self.deg)

        def work():
            return qalc_one(expr, self.deg)

        def done(res):
            if seq != self.calc_seq:
                return        # you typed more meanwhile
            ans, err = res
            if err or ans is None:
                self.show_answer("", preview=True)
            elif ans.strip() == text.strip():
                self.show_answer("", preview=True)
            else:
                self.show_answer(ans, preview=True)
        GLib.timeout_add(90, lambda: (run_bg(work, done) if seq == self.calc_seq else None, False)[1])

    def equals(self):
        text = self.entry.get_text().strip()
        if not text:
            return
        self.calc_seq += 1
        seq = self.calc_seq
        expr = prepare(text, self.deg)

        def done(res):
            if seq != self.calc_seq:
                return
            ans, err = res
            if err or not ans:
                self.show_answer(err or "Can't calculate that", error=True)
                return
            self.show_answer(ans)
            self.prev.set_label(f"{text} =")
            self.add_history(text, ans)
            self.calc_seq += 1       # the text change below must not re-preview
            self.entry.set_text(ans.replace("−", "-"))
            self.entry.set_position(-1)
            self.calc_seq += 1
            self.show_answer(ans)
        run_bg(lambda: qalc_one(expr, self.deg), done)

    def show_answer(self, text, preview=False, error=False):
        self.answer = None if (error or not text) else text
        self.ans.set_label(("= " + text) if (text and not error) else text)
        for c, on in (("preview", preview), ("error", error)):
            (self.ans.add_css_class if on else self.ans.remove_css_class)(c)

    def copy_answer(self):
        if self.answer:
            copy(self.answer.replace("−", "-"))
            self.toast.set_label(f"{I_COPY} copied")
            GLib.timeout_add(1200, lambda: (self.toast.set_label(""), False)[1])

    def toggle_deg(self):
        self.deg = not self.deg
        self.deg_btn.set_label("DEG" if self.deg else "RAD")
        self.angle_badge.set_label("DEG" if self.deg else "RAD")
        self.preview()

    # history
    @staticmethod
    def load_history():
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)[:HISTORY_MAX]
        except (OSError, ValueError):
            return []

    def save_history(self):
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            with open(HISTORY_FILE, "w") as f:
                json.dump(self.history[:HISTORY_MAX], f)
        except OSError:
            pass

    def add_history(self, expr, res):
        if self.history and self.history[0] == {"expr": expr, "res": res}:
            return
        self.history.insert(0, {"expr": expr, "res": res})
        del self.history[HISTORY_MAX:]
        self.save_history()
        self.render_history()

    def clear_history(self):
        self.history = []
        self.save_history()
        self.render_history()

    def render_history(self):
        while (child := self.hist.get_first_child()) is not None:
            self.hist.remove(child)
        for h in self.history:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(spacing=8)
            box.append(label(h["expr"], "hist-expr", xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
            box.append(label("= " + h["res"], "hist-res", xalign=1, ellipsize=Pango.EllipsizeMode.START))
            row.set_child(box)
            row.set_tooltip_text("Click to use · the answer is copied")
            row.item = h
            self.hist.append(row)
        self.hist_scroll.set_visible(bool(self.history))

    def use_history(self, row):
        res = row.item["res"]
        copy(res.replace("−", "-"))
        self.entry.set_text(res.replace("−", "-"))
        self.entry.set_position(-1)
        self.entry.grab_focus_without_selecting()

    # ----- programmer ---------------------------------------------------------------
    def build_prog(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        disp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        disp.add_css_class("display")
        self.prog_entry = Gtk.Entry(placeholder_text="FF AND 0F · 1 << 8 · 255 XOR 170", hexpand=True)
        self.prog_entry.connect("changed", lambda *_: self.prog_update())
        self.prog_entry.connect("activate", lambda *_: self.prog_equals())
        disp.append(self.prog_entry)
        self.prog_err = label(css="prev", xalign=1)
        disp.append(self.prog_err)
        page.append(disp)

        bases = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        bases.add_css_class("bases")
        self.base_rows = {}
        for name in BASES:
            row = Gtk.Box(spacing=10)
            row.add_css_class("base-row")
            row.append(label(name, "base-name", xalign=0))
            val = label("0", "base-val", xalign=0, hexpand=True, wrap=True,
                        wrap_mode=Pango.WrapMode.CHAR, selectable=False)
            row.append(val)
            click = Gtk.GestureClick()
            click.connect("released", lambda *_a, n=name: self.set_base(n))
            row.add_controller(click)
            row.set_tooltip_text(f"Type in {name} (the value is copied)")
            self.base_rows[name] = (row, val)
            bases.append(row)
        page.append(bases)

        grid = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True, row_homogeneous=True)
        grid.add_css_class("keys")
        grid.add_css_class("sci")
        layout = [
            [("AND", " AND ", "fn"), ("OR", " OR ", "fn"), ("XOR", " XOR ", "fn"), ("NOT", "NOT ", "fn"), ("<<", " << ", "fn"), (">>", " >> ", "fn")],
            [("A", "A", "hexd"), ("B", "B", "hexd"), ("C", "C", "hexd"), ("(", "(", "fn"), (")", ")", "fn"), ("MOD", " MOD ", "fn")],
            [("D", "D", "hexd"), ("E", "E", "hexd"), ("F", "F", "hexd"), ("7", "7", "d8"), ("8", "8", "d10"), ("9", "9", "d10")],
            [("4", "4", "d8"), ("5", "5", "d8"), ("6", "6", "d8"), ("1", "1", "d2"), ("2", "2", "d8"), ("3", "3", "d8")],
            [("0", "0", "d2"), ("÷", " / ", "op"), ("×", " * ", "op"), ("−", " - ", "op"), ("+", " + ", "op"), ("=", "EQ", "eq")],
        ]
        self.digit_btns = []
        for r, row in enumerate(layout):
            for c, (text, ins, kind) in enumerate(row):
                css = kind if kind in ("fn", "op", "eq") else ""
                b = button(text, css, lambda i=ins: self.prog_press(i))
                if kind in ("hexd", "d10", "d8", "d2"):
                    self.digit_btns.append((b, {"hexd": 16, "d10": 10, "d8": 8, "d2": 2}[kind]))
                grid.attach(b, c, r, 1, 1)
        page.append(grid)
        ctl = Gtk.Box(spacing=6, homogeneous=True, margin_top=6)
        ctl.add_css_class("keys")
        ctl.append(button("C", "clear", lambda: self.prog_entry.set_text("")))
        ctl.append(button(I_BACK, "fn", lambda: self.prog_press("BACK")))
        page.append(ctl)
        self.set_base("DEC", copy_value=False)
        return page

    def prog_press(self, key):
        e = self.prog_entry
        if key == "EQ":
            self.prog_equals()
        elif key == "BACK":
            pos = e.get_position()
            if pos > 0:
                e.delete_text(pos - 1, pos)
        else:
            pos = e.get_position()
            e.insert_text(key, pos)
            e.set_position(pos + len(key))
        e.grab_focus_without_selecting()

    def prog_value(self):
        try:
            return prog_eval(self.prog_entry.get_text(), BASES[self.prog_base]), None
        except (ValueError, SyntaxError, ZeroDivisionError, TypeError, OverflowError) as ex:
            return None, str(ex) if isinstance(ex, ValueError) else "…"

    def prog_update(self):
        n, err = self.prog_value()
        self.prog_err.set_label(err or "")
        for name, (_row, val) in self.base_rows.items():
            val.set_label(fmt_base(n, BASES[name]) if n is not None else "–")

    def prog_equals(self):
        n, _err = self.prog_value()
        if n is None:
            return
        base = BASES[self.prog_base]
        text = fmt_base(n, base).replace(" ", "").replace(",", "")
        self.prog_entry.set_text(text)
        self.prog_entry.set_position(-1)

    def set_base(self, name, copy_value=True):
        n, _err = self.prog_value() if hasattr(self, "prog_entry") else (None, None)
        if copy_value and n is not None:
            copy(fmt_base(n, BASES[name]).replace(" ", "").replace(",", ""))
        self.prog_base = name
        for other, (row, _v) in self.base_rows.items():
            (row.add_css_class if other == name else row.remove_css_class)("active")
        for b, needs in self.digit_btns:
            b.set_sensitive(BASES[name] >= needs)
        if n is not None:
            self.prog_entry.set_text(fmt_base(n, BASES[name]).replace(" ", "").replace(",", ""))
            self.prog_entry.set_position(-1)
        self.prog_update()

    # ----- converter -------------------------------------------------------------------
    def build_conv(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        chips = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=6,
                            column_spacing=4, row_spacing=4, homogeneous=True)
        chips.add_css_class("chips")
        self.kind_btns = {}
        for kind in UNITS:
            b = button(kind, cb=lambda k=kind: self.set_kind(k))
            self.kind_btns[kind] = b
            chips.append(b)
        page.append(chips)

        row = Gtk.Box(spacing=8)
        src = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        src.add_css_class("field")
        src.append(label("FROM", "field-label", xalign=0))
        srow = Gtk.Box(spacing=6)
        self.conv_amount = Gtk.Entry(text="1", hexpand=True)
        self.conv_amount.add_css_class("field")
        self.conv_amount.connect("changed", lambda *_: self.conv_update())
        self.conv_from = Gtk.DropDown(valign=Gtk.Align.CENTER)
        self.conv_from.connect("notify::selected", lambda *_: self.conv_update())
        srow.append(self.conv_amount)
        srow.append(self.conv_from)
        src.append(srow)
        row.append(src)
        swap = button(I_SWAP, "swap", self.conv_swap, "Swap")
        swap.set_valign(Gtk.Align.CENTER)
        row.append(swap)
        page.append(row)

        res = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=8)
        res.add_css_class("display")
        self.conv_big = label("", "big", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.conv_big.set_tooltip_text("Click to copy")
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self.conv_copy())
        self.conv_big.add_controller(click)
        self.conv_small = label("", "small", xalign=0)
        res.append(self.conv_big)
        res.append(self.conv_small)
        page.append(res)

        head = Gtk.Box(spacing=6)
        head.append(label("ALL UNITS", "section", xalign=0, hexpand=True))
        self.rates_btn = button(f"{I_REFRESH} update rates", "link", self.update_rates,
                                "Download the latest exchange rates")
        head.append(self.rates_btn)
        page.append(head)
        self.units_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.units_list.add_css_class("units")
        self.units_list.connect("row-activated", lambda _l, r: self.set_target(r.index))
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                    propagate_natural_height=True, max_content_height=260)
        scroll.set_child(self.units_list)
        page.append(scroll)
        self.set_kind("Length")
        return page

    def set_kind(self, kind):
        self.conv_kind = kind
        for k, b in self.kind_btns.items():
            (b.add_css_class if k == kind else b.remove_css_class)("active")
        units = UNITS[kind]
        self.conv_from.set_model(Gtk.StringList.new([u for u, _ in units]))
        self.conv_from.set_selected(0)
        self.conv_target = 1 if len(units) > 1 else 0
        self.rates_btn.set_visible(kind == "Currency")
        while (child := self.units_list.get_first_child()) is not None:
            self.units_list.remove(child)
        self.unit_vals = []
        for i, (u, name) in enumerate(units):
            row = Gtk.ListBoxRow()
            row.index = i
            box = Gtk.Box(spacing=8)
            box.append(label(name, "unit-name", xalign=0, hexpand=True))
            val = label("", "unit-val", xalign=1, ellipsize=Pango.EllipsizeMode.START)
            box.append(val)
            row.set_child(box)
            self.unit_vals.append((row, val))
            self.units_list.append(row)
        self.conv_update()

    def set_target(self, i):
        self.conv_target = i
        self.conv_update()

    def conv_swap(self):
        src = self.conv_from.get_selected()
        self.conv_from.set_selected(self.conv_target)
        self.conv_target = src
        self.conv_update()

    def conv_update(self):
        if not hasattr(self, "unit_vals"):
            return
        units = UNITS[self.conv_kind]
        src_i = self.conv_from.get_selected()
        if src_i >= len(units):
            return
        amount = self.conv_amount.get_text().strip() or "0"
        src = units[src_i][0]
        for i, (row, _v) in enumerate(self.unit_vals):
            (row.add_css_class if i == self.conv_target else row.remove_css_class)("target")
        self.conv_seq += 1
        seq = self.conv_seq
        exprs = [f"({amount}) {src} to -{u}" for u, _n in units]

        def done(answers):
            if seq != self.conv_seq:
                return
            for (row, val), a in zip(self.unit_vals, answers):
                val.set_label(a or "–")
            t = answers[self.conv_target] if self.conv_target < len(answers) else None
            self.conv_result = t
            self.conv_big.set_label(t or "–")
            self.conv_small.set_label(f"{amount} {src} = {t}" if t else "Type an amount")
        run_bg(lambda: qalc_many(exprs), done)

    def conv_copy(self):
        t = getattr(self, "conv_result", None)
        if t:
            copy(t.replace("−", "-"))
            self.conv_small.set_label(f"{I_COPY} copied {t}")

    def update_rates(self):
        self.rates_btn.set_label(f"{I_REFRESH} updating…")

        def done(_r):
            self.rates_btn.set_label(f"{I_REFRESH} rates updated")
            self.conv_update()
        run_bg(lambda: subprocess.run(["qalc", "-e", "1"], capture_output=True, timeout=60), done)

    # ----- date --------------------------------------------------------------------------
    def build_date(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.append(label("BETWEEN TWO DATES", "section", xalign=0))
        row = Gtk.Box(spacing=8, homogeneous=True)
        self.d_from = self.date_field(row, "FROM")
        self.d_to = self.date_field(row, "TO")
        page.append(row)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("display")
        self.diff_big = label("", "big", xalign=0, wrap=True)
        self.diff_small = label("", "small", xalign=0, wrap=True)
        box.append(self.diff_big)
        box.append(self.diff_small)
        page.append(box)

        page.append(label("ADD OR SUBTRACT", "section", xalign=0))
        row = Gtk.Box(spacing=8)
        self.d_base = self.date_field(row, "DATE")
        amt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        amt.add_css_class("field")
        amt.append(label("AMOUNT", "field-label", xalign=0))
        self.d_amount = Gtk.Entry(text="30", width_chars=6)
        self.d_amount.add_css_class("field")
        self.d_amount.connect("changed", lambda *_: self.date_update())
        amt.append(self.d_amount)
        row.append(amt)
        page.append(row)
        units = Gtk.Box(spacing=6, homogeneous=True)
        self.d_unit = "days"
        self.d_sign = 1
        self.unit_btns = {}
        for u in ("days", "weeks", "months", "years"):
            b = button(u, "pill", lambda u=u: self.set_date_unit(u))
            self.unit_btns[u] = b
            units.append(b)
        self.sign_btn = button("+ after", "pill active", self.flip_sign, "After / before")
        units.append(self.sign_btn)
        page.append(units)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("display")
        self.add_big = label("", "big", xalign=0, wrap=True)
        self.add_small = label("", "small", xalign=0, wrap=True)
        box.append(self.add_big)
        box.append(self.add_small)
        page.append(box)
        self.set_date_unit("days")
        return page

    def date_field(self, parent, title):
        f = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        f.add_css_class("field")
        head = Gtk.Box()
        head.append(label(title, "field-label", xalign=0, hexpand=True))
        f.append(head)
        e = Gtk.Entry(text=dt.date.today().isoformat(), placeholder_text="YYYY-MM-DD")
        e.add_css_class("field")
        e.set_tooltip_text("YYYY-MM-DD, or today / tomorrow / yesterday")
        e.connect("changed", lambda *_: self.date_update())
        f.append(e)
        parent.append(f)
        return e

    def set_date_unit(self, u):
        self.d_unit = u
        for k, b in self.unit_btns.items():
            (b.add_css_class if k == u else b.remove_css_class)("active")
        self.date_update()

    def flip_sign(self):
        self.d_sign = -self.d_sign
        self.sign_btn.set_label("+ after" if self.d_sign > 0 else "− before")
        self.date_update()

    def date_update(self):
        if not hasattr(self, "add_big"):
            return
        try:
            a, b = parse_date(self.d_from.get_text()), parse_date(self.d_to.get_text())
            lo, hi = sorted((a, b))
            days = (hi - lo).days
            y, m, d = span(lo, hi)
            parts = [plural(n, w) for n, w in ((y, "year"), (m, "month"), (d, "day")) if n] or ["same day"]
            self.diff_big.set_label(plural(days, "day"))
            weeks, rest = divmod(days, 7)
            workdays = sum(1 for i in range(days) if (lo + dt.timedelta(days=i)).weekday() < 5)
            weeks_text = plural(weeks, "week") + (f" + {plural(rest, 'day')}" if rest else "")
            self.diff_small.set_label(f"{', '.join(parts)}  ·  {weeks_text}  ·  {workdays} weekdays")
        except (ValueError, OverflowError) as ex:
            self.diff_big.set_label("–")
            self.diff_small.set_label(str(ex))
        try:
            base = parse_date(self.d_base.get_text())
            n = int(self.d_amount.get_text().strip() or "0") * self.d_sign
            if self.d_unit == "days":
                r = base + dt.timedelta(days=n)
            elif self.d_unit == "weeks":
                r = base + dt.timedelta(weeks=n)
            elif self.d_unit == "months":
                r = add_months(base, n)
            else:
                r = add_months(base, 12 * n)
            en, fa = describe(r)
            self.add_big.set_label(r.isoformat())
            self.add_small.set_label(f"{en}  ·  {fa}")
        except (ValueError, OverflowError) as ex:
            self.add_big.set_label("–")
            self.add_small.set_label(str(ex) if "YYYY" in str(ex) else "Type a whole number")

    # ----- tabs + keys ---------------------------------------------------------------------
    def set_tab(self, key):
        self.tab = key
        for k, b in self.tab_btns.items():
            (b.add_css_class if k == key else b.remove_css_class)("active")
        self.stack.set_visible_child_name("calc" if key in ("std", "sci") else key)
        self.sci.set_reveal_child(key == "sci")
        self.angle_badge.set_visible(key == "sci")
        self.focus_tab()

    def focus_tab(self):
        target = {"std": self.entry, "sci": self.entry, "prog": self.prog_entry,
                  "conv": self.conv_amount, "date": self.d_from}[self.tab]
        target.grab_focus()

    def on_key(self, _ctl, keyval, _code, state):
        alt = state & Gdk.ModifierType.ALT_MASK
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if keyval == Gdk.KEY_Escape:
            self.win.close()
            return True
        if alt and Gdk.KEY_1 <= keyval <= Gdk.KEY_5:
            self.set_tab(self.TABS[keyval - Gdk.KEY_1][0])
            return True
        # Tab / Shift+Tab (and Ctrl+Tab): next / previous tab
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            keys = [k for k, _ in self.TABS]
            step = -1 if state & Gdk.ModifierType.SHIFT_MASK or keyval == Gdk.KEY_ISO_Left_Tab else 1
            self.set_tab(keys[(keys.index(self.tab) + step) % len(keys)])
            return True
        if ctrl and keyval in (Gdk.KEY_c, Gdk.KEY_C) and self.tab in ("std", "sci") \
                and not self.entry.get_selection_bounds():
            self.copy_answer()
            return True
        return False


if __name__ == "__main__":
    sys.exit(Calculator().run([sys.argv[0]]))
