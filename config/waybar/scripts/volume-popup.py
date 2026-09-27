#!/usr/bin/env python3
"""
Sound popup for Waybar in the Everforest style.

  volume-popup.py [THEME]

- Opens under the mouse, just below the bar; click anywhere outside or press Esc to close.
- Clicking the bar icon again also closes it.
- Stays running after the first use (or `--hidden` at login), so it opens instantly;
  the bar opens it through popup.sh, which only sends a D-Bus message.
- Now playing: one card per player (Spotify, SoundCloud, YouTube, any browser tab
  or music app) with cover art, a seek bar and previous / play-pause / next.
- Speaker and microphone: volume, mute, and which device to use.
- Every app that plays sound gets its own volume and mute.
- Scroll on any slider to change it.
"""
import ctypes
import hashlib
import json
import re
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import unicodedata
import urllib.request

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
if __name__ == "__main__" and not os.environ.get("VOLUME_POPUP_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["VOLUME_POPUP_PRELOADED"] = "1"
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

# imported by Settings (panel.py): no window, the theme in use
THEME = sys.argv[1] if __name__ == "__main__" and len(sys.argv) > 1 else palette.current()
WIDTH = 440
MAX_VOLUME = 100  # same limit as the volume keys
MAX_PLAYERS = 8
CARD_HEIGHT = 230  # every Now Playing card is this tall, whatever it shows
ART_CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "volume-popup")

ALIASES = {}
P = palette.load(THEME, **ALIASES)

# where the music comes from: label (None = the player's own name), icon, colour
BRANDS = {
    "spotify":    ("Spotify",       "",     "#1ed760"),
    "soundcloud": ("SoundCloud",    "",     "#ff7a1a"),
    "ytmusic":    ("YouTube Music", "",     "#ff4e45"),
    "youtube":    ("YouTube",       "",     "#ff4e45"),
    "browser":    (None,            "\U000f059f", "#7fbbb3"),
    "player":     (None,            "\U000f075a", "#d699b6"),
}
BROWSERS = ("firefox", "zen", "chromium", "chrome", "brave", "vivaldi", "librewolf", "edge")

STYLE = """
window.volume-popup { background: transparent; }
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
.title { font-size: 19px; }
.title-sub { color: @grey; font-weight: normal; font-size: 12px; }
.section { color: @grey; font-size: 11px; letter-spacing: 2px; margin: 14px 6px 4px 6px; }
.placeholder { color: @grey; font-weight: normal; padding: 6px 6px; }
.sub { color: @grey; font-weight: normal; font-size: 12px; }
.pct { min-width: 46px; font-size: 13px; }

.card {
  background: @bg1;
  border-radius: 16px;
  border: 1px solid alpha(@fg, 0.04);
  border-bottom: 3px solid @edge;
  margin: 5px 0;
  padding: 10px 12px;
}
.card.muted .pct, .card.muted .name { color: @grey; }

/* ---- now playing ---- */
.media { padding: 14px; }
.art {
  border-radius: 14px;
  background-image: linear-gradient(135deg, @bg3, @bg2);
  box-shadow: 0 6px 16px alpha(black, 0.35);
}
.art-icon { font-size: 34px; color: alpha(@fg, 0.55); }
.badge { font-size: 11px; letter-spacing: 1px; }
.song { font-size: 16px; }
.time { color: @grey; font-weight: normal; font-size: 11px; min-width: 38px; }

button.media-btn {
  background: transparent; color: @fg;
  border: none; box-shadow: none; border-radius: 50%;
  font-size: 20px; padding: 4px 10px; min-height: 0; min-width: 0;
}
button.media-btn:hover { background: alpha(@fg, 0.08); }
button.media-btn.play {
  font-size: 22px; min-width: 46px; min-height: 46px; padding: 0;
  color: @on_accent;
  box-shadow: 0 4px 12px alpha(black, 0.3);
}

/* ---- buttons ---- */
button.mute, button.footer {
  background: @bg2; color: @fg;
  border: none; border-radius: 12px; border-bottom: 3px solid @edge;
  box-shadow: none; padding: 2px 8px; min-height: 0; min-width: 0;
}
button.mute { font-size: 18px; min-width: 36px; min-height: 32px; }
button.mute:hover, button.footer:hover { background: @bg3; }
button.mute.muted { background: @red; color: @on_accent; }
button.footer { margin-top: 12px; padding: 8px 10px; border-radius: 14px; }

/* ---- sliders ---- */
.popup scale { padding: 0 4px; }
.popup scale trough {
  min-height: 8px; border-radius: 8px; border: none;
  background: alpha(@fg, 0.14);
}
.popup scale highlight {
  border-radius: 8px; border: none; margin: 0; min-height: 8px; min-width: 0;
  background-image: linear-gradient(90deg, @aqua, @green);
}
.card.muted scale highlight { background-image: none; background: @grey; }
.popup scale slider {
  min-width: 16px; min-height: 16px; margin: -5px 0;
  border-radius: 50%; border: none;
  background: @fg; box-shadow: 0 1px 4px alpha(black, 0.45);
}
.popup scale slider:hover { background: shade(@fg, 1.1); }
.media scale trough { min-height: 5px; }
.media scale highlight { min-height: 5px; }
.media scale slider { min-width: 12px; min-height: 12px; margin: -4px 0; }

/* ---- player carousel ---- */
.carousel-nav { margin-top: 2px; }
button.nav {
  background: transparent; color: @grey; border: none; box-shadow: none;
  border-radius: 50%; padding: 0 8px; min-height: 0; min-width: 0; font-size: 16px;
}
button.nav:hover { background: alpha(@fg, 0.08); color: @fg; }
.dot { color: alpha(@fg, 0.25); font-size: 9px; margin: 0 3px; }
.dot.on { color: @green; }

.tab-note { color: @grey; font-weight: normal; font-size: 11px; }
.media .card { background: transparent; border: none; margin: 0; padding: 0; }

/* ---- per-app output ---- */
.popup dropdown.stream-out > button { padding: 0 8px; font-size: 12px; min-height: 26px; }

/* ---- device menu ---- */
.popup dropdown > button {
  background: @bg2; color: @fg;
  border: none; border-radius: 12px; border-bottom: 3px solid @edge;
  box-shadow: none; padding: 2px 10px; min-height: 0;
}
.popup dropdown > button:hover { background: @bg3; }
popover > contents {
  background: @bg1; color: @fg; border-radius: 14px;
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif; font-weight: bold;
}
popover listview > row { border-radius: 8px; }
popover listview > row:selected, popover listview > row:hover { background: @bg3; }
""" + "".join(f"""
.media.{key} {{
  background-image: linear-gradient(135deg, alpha({color}, 0.30), alpha({color}, 0.06) 55%, @bg1);
  border-color: alpha({color}, 0.25);
}}
.media.{key} .badge {{ color: {color}; }}
.media.{key} button.play {{ background: {color}; }}
.media.{key} button.play:hover {{ background: shade({color}, 1.1); }}
.media.{key} scale highlight {{ background-image: none; background: {color}; }}
""" for key, (_label, _icon, color) in BRANDS.items())
CSS = "".join(f"@define-color {k} {v};\n" for k, v in P.items()) + STYLE

# icons (JetBrainsMono Nerd Font)
I_SPK_MUTE, I_SPK_LOW, I_SPK_MID, I_SPK_HIGH = "\U000f075f", "\U000f057f", "\U000f0580", "\U000f057e"
I_MIC, I_MIC_OFF = "\U000f036c", "\U000f036d"
I_PREV, I_PLAY, I_PAUSE, I_NEXT = "\U000f04ae", "\U000f040a", "\U000f03e4", "\U000f04ad"
I_MUSIC, I_SETTINGS = "\U000f075a", "\U000f0493"
I_LEFT, I_RIGHT = "\U000f0141", "\U000f0142"


# ---------------------------------------------------------------------------
# PipeWire / PulseAudio helpers (pactl)
# ---------------------------------------------------------------------------
def pactl_json(what):
    # pactl warns on stderr about non-ASCII device names; stdout is still valid JSON
    try:
        r = subprocess.run(["pactl", "-f", "json", "list", what],
                           capture_output=True, text=True, timeout=5)
        return json.loads(r.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []


def pactl_out(*args):
    try:
        return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def pactl(*args):
    try:
        subprocess.Popen(["pactl", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def percent(volume):
    vals = []
    for ch in (volume or {}).values():
        try:
            vals.append(int(str(ch.get("value_percent", "0")).rstrip("%")))
        except ValueError:
            pass
    return max(vals, default=0)


def usable(dev, default):
    """Hide AirPlay speakers on the network and jacks with nothing plugged in."""
    if dev["name"] == default:
        return True
    if dev["name"].startswith("raop_sink.") or dev["name"].endswith(".monitor"):
        return False
    ports = dev.get("ports") or []
    return not ports or any(p.get("availability") != "not available" for p in ports)


def device_label(dev):
    props = dev.get("properties") or {}
    label = props.get("device.profile.description") or props.get("node.nick") or dev.get("description") or ""
    if not label or label == "(null)":
        label = dev.get("description") or dev["name"]
    if label == "(null)":  # AirPlay speaker without a name: raop_sink.<host>.local....
        label = dev["name"].split(".")[1] if dev["name"].count(".") > 1 else dev["name"]
    for suffix in (" Output", " Input"):
        if label.endswith(suffix):
            label = label[: -len(suffix)]
    return label


def app_info(stream):
    props = stream.get("properties") or {}
    name = (props.get("application.name") or props.get("application.process.binary")
            or props.get("node.name") or "App")
    media = props.get("media.name") or ""
    if media.lower() in (name.lower(), "playback", "audio stream", "playstream", "audiostream"):
        media = ""
    return name, media


# ---------------------------------------------------------------------------
# Media players (MPRIS through playerctl)
# ---------------------------------------------------------------------------
FIELDS = ("status", "artist", "title", "album", "mpris:artUrl", "mpris:length", "position", "xesam:url")
SEP = "\x1f"


def to_seconds(us):
    try:
        return max(0.0, int(us) / 1_000_000)
    except ValueError:
        return 0.0


def read_players():
    try:
        names = subprocess.run(["playerctl", "-l"], capture_output=True, text=True, timeout=3).stdout.split()
    except (OSError, subprocess.TimeoutExpired):
        return []
    fmt = SEP.join("{{%s}}" % f for f in FIELDS)
    players = []
    for name in names:
        try:
            r = subprocess.run(["playerctl", "-p", name, "metadata", "--format", fmt],
                               capture_output=True, text=True, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            continue
        parts = r.stdout.rstrip("\n").split(SEP)
        if r.returncode != 0 or len(parts) != len(FIELDS):
            continue
        d = dict(zip(FIELDS, parts))
        if not (d["title"] or d["artist"]) or d["status"] == "Stopped":
            continue
        players.append(dict(
            name=name, status=d["status"], artist=d["artist"], title=d["title"], album=d["album"],
            art=d["mpris:artUrl"], url=d["xesam:url"],
            length=to_seconds(d["mpris:length"]), position=to_seconds(d["position"])))
    players.sort(key=lambda p: (p["status"] != "Playing", p["name"]))
    return players[:MAX_PLAYERS]


def brand(player):
    name = player["name"].lower()
    hay = " ".join((name, player["url"], player["art"])).lower()
    if "spotify" in hay or "scdn.co" in hay:
        key = "spotify"
    elif "soundcloud" in hay or "sndcdn" in hay:
        key = "soundcloud"
    elif "music.youtube" in hay:
        key = "ytmusic"
    elif "youtube" in hay or "ytimg" in hay or "youtu.be" in hay:
        key = "youtube"
    elif name.split(".")[0] in BROWSERS:
        key = "browser"
    else:
        key = "player"
    label, icon, _color = BRANDS[key]
    if label is None:
        label = name.split(".")[0].replace("_", " ").title()
    return key, label, icon


def art_file(url):
    """Local file for the cover art; web images are downloaded once into the cache."""
    if url.startswith("file://"):
        path = urllib.parse.unquote(url[len("file://"):])
        return path if os.path.exists(path) else None
    if not url.startswith(("http://", "https://")):
        return None
    path = os.path.join(ART_CACHE, hashlib.sha1(url.encode()).hexdigest())
    if os.path.exists(path):
        return path
    try:
        os.makedirs(ART_CACHE, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = resp.read(8_000_000)
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
        return path
    except OSError:
        return None


def clock(seconds):
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def playerctl(name, *args):
    try:
        subprocess.Popen(["playerctl", "-p", name, *args],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def read_state():
    default_sink = pactl_out("get-default-sink")
    default_source = pactl_out("get-default-source")
    sinks = [s for s in pactl_json("sinks") if usable(s, default_sink)]
    sources = [s for s in pactl_json("sources") if usable(s, default_source)]
    apps = [a for a in pactl_json("sink-inputs")
            if (a.get("properties") or {}).get("media.role") != "event"]  # skip beeps
    return dict(sinks=sinks, sources=sources, apps=apps,
                default_sink=default_sink, default_source=default_source,
                players=read_players())


def die_with_parent():
    """In a child process: end when the popup ends, even when it is killed (a popup
    restart, a test timeout). A leftover `pactl subscribe` keeps its connection, and
    PipeWire refuses every app once about 64 of them are open."""
    try:
        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM)   # 1 = PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass


def run_bg(work, done):
    def target():
        result = work()
        GLib.idle_add(lambda: (done(result), False)[1])
    threading.Thread(target=target, daemon=True).start()


def speaker_icon(vol, muted):
    if muted or vol == 0:
        return I_SPK_MUTE
    return I_SPK_LOW if vol < 34 else I_SPK_MID if vol < 67 else I_SPK_HIGH


def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def is_rtl(text):
    """Persian / Arabic / Hebrew: the first letter that has a direction decides."""
    for ch in text:
        d = unicodedata.bidirectional(ch)
        if d in ("R", "AL"):
            return True
        if d == "L":
            return False
    return False


class Marquee(Gtk.ScrolledWindow):
    """One line of text that never makes its box wider: if it doesn't fit, it slides
    slowly to show the rest (to the left for English, to the right for Persian),
    waits, and starts again."""

    SPEED = 35      # pixels per second
    PAUSE = 1.8     # seconds at each end

    def __init__(self, css):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.EXTERNAL, vscrollbar_policy=Gtk.PolicyType.NEVER,
                         hexpand=True, propagate_natural_height=True, kinetic_scrolling=False)
        self.text = None
        self.rtl = False
        self.start = None
        self.label = label(css=css, xalign=0)
        self.set_child(self.label)
        self.add_tick_callback(self.on_tick)

    def set_label(self, text):
        if text == self.text:
            return
        self.text = text
        self.rtl = is_rtl(text)
        self.label.set_label(text)
        self.label.set_xalign(1 if self.rtl else 0)
        self.start = None              # start over from the beginning of the text

    def on_tick(self, _widget, clock):
        now = clock.get_frame_time() / 1_000_000
        if self.start is None:
            self.start = now
        adj = self.get_hadjustment()
        span = adj.get_upper() - adj.get_page_size()
        if span <= 1:                  # it fits: nothing to move
            adj.set_value(0)
            return GLib.SOURCE_CONTINUE
        run = span / self.SPEED
        t = (now - self.start) % (self.PAUSE + run + self.PAUSE)
        moved = 0 if t < self.PAUSE else min(span, (t - self.PAUSE) * self.SPEED)
        # English reads from the left, so the text slides left; Persian the other way
        adj.set_value(span - moved if self.rtl else moved)
        return GLib.SOURCE_CONTINUE


class VolumeCard(Gtk.Box):
    """Mute button + name + slider + percent, for a device or an app."""

    def __init__(self, kind, key, mic=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("card")
        self.kind, self.key, self.mic = kind, key, mic
        self.updating = False
        self.touched = 0.0     # last time you moved the slider
        self.muted = False

        top = Gtk.Box(spacing=10)
        self.mute_btn = Gtk.Button(valign=Gtk.Align.CENTER, tooltip_text="Mute")
        self.mute_btn.add_css_class("mute")
        self.mute_btn.connect("clicked", self.on_mute)
        top.append(self.mute_btn)

        self.names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        self.name = label(css="name", xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=1)
        self.sub = label(css="sub", xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=1)
        self.names.append(self.name)
        self.names.append(self.sub)
        top.append(self.names)

        self.extra = Gtk.Box()          # device picker goes here
        top.append(self.extra)
        self.append(top)

        row = Gtk.Box(spacing=6)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, MAX_VOLUME, 1)
        self.scale.set_hexpand(True)
        self.scale.set_draw_value(False)
        self.scale.set_increments(5, 5)
        self.scale.connect("value-changed", self.on_scale)
        self.pct = label(css="pct", xalign=1)
        row.append(self.scale)
        row.append(self.pct)
        self.append(row)

    def set_names(self, name, sub=""):
        self.name.set_label(name)
        self.sub.set_label(sub)
        self.sub.set_visible(bool(sub))

    def update(self, vol, muted):
        self.muted = muted
        (self.add_css_class if muted else self.remove_css_class)("muted")
        (self.mute_btn.add_css_class if muted else self.mute_btn.remove_css_class)("muted")
        if self.mic:
            self.mute_btn.set_label(I_MIC_OFF if muted else I_MIC)
        else:
            self.mute_btn.set_label(speaker_icon(vol, muted))
        # don't fight the mouse while you are dragging
        if time.monotonic() - self.touched > 0.6:
            self.updating = True
            self.scale.set_value(min(vol, MAX_VOLUME))
            self.updating = False
            self.pct.set_label(f"{vol}%")

    def on_scale(self, scale):
        vol = int(round(scale.get_value()))
        self.pct.set_label(f"{vol}%")
        if self.updating:
            return
        self.touched = time.monotonic()
        pactl(f"set-{self.kind}-volume", str(self.key), f"{vol}%")
        if self.muted and vol > 0:
            pactl(f"set-{self.kind}-mute", str(self.key), "0")
        if not self.mic:
            self.mute_btn.set_label(speaker_icon(vol, self.muted))

    def on_mute(self, _btn):
        pactl(f"set-{self.kind}-mute", str(self.key), "toggle")


class DevicePicker(Gtk.DropDown):
    """Choose the default speaker / microphone."""

    def __init__(self, on_pick):
        super().__init__(valign=Gtk.Align.CENTER, hexpand=True, tooltip_text="Choose device")
        self.names = []
        self.updating = False
        self.on_pick = on_pick
        self.connect("notify::selected", self.on_selected)

    def update(self, devices, default):
        names = [d["name"] for d in devices]
        self.updating = True
        if names != self.names:
            self.names = names
            self.set_model(Gtk.StringList.new([device_label(d) for d in devices]))
        if default in names:
            self.set_selected(names.index(default))
        self.updating = False
        self.set_visible(len(names) > 1)
        # the menu already shows the device name
        card = self.get_ancestor(VolumeCard)
        if card:
            card.names.set_visible(len(names) <= 1)
            card.extra.set_hexpand(len(names) > 1)

    def on_selected(self, *_):
        i = self.get_selected()
        if not self.updating and 0 <= i < len(self.names):
            self.on_pick(self.names[i])


class StreamPicker(Gtk.DropDown):
    """Which speaker one app plays on (move-sink-input): e.g. YouTube on the laptop
    speakers and SoundCloud on the headset at the same time."""

    def __init__(self, index):
        super().__init__(valign=Gtk.Align.CENTER, tooltip_text="Play this app on…")
        self.add_css_class("stream-out")
        self.index = index
        self.names = []
        self.updating = False
        # short label on the button, full names in the menu
        button = Gtk.SignalListItemFactory()
        button.connect("setup", lambda _f, item: item.set_child(
            Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=12)))
        button.connect("bind", lambda _f, item: item.get_child().set_label(item.get_item().get_string()))
        menu = Gtk.SignalListItemFactory()
        menu.connect("setup", lambda _f, item: item.set_child(Gtk.Label(xalign=0)))
        menu.connect("bind", lambda _f, item: item.get_child().set_label(item.get_item().get_string()))
        self.set_factory(button)
        self.set_list_factory(menu)
        self.connect("notify::selected", self.on_selected)

    def update(self, sinks, current):
        names = [s.get("index") for s in sinks]
        self.updating = True
        if names != self.names:
            self.names = names
            self.set_model(Gtk.StringList.new([device_label(s) for s in sinks]))
        if current in names:
            self.set_selected(names.index(current))
        self.updating = False
        self.set_visible(len(names) > 1)

    def on_selected(self, *_):
        i = self.get_selected()
        if not self.updating and 0 <= i < len(self.names):
            pactl("move-sink-input", str(self.index), str(self.names[i]))


class MediaCarousel(Gtk.Box):
    """Player cards side by side: one at a time, swipe the touchpad sideways (or
    Shift+wheel, or the arrows / dots) to see the next."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        # one fixed size for every card, so switching never resizes the popup
        self.stack = Gtk.Stack(transition_duration=220, vhomogeneous=True, hhomogeneous=True)
        self.stack.set_size_request(-1, CARD_HEIGHT)
        self.append(self.stack)
        self.order = []
        self.cards = {}

        self.nav = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER)
        self.nav.add_css_class("carousel-nav")
        prev_btn = Gtk.Button(label=I_LEFT, tooltip_text="Previous player")
        next_btn = Gtk.Button(label=I_RIGHT, tooltip_text="Next player")
        for b, step in ((prev_btn, -1), (next_btn, 1)):
            b.add_css_class("nav")
            b.connect("clicked", lambda _b, s=step: self.go(s))
        self.dots = Gtk.Box()
        self.nav.append(prev_btn)
        self.nav.append(self.dots)
        self.nav.append(next_btn)
        self.append(self.nav)

        # sideways on the touchpad, or the normal mouse wheel
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
        # before the scrolling titles inside the cards can take the wheel
        scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        scroll.connect("scroll", self.on_scroll)
        scroll.connect("scroll-end", lambda *_: self.reset_swipe())
        self.add_controller(scroll)
        self.swipe = 0.0
        self.swiped = False
        # or grab a card and drag it sideways (sliders and buttons keep their own clicks)
        drag = Gtk.GestureDrag()
        drag.connect("drag-end", self.on_drag_end)
        self.stack.add_controller(drag)

    def on_drag_end(self, _g, dx, dy):
        if abs(dx) > 60 and abs(dx) > abs(dy) * 1.5:
            self.go(-1 if dx > 0 else 1)

    def current(self):
        return self.stack.get_visible_child_name()

    def set_cards(self, names, cards, restart=False):
        """names: best first. While it is open the order stays put; new players join
        at the end. restart (on open): show the best one."""
        for name in list(self.cards):
            if name not in names:
                self.stack.remove(self.cards.pop(name))
        for name in names:
            if name not in self.cards:
                self.cards[name] = cards[name]
                self.stack.add_named(cards[name], name)
        if restart:
            self.order = list(names)
        else:
            self.order = [n for n in self.order if n in names] + [n for n in names if n not in self.order]
        if self.order and (restart or self.current() not in self.order):
            self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
            self.stack.set_visible_child_name(self.order[0])
        self.draw_dots()

    def go(self, step):
        if len(self.order) < 2:
            return
        i = self.order.index(self.current()) if self.current() in self.order else 0
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT if step > 0
                                       else Gtk.StackTransitionType.SLIDE_RIGHT)
        self.stack.set_visible_child_name(self.order[(i + step) % len(self.order)])
        self.draw_dots()

    def draw_dots(self):
        while (c := self.dots.get_first_child()) is not None:
            self.dots.remove(c)
        for name in self.order:
            dot = label("\u25cf", "dot" + (" on" if name == self.current() else ""), valign=Gtk.Align.CENTER)
            click = Gtk.GestureClick()
            click.connect("pressed", lambda *_a, n=name: self.jump(n))
            dot.add_controller(click)
            self.dots.append(dot)
        self.nav.set_visible(len(self.order) > 1)

    def jump(self, name):
        if name in self.order and self.current() in self.order:
            step = self.order.index(name) - self.order.index(self.current())
            if step:
                self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT if step > 0
                                               else Gtk.StackTransitionType.SLIDE_RIGHT)
                self.stack.set_visible_child_name(name)
                self.draw_dots()

    def on_scroll(self, ctl, dx, dy):
        if len(self.order) < 2:
            return False
        if self.swiped:
            return True
        # the wheel moves in clicks, the touchpad in pixels
        discrete = ctl.get_unit() == Gdk.ScrollUnit.WHEEL
        if discrete or abs(dy) > abs(dx):
            dx = dx or dy          # wheel down / touchpad down = next
        self.swipe += dx * (40 if discrete else 1)
        if abs(self.swipe) >= 40:
            self.go(1 if self.swipe > 0 else -1)
            self.swiped = True
            # a wheel has no "scroll end": allow the next click after a moment
            GLib.timeout_add(350 if discrete else 900, lambda: (self.reset_swipe(), False)[1])
        return True

    def reset_swipe(self):
        self.swipe = 0.0
        self.swiped = False


def browser_tabs(apps, players):
    """Browser audio streams that have no player of their own. Zen and Firefox tell
    the system about only one tab (the last one that played), so the others would
    be invisible; they still get a card, with volume, mute and speaker."""
    tabs, streams = [], 0
    for a in apps:
        props = a.get("properties") or {}
        who = " ".join(str(props.get(k, "")) for k in
                       ("application.name", "application.process.binary", "application.id")).lower()
        if not any(b in who for b in BROWSERS):
            continue
        streams += 1
        media = (props.get("media.name") or "").strip()
        if media.lower() in ("", "(null)", "null", "audiostream", "audio stream", "playback", "playstream"):
            continue           # nameless: nothing to show (it is still listed under APPS)
        tabs.append(a)
    # no more browser streams than browser players: the player cards cover them all
    if streams <= sum(1 for p in players if p["name"].split(".")[0] in BROWSERS):
        return []
    # drop the tab each player card already shows: same title, or else same site
    # (SoundCloud renames its tab to the site slogan while it plays)
    for p in players:
        title = p["title"].lower()
        site = brand(p)[0]
        match = next((a for a in tabs if title and (title in tab_title(a) or tab_title(a) in title)), None)
        if match is None and site not in ("browser", "player"):
            match = next((a for a in tabs if brand(tab_info(a))[0] == site), None)
        if match is not None:
            tabs.remove(match)
    return tabs


def tab_title(a):
    return ((a.get("properties") or {}).get("media.name") or "").strip().lower()


def tab_info(a):
    """A stream described like a player, for brand()."""
    props = a.get("properties") or {}
    return dict(name=(props.get("application.name") or "browser").lower(),
                url=props.get("media.name") or "", art="")


class TabCard(Gtk.Box):
    """A browser tab that plays sound but has no player controls."""

    def __init__(self, index):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("card")
        self.add_css_class("media")
        self.index = index
        self.brand_key = None

        top = Gtk.Box(spacing=14)
        art = Gtk.Overlay()
        art.add_css_class("art")
        art.set_size_request(MediaCard.ART, MediaCard.ART)
        art.set_valign(Gtk.Align.CENTER)
        self.art_icon = label(I_MUSIC, "art-icon")
        art.set_child(self.art_icon)
        top.append(art)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True, valign=Gtk.Align.CENTER)
        self.badge = label(css="badge", xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=1)
        self.song = Marquee("song")
        self.state = label(css="sub", xalign=0)
        self.note = label("Play / pause it in the browser tab", "tab-note", xalign=0,
                          ellipsize=Pango.EllipsizeMode.END, max_width_chars=1)
        for w in (self.badge, self.song, self.state, self.note):
            text.append(w)
        top.append(text)
        self.append(top)

        self.volume = VolumeCard("sink-input", index)
        self.volume.names.set_visible(False)
        self.volume.extra.set_hexpand(True)
        self.volume.extra.set_halign(Gtk.Align.END)
        self.picker = StreamPicker(index)
        self.volume.extra.append(self.picker)
        self.append(self.volume)

    def update(self, a, sinks):
        props = a.get("properties") or {}
        media = props.get("media.name") or ""
        app = props.get("application.name") or "Browser"
        key, brand_label, icon = brand(tab_info(a))
        if key != self.brand_key:
            if self.brand_key:
                self.remove_css_class(self.brand_key)
            self.add_css_class(key)
            self.brand_key = key
        self.art_icon.set_label(icon)
        self.badge.set_label(f"{icon}  {brand_label.upper()}  ·  {app.upper()} TAB")
        title = re.sub(r"\s+[-–|]\s+(YouTube|YouTube Music|SoundCloud)$", "", media)
        self.song.set_label(title)
        self.song.set_tooltip_text(media)
        self.state.set_label("Paused" if a.get("corked") else "Playing")
        self.volume.update(percent(a.get("volume")), bool(a.get("mute")))
        self.picker.update(sinks, a.get("sink"))


class MediaCard(Gtk.Box):
    """Cover art, title, artist, seek bar and controls for one player."""

    ART = 88

    def __init__(self, name):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("card")
        self.add_css_class("media")
        self.name = name
        self.brand_key = None
        self.art_url = None
        self.status = ""
        self.position = 0.0
        self.length = 0.0
        self.touched = 0.0
        self.updating = False

        top = Gtk.Box(spacing=14)
        art = Gtk.Overlay()
        art.add_css_class("art")
        art.set_size_request(self.ART, self.ART)
        art.set_overflow(Gtk.Overflow.HIDDEN)
        art.set_valign(Gtk.Align.CENTER)
        art.set_child(label(I_MUSIC, "art-icon"))
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        self.picture.set_size_request(self.ART, self.ART)
        art.add_overlay(self.picture)
        top.append(art)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True,
                       valign=Gtk.Align.CENTER)
        self.badge = label(css="badge", xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=1)
        self.song = Marquee("song")
        self.artist = Marquee("sub")
        for w in (self.badge, self.song, self.artist):
            text.append(w)
        top.append(text)
        self.append(top)

        self.seek_row = Gtk.Box(spacing=8)
        self.t_now = label(css="time", xalign=0)
        self.t_end = label(css="time", xalign=1)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self.scale.set_hexpand(True)
        self.scale.set_draw_value(False)
        self.scale.connect("change-value", self.on_seek)
        for w in (self.t_now, self.scale, self.t_end):
            self.seek_row.append(w)
        self.append(self.seek_row)

        buttons = Gtk.Box(spacing=18, halign=Gtk.Align.CENTER)
        for icon, cmd in ((I_PREV, "previous"), (I_PLAY, "play-pause"), (I_NEXT, "next")):
            btn = Gtk.Button(label=icon, valign=Gtk.Align.CENTER)
            btn.add_css_class("media-btn")
            btn.connect("clicked", lambda _b, c=cmd: self.command(c))
            if cmd == "play-pause":
                btn.add_css_class("play")
                self.play_btn = btn
            buttons.append(btn)
        self.append(buttons)

    def update(self, p):
        key, brand_label, icon = brand(p)
        if key != self.brand_key:
            if self.brand_key:
                self.remove_css_class(self.brand_key)
            self.add_css_class(key)
            self.brand_key = key
        self.badge.set_label(f"{icon}  {brand_label.upper()}")
        self.song.set_label(p["title"] or brand_label)
        self.song.set_tooltip_text(p["title"])
        who = " — ".join(x for x in (p["artist"], p["album"]) if x)
        self.artist.set_label(who)     # stays in place even when empty: the card keeps its layout
        self.status = p["status"]
        self.play_btn.set_label(I_PAUSE if self.status == "Playing" else I_PLAY)
        self.length = p["length"]
        if time.monotonic() - self.touched > 1.5:
            self.position = p["position"]
        self.show_position()
        if p["art"] != self.art_url:
            self.art_url = p["art"]
            self.picture.set_paintable(None)
            url = p["art"]
            run_bg(lambda: art_file(url), lambda path: self.set_art(url, path))

    def set_art(self, url, path):
        if url != self.art_url or not path:
            return
        try:
            self.picture.set_paintable(Gdk.Texture.new_from_filename(path))
        except GLib.Error:
            pass

    def show_position(self):
        has_length = self.length > 0
        self.seek_row.set_visible(has_length)
        if not has_length:
            return
        self.updating = True
        self.scale.set_range(0, self.length)
        if time.monotonic() - self.touched > 1.5:
            self.scale.set_value(min(self.position, self.length))
        self.updating = False
        self.t_now.set_label(clock(min(self.position, self.length)))
        self.t_end.set_label(clock(self.length))

    def tick(self):
        if self.status == "Playing" and self.length > 0:
            self.position = min(self.position + 1, self.length)
            self.show_position()

    def on_seek(self, _scale, _scroll, value):
        value = max(0.0, min(value, self.length))
        self.touched = time.monotonic()
        self.position = value
        self.t_now.set_label(clock(value))
        playerctl(self.name, "position", f"{value:.1f}")
        return False

    def command(self, cmd):
        playerctl(self.name, cmd)
        if cmd == "play-pause":   # answer the click right away
            self.status = "Paused" if self.status == "Playing" else "Playing"
            self.play_btn.set_label(I_PAUSE if self.status == "Playing" else I_PLAY)


class VolumePanel:
    """Now playing, speaker, microphone and every app's volume. Shown by the popup
    below and by Settings (see panel.py for the host), which leaves out Now playing."""

    def __init__(self, host):
        self.host = host
        self.app_cards = {}
        self.media_cards = {}
        self.subscriber = None
        self.refresh_pending = False
        self.restart_players = False
        self.build()
        self.watch_changes()
        GLib.timeout_add_seconds(2, self._tick)
        GLib.timeout_add_seconds(1, self._tick_media)

    def on_show(self):
        self.restart_players = True
        self.refresh()

    def on_hide(self):
        pass

    def stop(self):
        if self.subscriber:
            self.subscriber.kill()

    def build(self):
        popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.add_css_class("popup")
        popup.set_size_request(WIDTH, -1)

        header = Gtk.Box(spacing=10)
        header.append(label(f"{I_SPK_HIGH}  Sound", "title", xalign=0, hexpand=True))
        self.header_sub = label(css="title-sub", xalign=1)
        header.append(self.header_sub)
        popup.append(header)

        # now playing
        self.media_title = self.section("NOW PLAYING")
        popup.append(self.media_title)
        self.media_box = MediaCarousel()
        popup.append(self.media_box)
        if self.host.embedded:  # music isn't a setting
            self.media_title.set_visible(False)
            self.media_box.set_visible(False)

        # speaker
        popup.append(self.section("OUTPUT"))
        self.out_card = VolumeCard("sink", "@DEFAULT_SINK@")
        self.out_pick = DevicePicker(lambda name: pactl("set-default-sink", name))
        self.out_card.extra.append(self.out_pick)
        popup.append(self.out_card)

        # microphone
        popup.append(self.section("MICROPHONE"))
        self.in_card = VolumeCard("source", "@DEFAULT_SOURCE@", mic=True)
        self.in_pick = DevicePicker(lambda name: pactl("set-default-source", name))
        self.in_card.extra.append(self.in_pick)
        popup.append(self.in_card)

        # apps
        popup.append(self.section("APPS"))
        self.apps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.no_apps = label("No app is playing sound", "placeholder", xalign=0)
        self.apps_box.append(self.no_apps)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                    propagate_natural_height=True, max_content_height=300)
        scroll.set_child(self.apps_box)
        popup.append(scroll)

        if not self.host.embedded:  # Settings opens no other app
            settings = Gtk.Button(label=f"{I_SETTINGS}   Sound settings")
            settings.add_css_class("footer")
            settings.connect("clicked", self.open_settings)
            popup.append(settings)
        self.root = popup


    @staticmethod
    def section(text):
        return label(text, "section", xalign=0)

    # ----- state -------------------------------------------------------------
    def watch_changes(self):
        """Follow `pactl subscribe` so the popup updates live (keys, other apps, plugging)."""
        try:
            self.subscriber = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE,
                                               stderr=subprocess.DEVNULL, text=True,
                                               preexec_fn=die_with_parent)
        except OSError:
            return
        out = self.subscriber.stdout

        def reader():
            for line in out:
                if any(w in line for w in ("sink", "source", "server")):
                    GLib.idle_add(self.queue_refresh)
        threading.Thread(target=reader, daemon=True).start()

    def queue_refresh(self):
        # many events arrive at once; refresh once (and only while it is open)
        if not self.host.is_shown():
            return False
        if not self.refresh_pending:
            self.refresh_pending = True
            GLib.timeout_add(80, lambda: (self.refresh(), False)[1])
        return False

    def _tick(self):
        if self.host.is_shown():
            self.refresh()   # catches track changes of the media players
        return True

    def _tick_media(self):
        if not self.host.is_shown():
            return True
        for card in self.media_cards.values():
            if isinstance(card, MediaCard):
                card.tick()
        return True

    def refresh(self):
        self.refresh_pending = False
        run_bg(read_state, self.apply)

    def apply(self, st):
        sink = next((s for s in st["sinks"] if s["name"] == st["default_sink"]), None)
        if sink:
            vol, muted = percent(sink.get("volume")), bool(sink.get("mute"))
            self.out_card.set_names(device_label(sink))
            self.out_card.update(vol, muted)
            self.header_sub.set_label("muted" if muted else f"{vol}%")
        else:
            self.out_card.set_names("No output device")
            self.header_sub.set_label("")
        self.out_pick.update(st["sinks"], st["default_sink"])

        src = next((s for s in st["sources"] if s["name"] == st["default_source"]), None)
        if src:
            self.in_card.set_names(device_label(src))
            self.in_card.update(percent(src.get("volume")), bool(src.get("mute")))
        else:
            self.in_card.set_names("No microphone")
        self.in_pick.update(st["sources"], st["default_source"])

        self.apply_apps(st["apps"], st["sinks"])
        if not self.host.embedded:
            self.apply_players(st["players"], browser_tabs(st["apps"], st["players"]), st["sinks"])

    def apply_apps(self, apps, sinks):
        sink_names = {s.get("index"): device_label(s) for s in sinks}
        seen = set()
        for a in apps:
            idx = a.get("index")
            seen.add(idx)
            card = self.app_cards.get(idx)
            if card is None:
                card = VolumeCard("sink-input", idx)
                card.picker = StreamPicker(idx)
                card.extra.append(card.picker)
                self.app_cards[idx] = card
                self.apps_box.append(card)
            name, media = app_info(a)
            card.picker.update(sinks, a.get("sink"))
            # the menu shows the speaker; without a menu say where it plays
            where = sink_names.get(a.get("sink"), "") if not card.picker.get_visible() else ""
            sub = " · ".join(x for x in (media, where if len(sinks) > 1 else "") if x)
            card.set_names(name, sub)
            card.update(percent(a.get("volume")), bool(a.get("mute")))
        for idx in list(self.app_cards):
            if idx not in seen:
                self.apps_box.remove(self.app_cards.pop(idx))
        self.no_apps.set_visible(not self.app_cards)

    def apply_players(self, players, tabs=(), sinks=()):
        seen = []
        for p in players:
            seen.append(p["name"])
            card = self.media_cards.get(p["name"])
            if card is None:
                card = MediaCard(p["name"])
                self.media_cards[p["name"]] = card
            card.update(p)
        # browser tabs without a player: after the real players, playing ones first
        for a in sorted(tabs, key=lambda a: bool(a.get("corked"))):
            key = f"tab:{a.get('index')}"
            seen.append(key)
            card = self.media_cards.get(key)
            if card is None:
                card = TabCard(a.get("index"))
                self.media_cards[key] = card
            card.update(a, sinks)
        for name in list(self.media_cards):
            if name not in seen:
                self.media_cards.pop(name)
        # the playing one first; swipe sideways for the others
        self.media_box.set_cards(seen, self.media_cards, restart=self.restart_players)
        self.restart_players = False
        self.media_title.set_label(f"NOW PLAYING  ·  {len(seen)}" if len(seen) > 1 else "NOW PLAYING")
        self.media_title.set_visible(bool(seen))
        self.media_box.set_visible(bool(seen))

    # ----- events ------------------------------------------------------------
    def open_settings(self, *_):
        try:
            subprocess.Popen(["pavucontrol"], start_new_session=True)
        except OSError:
            return
        self.host.close()


class VolumePopup(Gtk.Application):
    """The popup: the panel in a layer-shell window, right under the mouse."""

    embedded = False

    def __init__(self):
        super().__init__(application_id="io.local.volumepopup")
        self.win = None
        self.panel = None
        self.start_hidden = "--hidden" in sys.argv

    # ----- host (see panel.py) ---------------------------------------------------
    def close(self):
        self.win.close()

    def is_shown(self):
        return self.win is not None and self.win.get_visible()

    # every later launch (clicking the bar icon) opens or closes the same window
    def do_activate(self):
        if self.win is None:
            self.hold()   # keep running while hidden, so the next open is instant
            self.build()
            if self.start_hidden:
                self.panel.refresh()
                return
        if self.win.get_visible():
            self.win.close()
        elif GLib.get_monotonic_time() - getattr(self, 'closed_at', 0) > 400_000:
            # the click that just closed it (outside the popup, on the bar icon)
            # also reaches the bar, which asks to open it again: ignore that one
            self.show_popup()

    def show_popup(self):
        self.place()
        self.win.present()
        self.panel.on_show()

    def on_close(self, win):
        self.closed_at = GLib.get_monotonic_time()
        win.set_visible(False)   # hide, don't destroy
        return True

    def do_shutdown(self):
        if self.panel:
            self.panel.stop()
        Gtk.Application.do_shutdown(self)

    @staticmethod
    def cursor_offset():
        """Cursor x inside the focused screen, so the popup opens right under the icon."""
        try:
            pos = json.loads(subprocess.run(["hyprctl", "-j", "cursorpos"],
                                            capture_output=True, text=True, timeout=2).stdout)
            mons = json.loads(subprocess.run(["hyprctl", "-j", "monitors"],
                                             capture_output=True, text=True, timeout=2).stdout)
            mon = next(m for m in mons if m.get("focused"))
            width = mon["width"] / mon["scale"]
            if mon.get("transform", 0) % 2:
                width = mon["height"] / mon["scale"]
            return (pos["x"] - mon["x"]) / (width or 1), width
        except (OSError, ValueError, KeyError, StopIteration, subprocess.TimeoutExpired):
            return None

    def build(self):
        prov = Gtk.CssProvider()
        if hasattr(prov, "load_from_string"):          # GTK >= 4.12
            prov.load_from_string(CSS)
        else:
            prov.load_from_data(CSS, -1)
        add = getattr(Gtk, "style_context_add_provider_for_display", None) \
            or Gtk.StyleContext.add_provider_for_display
        add(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)

        win = Gtk.ApplicationWindow(application=self, title="Sound")
        win.add_css_class("volume-popup")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win
        self.panel = VolumePanel(self)
        popup = self.popup = self.panel.root

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)

        if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
            # full-screen transparent layer: clicking outside the popup closes it
            LS.init_for_window(win)
            LS.set_namespace(win, "volume-popup")
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
            # fallback: normal window that closes when it loses focus
            win.set_child(popup)
            win.connect("notify::is-active", lambda w, _p: None if w.is_active() else w.close())
            self.layered = False

    def place(self):
        """Put the popup right under the mouse, on whichever screen it is."""
        if not self.layered:
            return
        popup, full = self.popup, WIDTH + 36  # popup plus its shadow margin
        cursor = self.cursor_offset()
        if cursor:
            frac, screen_w = cursor
            popup.set_halign(Gtk.Align.START)
            popup.set_margin_end(0)
            popup.set_margin_start(max(0, min(int(frac * screen_w - full / 2), int(screen_w) - full)))
        else:
            popup.set_halign(Gtk.Align.END)
            popup.set_margin_end(240)

    def on_key(self, _ctl, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self.win.close()
            return True
        return False


if __name__ == "__main__":
    sys.exit(VolumePopup().run([sys.argv[0]]))
