"""CHAR-7: given the pop-up sticker, when its window is built (not shown), then its keyboard
mode is none and its input region is empty. Run under tests/private-bus.conf by
tests/smoke_sticker.sh."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "waybar", "scripts"))
import sticker  # noqa: E402
from gi.repository import Gdk  # noqa: E402

regions = []
real = Gdk.Surface.set_input_region
Gdk.Surface.set_input_region = lambda self, region: (regions.append(region), real(self, region))

app = sticker.Sticker("zoro")
app.register(None)
win = sticker.build(app, "zoro")
win.realize()
mode = sticker.LS.get_keyboard_mode(win) if sticker.LS else None
ok = (mode == sticker.LS.KeyboardMode.NONE if sticker.LS else True) and len(regions) == 1 and regions[0].is_empty()
print("ok" if ok else f"FAIL keyboard mode {mode}, regions {len(regions)}", file=sys.stderr)
sys.exit(0 if ok else 1)
