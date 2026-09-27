"""
Build every Settings page once, with the window hidden, and let the panels read the
system for a few seconds. Run by smoke_popups.sh on a private D-Bus session:

    GTK_A11Y=none dbus-run-session -- python3 tests/smoke_settings_pages.py

Exit 0 when every panel page was built and nothing raised.
"""

import os
import subprocess
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "waybar", "scripts")
)
sys.argv = ["settings.py", "--hidden"]
import settings  # noqa: E402
from gi.repository import Gdk, GLib  # noqa: E402

app = settings.Settings()
failed = []
sys.excepthook = lambda *exc: (failed.append(exc), sys.__excepthook__(*exc))


def visit():
    for key, _icon, _name in settings.PAGES:
        app.show_page(key)
        app.page_shown(key)  # as if the window were open
        app.panel_hidden(key)
        if key in settings.PANELS and key not in app.panels:
            failed.append(key)
            print("FAIL page " + key, file=sys.stderr)
    app.apply_css()  # a theme switch recolors every panel
    return False


def visit_editor():
    """The theme editor: a new theme, and editing an existing one, builds every color
    picker and the Advanced expander (GEAR-9, GEAR-10, GEAR-13), then one color change
    runs the live-preview redraw (GEAR-11)."""
    app.open_editor(None)
    app.open_editor(settings.palette.DEFAULT)
    picked = Gdk.RGBA()
    picked.parse("#334455")
    app.editor_choosers["bg"].props.rgba = picked
    app.show_page("theme")
    return False


def open_page(name):
    """`settings.py NAME --hidden`, as SUPER+I or a terminal would, to the running Settings."""
    subprocess.Popen([sys.executable, os.path.join(settings.SCRIPTS, "settings.py"), name, "--hidden"])
    return False


def expect(page):
    if app.page != page:
        failed.append(page)
        print(f"FAIL command line opened {app.page}, not {page}", file=sys.stderr)
    return False


def finish():
    app.quit()
    return False


GLib.timeout_add(500, visit)
GLib.timeout_add(1000, visit_editor)
GLib.timeout_add(1500, lambda: open_page("input"))  # the old name of Keyboard & touchpad
GLib.timeout_add(4000, lambda: expect("keyboard") or open_page("wifi"))
GLib.timeout_add(6500, lambda: expect("wifi"))
GLib.timeout_add(7000, finish)
app.run(sys.argv)
sys.exit(1 if failed else 0)
