#!/usr/bin/env python3
"""
Wi-Fi popup for Waybar in the Everforest "raised box" style.

  wifi-menu.py [THEME]

- Opens under the bar at the top right; click anywhere outside or press Esc to close.
- Clicking the bar icon again also closes it.
- Stays running hidden after the first use (or `--hidden` at login), so it opens instantly.
- On/off switch, rescan, connect, inline password, disconnect, forget.
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
if __name__ == "__main__" and not os.environ.get("WIFI_MENU_PRELOADED"):
    lib = next((p for p in LAYER_LIBS if os.path.exists(p)), None)
    os.environ["WIFI_MENU_PRELOADED"] = "1"
    if lib:
        old = os.environ.get("LD_PRELOAD", "")
        os.environ["LD_PRELOAD"] = lib + (":" + old if old else "")
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LS  # noqa: E402
except (ValueError, ImportError):
    LS = None

import fonts  # noqa: E402
import palette  # noqa: E402

import popup_backdrop  # noqa: E402

# imported by Settings (panel.py): no window, the theme in use
THEME = sys.argv[1] if __name__ == "__main__" and len(sys.argv) > 1 else palette.current()

ALIASES = dict(edge="edge_deep")
P = palette.load(THEME, **ALIASES)

STYLE = """
window.wifi-menu { background: transparent; }
.backdrop { background: transparent; }

.popup {
  background: @bg0;
  color: @fg;
  border-radius: 14px;
  border-bottom: 6px solid @edge;
  padding: 14px;
  font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif;
  font-weight: bold;
  font-size: 14px;
}
.title { font-size: 18px; }
.status { color: @grey; font-weight: normal; margin: 6px 4px 4px 4px; }
.status.error { color: @red; }

list.nets { background: transparent; }
list.nets > row {
  background: @bg1;
  color: @fg;
  border-radius: 10px;
  border-bottom: 4px solid @edge;
  margin: 5px 0;
  padding: 8px 12px;
  outline: none;
}
list.nets > row:hover { background: @bg2; }
list.nets > row.connected { background: @bg2; box-shadow: inset 4px 0 0 @green; }
.bars { font-size: 18px; min-width: 28px; }
.lock { color: @grey; }
.check { color: @green; }
.placeholder { color: @grey; font-weight: normal; padding: 24px 8px; }

button.pill {
  background: @green; color: @bg0;
  border: none; border-radius: 8px; border-bottom: 3px solid @green_edge;
  box-shadow: none; padding: 4px 14px; min-height: 0;
}
button.pill:hover { background: shade(@green, 1.08); }
button.pill.danger { background: @red; border-bottom-color: @red_edge; }
button.pill.ghost  { background: @bg3; color: @fg; border-bottom-color: @edge; }

button.icon-btn, button.footer {
  background: @bg1; color: @fg;
  border: none; border-radius: 8px; border-bottom: 3px solid @edge;
  box-shadow: none; padding: 2px 10px; min-height: 0;
}
button.icon-btn:hover, button.footer:hover { background: @bg2; }
button.footer { margin-top: 10px; padding: 6px 10px; }

.popup entry, .popup passwordentry, .popup password {
  background: @bg0; color: @fg;
  border: none; border-radius: 8px; border-bottom: 3px solid @edge;
  box-shadow: none; outline: none; padding: 2px 8px; min-height: 28px;
}
.popup passwordentry.error { border-bottom-color: @red; }

.popup switch { background: @bg3; border: none; border-radius: 14px; box-shadow: none; }
.popup switch:checked { background: @green; }
.popup switch slider { background: @fg; border: none; border-radius: 12px; box-shadow: none; }
.popup spinner { color: @green; }
"""
CSS = fonts.swap("".join(f"@define-color {k} {v};\n" for k, v in P.items()) + STYLE)


# ---------------------------------------------------------------------------
# NetworkManager helpers (nmcli)
# ---------------------------------------------------------------------------
def nm(*args, timeout=45):
    try:
        r = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 1, "", "Timed out"
    msg = (r.stderr or r.stdout).strip()
    msg = re.sub(r"^Error:\s*", "", msg.splitlines()[-1] if msg else "")
    return r.returncode, r.stdout, msg


def split_terse(line):
    """nmcli -t escapes ':' as '\\:' inside values."""
    return [p.replace("\\:", ":").replace("\\\\", "\\") for p in re.split(r"(?<!\\):", line)]


def read_state(rescan=False):
    _, out, _ = nm("-t", "-f", "WIFI", "general")
    enabled = out.strip() == "enabled"
    nets = []
    if enabled:
        _, out, _ = nm("-t", "-f", "IN-USE,SIGNAL,SECURITY,SSID", "device", "wifi", "list",
                       "--rescan", "yes" if rescan else "auto")
        seen = {}
        for line in out.splitlines():
            f = split_terse(line)
            if len(f) < 4:
                continue
            inuse, sig, sec, ssid = f[0], f[1], f[2], ":".join(f[3:])
            if not ssid:
                continue
            try:
                sig = int(sig)
            except ValueError:
                sig = 0
            n = seen.get(ssid)
            if n:
                n["active"] = n["active"] or inuse == "*"
                n["signal"] = max(n["signal"], sig)
                continue
            seen[ssid] = dict(ssid=ssid, signal=sig, secure=sec not in ("", "--"), active=inuse == "*")
        nets = sorted(seen.values(), key=lambda n: (not n["active"], -n["signal"]))
    _, out, _ = nm("-t", "-f", "NAME,TYPE", "connection", "show")
    saved = set()
    for line in out.splitlines():
        f = split_terse(line)
        if len(f) >= 2 and f[-1] == "802-11-wireless":
            saved.add(":".join(f[:-1]))
    return enabled, nets, saved


def bars(signal):
    if signal >= 80:
        return "\U000f0928"
    if signal >= 60:
        return "\U000f0925"
    if signal >= 40:
        return "\U000f0922"
    if signal >= 20:
        return "\U000f091f"
    return "\U000f092f"


def notify(title, body=""):
    try:
        subprocess.Popen(["notify-send", "-a", "Wi-Fi", "-i", "network-wireless", title, body])
    except OSError:
        pass


def run_bg(work, done):
    def target():
        result = work()
        GLib.idle_add(lambda: (done(result), False)[1])
    threading.Thread(target=target, daemon=True).start()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
class NetRow(Gtk.ListBoxRow):
    def __init__(self, menu, net, saved):
        super().__init__()
        self.menu, self.net, self.saved = menu, net, saved
        self.set_activatable(True)
        if net["active"]:
            self.add_css_class("connected")

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        top = Gtk.Box(spacing=10)
        top.append(self._label(bars(net["signal"]), "bars"))
        name = self._label(net["ssid"])
        name.set_hexpand(True)
        name.set_xalign(0)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        top.append(name)
        if net["secure"]:
            top.append(self._label("\U000f033e", "lock"))
        if net["active"]:
            top.append(self._label("\U000f012c", "check"))
        outer.append(top)

        self.revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                                     transition_duration=150)
        outer.append(self.revealer)
        self.set_child(outer)
        self.entry = None

    @staticmethod
    def _label(text, css=None):
        lbl = Gtk.Label(label=text)
        if css:
            lbl.add_css_class(css)
        return lbl

    def collapse(self):
        self.revealer.set_reveal_child(False)

    def show_password(self, error=False):
        box = Gtk.Box(spacing=8, margin_top=10)
        self.entry = Gtk.PasswordEntry(show_peek_icon=True, hexpand=True)
        self.entry.set_property("placeholder-text", "Password")
        if error:
            self.entry.add_css_class("error")
        self.entry.connect("activate", lambda *_: self._submit())
        btn = Gtk.Button(label="Connect")
        btn.add_css_class("pill")
        btn.connect("clicked", lambda *_: self._submit())
        box.append(self.entry)
        box.append(btn)
        self.revealer.set_child(box)
        self.revealer.set_reveal_child(True)
        GLib.idle_add(lambda: (self.entry.grab_focus(), False)[1])

    def show_actions(self):
        box = Gtk.Box(spacing=8, margin_top=10, halign=Gtk.Align.END)
        dis = Gtk.Button(label="Disconnect")
        dis.add_css_class("pill")
        dis.add_css_class("ghost")
        dis.connect("clicked", lambda *_: self.menu.disconnect(self.net))
        forget = Gtk.Button(label="Forget")
        forget.add_css_class("pill")
        forget.add_css_class("danger")
        forget.connect("clicked", lambda *_: self.menu.forget(self.net))
        box.append(dis)
        box.append(forget)
        self.revealer.set_child(box)
        self.revealer.set_reveal_child(True)

    def _submit(self):
        pw = self.entry.get_text() if self.entry else ""
        if pw:
            self.menu.connect_net(self.net, pw)


class WifiPanel:
    """The switch, the networks, passwords, disconnect and forget. Shown by the popup
    below and by Settings (see panel.py for the host)."""

    def __init__(self, host):
        self.host = host
        self.busy = False
        self.open_row = None
        self.updating_switch = False
        self.saved = set()
        self.build()
        GLib.timeout_add_seconds(5, self._tick)

    def on_show(self):
        self.set_status("")
        self.open_row = None
        self.refresh()

    def on_hide(self):
        if self.open_row is not None:
            self.open_row.collapse()
            self.open_row = None

    def build(self):
        popup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.add_css_class("popup")
        popup.set_size_request(400, -1)

        header = Gtk.Box(spacing=10)
        title = Gtk.Label(label="\U000f05a9  Wi-Fi", xalign=0, hexpand=True)
        title.add_css_class("title")
        self.spinner = Gtk.Spinner()
        rescan = Gtk.Button(label="\U000f0450")
        rescan.add_css_class("icon-btn")
        rescan.set_tooltip_text("Rescan")
        rescan.connect("clicked", lambda *_: self.refresh(rescan=True))
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.connect("state-set", self.on_switch)
        for w in (title, self.spinner, rescan, self.switch):
            header.append(w)
        popup.append(header)

        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class("status")
        popup.append(self.status)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("nets")
        self.listbox.connect("row-activated", self.on_row)
        self.placeholder = Gtk.Label(label="Looking for networks…")
        self.placeholder.add_css_class("placeholder")
        self.listbox.set_placeholder(self.placeholder)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                    propagate_natural_height=True, max_content_height=380)
        scroll.set_child(self.listbox)
        popup.append(scroll)

        if not self.host.embedded:  # Settings opens no other app
            settings = Gtk.Button(label="\U000f0493   Network settings")
            settings.add_css_class("footer")
            settings.connect("clicked", self.open_settings)
            popup.append(settings)
        self.root = popup


    # ----- state -------------------------------------------------------------
    def set_status(self, text="", error=False):
        self.status.set_label(text)
        self.status.set_visible(bool(text))
        (self.status.add_css_class if error else self.status.remove_css_class)("error")

    def set_busy(self, busy):
        self.busy = busy
        self.spinner.set_spinning(busy)

    def _tick(self):
        if not self.host.is_shown():
            return True
        if not self.busy and self.open_row is None:
            self.refresh(quiet=True)
        return True

    def refresh(self, rescan=False, quiet=False, then=None):
        if not quiet:
            self.set_busy(True)
            if rescan:
                self.set_status("Scanning…")

        def done(state):
            enabled, nets, saved = state
            self.saved = saved
            if not quiet:
                self.set_busy(False)
                if rescan:
                    self.set_status("")
            self.updating_switch = True
            self.switch.set_active(enabled)
            self.switch.set_state(enabled)
            self.updating_switch = False
            self.populate(enabled, nets)
            if then:
                then()

        run_bg(lambda: read_state(rescan), done)

    def populate(self, enabled, nets):
        self.open_row = None
        while (child := self.listbox.get_first_child()) is not None:
            self.listbox.remove(child)
        if not enabled:
            self.placeholder.set_label("Wi-Fi is turned off")
            return
        self.placeholder.set_label("No networks found — try rescan")
        for net in nets:
            self.listbox.append(NetRow(self, net, net["ssid"] in self.saved))

    # ----- events ------------------------------------------------------------
    def on_escape(self):
        """Esc closes the open row first; False when there was none."""
        if self.open_row is None:
            return False
        self.open_row.collapse()
        self.open_row = None
        return True

    def on_switch(self, _sw, state):
        if self.updating_switch:
            return False
        self.set_busy(True)
        self.set_status("Turning Wi-Fi on…" if state else "Turning Wi-Fi off…")

        def done(res):
            code, _, msg = res
            self.set_busy(False)
            if code != 0:
                self.set_status(msg or "Couldn't change Wi-Fi", error=True)
                self.refresh(quiet=True)
                return
            self.set_status("")
            if state:
                self.placeholder.set_label("Looking for networks…")
                # give the card a moment to come up, then scan
                GLib.timeout_add(2500, lambda: (self.refresh(rescan=True), False)[1])
            else:
                self.refresh()

        run_bg(lambda: nm("radio", "wifi", "on" if state else "off"), done)
        return False

    def on_row(self, _lb, row):
        if self.busy:
            return
        if self.open_row is not None and self.open_row is not row:
            self.open_row.collapse()
        if row.revealer.get_reveal_child():
            row.collapse()
            self.open_row = None
            return
        net = row.net
        if net["active"]:
            row.show_actions()
            self.open_row = row
        elif row.saved or not net["secure"]:
            self.connect_net(net, None)
        else:
            row.show_password()
            self.open_row = row

    # ----- actions -----------------------------------------------------------
    def connect_net(self, net, password):
        ssid = net["ssid"]
        was_saved = ssid in self.saved
        self.set_busy(True)
        self.set_status(f"Connecting to {ssid}…")

        def work():
            if password is None and was_saved:
                return nm("connection", "up", "id", ssid, timeout=60)
            args = ["device", "wifi", "connect", ssid]
            if password:
                args += ["password", password]
            return nm(*args, timeout=60)

        def done(res):
            code, _, msg = res
            self.set_busy(False)
            if code == 0:
                self.set_status(f"Connected to {ssid}")
                notify("Connected", ssid)
                self.refresh(quiet=True)
                GLib.timeout_add(900, lambda: (self.host.close(), False)[1])
                return
            # a failed brand-new connection is not kept, so you can simply retry
            if not was_saved:
                threading.Thread(target=nm, args=("connection", "delete", "id", ssid), daemon=True).start()
            wrong_pw = any(w in msg.lower() for w in ("secrets", "password", "802-1x", "psk"))
            if net["secure"]:
                self.set_status("Wrong password — try again" if wrong_pw else msg, error=True)
                row = self.find_row(ssid)
                if row:
                    row.saved = False
                    row.show_password(error=True)
                    self.open_row = row
            else:
                self.set_status(msg or f"Couldn't connect to {ssid}", error=True)

        run_bg(work, done)

    def find_row(self, ssid):
        child = self.listbox.get_first_child()
        while child is not None:
            if isinstance(child, NetRow) and child.net["ssid"] == ssid:
                return child
            child = child.get_next_sibling()
        return None

    def active_name(self):
        _, out, _ = nm("-t", "-f", "NAME,TYPE", "connection", "show", "--active")
        for line in out.splitlines():
            f = split_terse(line)
            if len(f) >= 2 and f[-1] == "802-11-wireless":
                return ":".join(f[:-1])
        return None

    def disconnect(self, net):
        self.set_busy(True)
        self.set_status("Disconnecting…")

        def work():
            name = self.active_name() or net["ssid"]
            return nm("connection", "down", "id", name)

        def done(res):
            self.set_busy(False)
            self.set_status("" if res[0] == 0 else res[2], error=res[0] != 0)
            self.refresh()

        run_bg(work, done)

    def forget(self, net):
        self.set_busy(True)
        self.set_status(f"Forgetting {net['ssid']}…")

        def done(res):
            self.set_busy(False)
            self.set_status("" if res[0] == 0 else res[2], error=res[0] != 0)
            self.refresh()

        run_bg(lambda: nm("connection", "delete", "id", net["ssid"]), done)

    def open_settings(self, *_):
        try:
            subprocess.Popen(["nm-connection-editor"], start_new_session=True)
        except OSError:
            self.set_status("Install nm-connection-editor for advanced settings", error=True)
            return
        self.host.close()


class WifiMenu(Gtk.Application):
    """The popup: the panel in a layer-shell window under the bar."""

    embedded = False

    def __init__(self):
        super().__init__(application_id="io.local.wifimenu")
        self.win = None
        self.panel = None

    # ----- host (see panel.py) ---------------------------------------------------
    def close(self):
        if self.win is not None:
            self.win.close()

    def is_shown(self):
        return self.win is not None and self.win.get_visible()

    # every later launch (clicking the bar icon) opens or closes the same window
    def do_activate(self):
        if self.win is None:
            self.hold()   # keep running while hidden, so the next open is instant
            self.build()
            if "--hidden" in sys.argv:
                self.panel.refresh(quiet=True)
                return
        if self.win.get_visible():
            self.win.close()
        elif GLib.get_monotonic_time() - getattr(self, 'closed_at', 0) > 400_000:
            # the click that just closed it (outside the popup, on the bar icon)
            # also reaches the bar, which asks to open it again: ignore that one
            self.show_popup()

    def show_popup(self):
        self.win.present()
        self.panel.on_show()

    def on_close(self, win):
        self.panel.on_hide()
        self.closed_at = GLib.get_monotonic_time()
        win.set_visible(False)   # hide, don't destroy
        return True

    def build(self):
        prov = Gtk.CssProvider()
        if hasattr(prov, "load_from_string"):          # GTK >= 4.12
            prov.load_from_string(CSS)
        else:
            prov.load_from_data(CSS, -1)
        add = getattr(Gtk, "style_context_add_provider_for_display", None) \
            or Gtk.StyleContext.add_provider_for_display
        add(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)

        win = Gtk.ApplicationWindow(application=self, title="Wi-Fi")
        win.add_css_class("wifi-menu")
        win.set_decorated(False)
        win.connect("close-request", self.on_close)
        self.win = win
        self.panel = WifiPanel(self)
        popup = self.panel.root

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)

        if LS is not None and (not hasattr(LS, "is_supported") or LS.is_supported()):
            # full-screen transparent layer: clicking outside the popup closes it
            LS.init_for_window(win)
            LS.set_namespace(win, "wifi-menu")
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

            popup.set_halign(Gtk.Align.END)
            popup.set_valign(Gtk.Align.START)
            popup.set_margin_top(72)
            popup.set_margin_end(130)
            overlay = Gtk.Overlay()
            overlay.set_child(backdrop)
            overlay.add_overlay(popup)
            win.set_child(overlay)
        else:
            # fallback: normal window that closes when it loses focus
            win.set_child(popup)
            win.connect("notify::is-active", lambda w, _p: None if w.is_active() else w.close())

    def on_key(self, _ctl, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            if not self.panel.on_escape():
                self.win.close()
            return True
        return False


if __name__ == "__main__":
    sys.exit(WifiMenu().run([sys.argv[0]]))
