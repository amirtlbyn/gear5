"""Empty lists say one sentence and offer the one action that fills them (roadmap
4.4, spec EMPTY): Wi-Fi, Bluetooth and the minimized-windows picker. The tests
use the real EmptyState widget and click its button; without a display they are
skipped."""

import ast
import os
import re

import gi
import panel
import pytest
from conftest import SCRIPTS

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

needs_display = pytest.mark.skipif(not Gtk.init_check(), reason="needs a display")


def shown(empty):
    """(sentence, hint or "", button label or "") as the person sees them."""
    hint = empty.hint.get_label() if empty.hint.get_visible() else ""
    button = empty.button.get_label() if empty.button.get_visible() else ""
    return empty.text.get_label(), hint, button


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, name):
        return lambda *a, **k: self.calls.append((name, a, k))


@needs_display
def test_wifi_empty_states():
    """EMPTY-1: given Wi-Fi off, then "Wi-Fi is off." and "Turn on Wi-Fi", which
    turns the switch on; given no network, then "No networks nearby." and "Scan
    again", which rescans; while it turns on, "Looking for networks…" and no button."""
    mod = panel.load("wifi-menu")
    empty_state = __import__("empty_state")
    rec = Recorder()

    class Fake:
        def __init__(self):
            self.placeholder = empty_state.EmptyState()
            self.switch = Gtk.Switch()
            self.refresh = rec("refresh")

        def turn_on(self):
            mod.WifiPanel.turn_on(self)

    fake = Fake()
    mod.WifiPanel.show_empty(fake, False)
    assert shown(fake.placeholder) == ("Wi-Fi is off.", "", "Turn on Wi-Fi")
    fake.placeholder.button.emit("clicked")
    assert fake.switch.get_active() is True
    mod.WifiPanel.show_empty(fake, True)
    assert shown(fake.placeholder) == ("No networks nearby.", "", "Scan again")
    fake.placeholder.button.emit("clicked")
    assert rec.calls == [("refresh", (), {"rescan": True})]
    mod.WifiPanel.show_empty(fake, True, turning_on=True)
    assert shown(fake.placeholder) == ("Looking for networks…", "", "")


@needs_display
def test_bluetooth_empty_states():
    """EMPTY-2: given Bluetooth off, then "Bluetooth is off." and "Turn on
    Bluetooth", which powers it on; given no devices, then "No devices yet." and
    "Add device", which starts the search; given no adapter, then no button."""
    mod = panel.load("control-center")
    empty_state = __import__("empty_state")
    rec = Recorder()

    class Fake:
        def __init__(self):
            self.dev_placeholder = empty_state.EmptyState()
            self.set_power = rec("set_power")
            self.toggle_scan = rec("toggle_scan")

    fake = Fake()
    mod.BluetoothPanel.show_empty(fake, True, False)
    assert shown(fake.dev_placeholder) == ("Bluetooth is off.", "", "Turn on Bluetooth")
    fake.dev_placeholder.button.emit("clicked")
    mod.BluetoothPanel.show_empty(fake, True, True)
    assert shown(fake.dev_placeholder) == ("No devices yet.", "", "Add device")
    fake.dev_placeholder.button.emit("clicked")
    assert rec.calls == [("set_power", (True,), {}), ("toggle_scan", (), {})]
    mod.BluetoothPanel.show_empty(fake, False, False)
    assert shown(fake.dev_placeholder) == ("No Bluetooth adapter found.", "", "")


@needs_display
def test_picker_empty_state():
    """EMPTY-3: given nothing minimized, then "Nothing is minimized.", the SUPER+A
    hint and a "Close" button that leaves the picker."""
    with open(os.path.join(SCRIPTS, "minimized-picker.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    call = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "update"
        and ast.unparse(n.func.value) == "self.empty_box"
    )
    kw = {k.arg: k.value for k in call.keywords}
    assert ast.literal_eval(call.args[0]) == "Nothing is minimized."
    assert ast.literal_eval(kw["hint"]) == "SUPER+A minimizes the window you are in."
    assert ast.literal_eval(kw["button"]) == "Close"
    assert ast.unparse(kw["action"]) == "lambda: self.leave()"

    empty_state = __import__("empty_state")
    empty = empty_state.EmptyState()
    left = []
    empty.update(
        "Nothing is minimized.", hint="h", button="Close", action=lambda: left.append(1)
    )
    empty.button.emit("clicked")
    assert left == [1]


def test_empty_states_look_the_same_everywhere():
    """EMPTY-4: given the three popups, then each one's CSS (and so Settings'
    scoped copy) holds the shared empty-state rules, which use theme colors only."""
    empty_state = __import__("empty_state")
    css = empty_state.CSS
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)
    assert re.search(r"\.empty-text \{[^}]*color: @fg;", css)
    assert re.search(r"button\.empty-action \{[^}]*background: @green;", css)
    assert css in panel.load("wifi-menu").STYLE
    assert css in panel.load("control-center").STYLE
    assert css in panel.load("minimized-picker").CSS
