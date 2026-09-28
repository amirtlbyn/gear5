"""
The minimized-windows picker builds its grid — cards, newest first, numbered,
thumbnails skipped — from a fake client list. Never touches the real hyprctl
clients, grim, or a real window; the window is never presented. Run by
smoke_popups.sh on a private D-Bus session over the live display:

    GTK_A11Y=none dbus-run-session -- python3 tests/smoke_minimized_picker.py

Exit 0 when the grid held the right cards, in the right order, numbered.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "waybar", "scripts")
)
sys.argv = ["minimized-picker.py", "--hidden"]
import panel  # noqa: E402
from gi.repository import GLib  # noqa: E402

mod = panel.load("minimized-picker")

FAKE_CLIENTS = [
    {"address": "0x1", "title": "kitty A", "class": "kitty", "workspace": {"name": "special:minimized"}},
    {"address": "0x2", "title": "kitty B", "class": "kitty", "workspace": {"name": "special:minimized"}},
    {"address": "0x3", "title": "Zen", "class": "zen", "workspace": {"name": "1"}},  # not minimized
    {"address": "0x4", "title": "Telegram", "class": "telegram", "workspace": {"name": "special:minimized"}},
]
mod.read_clients = lambda: FAKE_CLIENTS  # never the real hyprctl clients
mod.capture_thumbnail = lambda client, thumb_dir=mod.THUMB_DIR: None  # never grim a real window
spawned = []
mod.spawn = spawned.append  # never run hyprctl: a close is only recorded
NO_ORDER_FILE = "/nonexistent/hypr-minimized"  # never the live session's order file

app = mod.Picker()
failed = []
sys.excepthook = lambda *exc: (failed.append(exc), sys.__excepthook__(*exc))


def check():
    try:
        # the same three steps show_popup() takes, minus present(): this window
        # is never shown on screen during the smoke run
        app.windows = mod.minimized_windows(mod.read_clients(), NO_ORDER_FILE)
        app.render(reset=True)
        app.start_thumbnails()
        if [c.address for c in app.cards] != ["0x1", "0x2", "0x4"]:
            failed.append("cards")
            print(f"FAIL expected [0x1, 0x2, 0x4], got {[c.address for c in app.cards]}", file=sys.stderr)
        # closing a card numbers the rest again: key 1 then restores the card that shows "1"
        app.close_window(app.cards[0])
        badges = {c.number: c.address for c in app.cards}
        if spawned != [mod.close_cmd("0x1")]:
            failed.append("close")
            print(f"FAIL close ran {spawned}", file=sys.stderr)
        for digit in (1, 2):
            target = mod.number_target(app.items, digit)
            if badges.get(digit) != (target or {}).get("address"):
                failed.append("numbers")
                print(
                    f"FAIL key {digit} restores {target}, badge {digit} is on {badges.get(digit)}",
                    file=sys.stderr,
                )
        # with filter text the badges go: typed digits belong to the filter
        app.search.set_text("kitty")
        app.render()
        if any(c.number is not None for c in app.cards):
            failed.append("filter badges")
            print("FAIL number badges still shown while filtering", file=sys.stderr)
    finally:
        app.quit()
    return False


GLib.timeout_add(200, check)
# only argv[0]: GLib's own option parser rejects "--hidden" as an unknown option
# and returns from run() before activate ever fires, otherwise
app.run([sys.argv[0]])
sys.exit(1 if failed else 0)
