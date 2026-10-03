"""The smoke tests' private D-Bus bus starts no service (spec PORTAL). With the
default session config, GTK's portal call on a private bus started a second
xdg-desktop-portal: its document portal unmounted /run/user/$UID/doc when the bus
closed, and its xdg-desktop-portal-hyprland segfaulted."""

import os
import re
import shutil
import subprocess

import pytest
from conftest import ROOT

TESTS = os.path.join(ROOT, "tests")
CONF = os.path.join(TESTS, "private-bus.conf")
ASK_BUS = """
from gi.repository import Gio, GLib
bus = Gio.bus_get_sync(Gio.BusType.SESSION)
def call(method, args=None):
    return bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                         method, args, None, Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
print(" ".join(call("ListActivatableNames")))
try:
    call("StartServiceByName", GLib.Variant("(su)", ("org.freedesktop.portal.Desktop", 0)))
    print("started")
except GLib.Error as e:
    print("refused", e.message)
"""


@pytest.mark.skipif(not shutil.which("dbus-run-session"), reason="needs dbus-run-session")
def test_the_private_bus_activates_no_service():
    """PORTAL-1: given the smoke tests' bus config, when a program on that bus
    lists the services it could start and asks for the desktop portal, then the
    list is only the bus itself and the portal is refused (not started)."""
    out = subprocess.run(
        ["dbus-run-session", f"--config-file={CONF}", "--", "python3", "-c", ASK_BUS],
        capture_output=True, text=True, timeout=30, check=True,
    ).stdout.splitlines()

    assert out[0] == "org.freedesktop.DBus"
    assert out[1].startswith("refused")


def test_every_private_bus_call_uses_the_config():
    """PORTAL-2: given the smoke scripts and the smoke .py usage lines, when they
    are read, then every dbus-run-session call passes the private bus config."""
    calls = []
    for name in sorted(os.listdir(TESTS)):
        if name.startswith("smoke_"):
            text = open(os.path.join(TESTS, name)).read()
            calls += [(name, m) for m in re.findall(r"dbus-run-session(?: [^\n]*?)? --(?: |$)", text, re.M)]

    assert len(calls) == 9
    for name, call in calls:
        assert re.search(r'--config-file=("\$bus_conf"|tests/private-bus\.conf) --', call), (name, call)
