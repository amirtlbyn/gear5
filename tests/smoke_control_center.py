"""
G5-5: the quick settings popup keeps its battery + power mode card, tiles,
brightness card, Bluetooth list and footer, in that order and working, after
the battery and brightness cards became panels shared with Settings. Run by
smoke_popups.sh on a private D-Bus session over the live display:

    GTK_A11Y=none dbus-run-session --config-file=tests/private-bus.conf -- python3 tests/smoke_control_center.py

Exit 0 when the popup built, battery, brightness and Bluetooth sit in the popup
in the old order, and the brightness card filled from the real screens.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "waybar", "scripts")
)
sys.argv = ["control-center.py", "--hidden"]
import panel  # noqa: E402
from gi.repository import GLib  # noqa: E402

mod = panel.load("control-center")
app = mod.ControlCenter()
failed = []
ran = []  # PH0-3: the checks really ran (a run that never reaches them must fail)
sys.excepthook = lambda *exc: (failed.append(exc), sys.__excepthook__(*exc))


def check():
    ran.append(True)
    try:
        children = []
        child = app.popup.get_first_child()
        while child is not None:
            children.append(child)
            child = child.get_next_sibling()
        for part, what in (
            (app.bat.root, "battery"),
            (app.bright.root, "brightness"),
            (app.bt.root, "bluetooth"),
        ):
            if part not in children:
                failed.append(what)
                print(f"FAIL the popup lost its {what} part", file=sys.stderr)
        if not failed and not (
            children.index(app.bat.root) < children.index(app.bright.root) < children.index(app.bt.root)
        ):
            failed.append("order")
            print("FAIL battery/brightness/bluetooth order changed", file=sys.stderr)
        # the brightness card filled from the real screens (read_screens ran)
        if app.st is not None and app.st["screens"]:
            if not app.bright.card.get_visible() or not app.bright.screen_scales:
                failed.append("brightness")
                print("FAIL brightness card did not fill from the screens", file=sys.stderr)
            else:
                print(f"brightness: {len(app.bright.screen_scales)} screens, card visible", file=sys.stderr)
    finally:
        app.quit()
    return False


# the popup refreshes once at start (build + refresh). ddcutil needs a moment.
GLib.timeout_add(4000, check)
# only argv[0]: GLib's own option parser rejects "--hidden" as an unknown option and
# returns from run() before activate fires, so check() never ran and the smoke
# passed without checking anything (PH0-3). start_hidden already read sys.argv.
app.run([sys.argv[0]])
if not ran:
    print("FAIL the checks never ran", file=sys.stderr)
sys.exit(1 if failed or not ran else 0)
