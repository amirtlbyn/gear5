#!/usr/bin/env bash
# LIVE SESSION ONLY (needs a running Hyprland, Waybar and the popup/Settings daemons).
# Switches to an empty desk, grims the bar with no windows, then opens each popup and
# Settings page in turn and grims it, into docs/screenshots/*.png. Switches back to the
# desk it started on when done. Skips the clipboard popup: it shows real history — GEAR-17
#   tests/screenshots.sh
# The shots are of YOUR desktop. Before you publish them, blur what is private: Wi-Fi
# and Bluetooth names (Wi-Fi, control center, Bluetooth), and your city (calendar weather,
# world clock). The launcher is taken on its Actions tab so no recent files show.
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd)/docs/screenshots"
mkdir -p "$DIR"
SCRIPTS=~/.config/waybar/scripts
marks="${XDG_RUNTIME_DIR:-/tmp}/popups"
fail=0

mon=$(hyprctl -j monitors | jq -r '.[] | select(.focused) | .name')

shrink() {  # $1 = a PNG path; optimize it, then scale it down until it is reasonably small
  if command -v oxipng >/dev/null 2>&1; then
    oxipng -q -o4 "$1" >/dev/null 2>&1
  elif command -v pngquant >/dev/null 2>&1; then
    pngquant --force --quality 65-90 --output "$1" "$1" >/dev/null 2>&1
  fi
  python3 - "$1" <<'PY'
import os
import sys

from PIL import Image

path = sys.argv[1]
limit = 580_000  # stay under the 600 KB budget with a margin
img = Image.open(path)
for _ in range(6):
    if os.path.getsize(path) <= limit:
        break
    w, h = img.size
    img = img.resize((max(1, round(w * 0.8)), max(1, round(h * 0.8))), Image.LANCZOS)
    img.save(path, optimize=True)
PY
}

wait_for_popup() {  # up to 3 s for a popup's mark file to appear
  for _ in $(seq 1 30); do
    [[ -n "$(ls -A "$marks" 2>/dev/null)" ]] && return 0
    sleep 0.1
  done
  return 1
}

settings_geom() {  # "x,y wxh" of the io.local.settings window, or empty
  hyprctl -j clients | jq -r '.[] | select(.class == "io.local.settings") |
    "\(.at[0]),\(.at[1]) \(.size[0])x\(.size[1])"' | head -1
}

wait_for_settings() {  # up to 3 s for the Settings window to be mapped
  for _ in $(seq 1 30); do
    [[ -n "$(settings_geom)" ]] && return 0
    sleep 0.1
  done
  return 1
}

press() {  # $1 = a key for the focused surface, e.g. Tab
  hyprctl eval "hl.dispatch(hl.dsp.send_shortcut({ mods = '', key = '$1' }))" >/dev/null
  sleep 0.3
}

shot_popup() {  # $1 = popup.sh name, $2 = output file stem, $3... = keys to press first
  "$SCRIPTS/popup.sh" "$1" >/dev/null 2>&1 &
  disown
  if wait_for_popup; then
    sleep 0.4
    for key in "${@:3}"; do press "$key"; done
    grim -o "$mon" "$DIR/$2.png"
    shrink "$DIR/$2.png"
    echo "ok   $2.png"
  else
    echo "FAIL $1 did not open"
    fail=1
  fi
  "$SCRIPTS/popup.sh" --close-all >/dev/null 2>&1
  sleep 0.3
}

shot_settings() {  # $1 = settings.py argument (a page, or theme-new), $2 = output file stem
  "$SCRIPTS/settings.py" "$1" >/dev/null 2>&1 &
  disown
  if wait_for_settings; then
    # a page switch crossfades, and the editor builds its widgets from scratch:
    # both need more than a moment to settle before the shot
    sleep 1.2
    grim -g "$(settings_geom)" "$DIR/$2.png"
    shrink "$DIR/$2.png"
    echo "ok   $2.png"
  else
    echo "FAIL settings $1 did not open"
    fail=1
  fi
}

before_desk=$(hyprctl -j activeworkspace | jq '(.id - 1) % 10 + 1')
empty_desk=$(hyprctl -j workspaces | jq '[.[] | select(.windows == 0)] | .[0].id // empty')
if [[ -z "$empty_desk" ]]; then
  echo "FAIL no empty desk to screenshot on (every desk has a window)"
  exit 1
fi
"$SCRIPTS/desk.sh" go "$empty_desk" >/dev/null
sleep 0.3

# the bar, with no windows on screen
grim -o "$mon" "$DIR/desktop.png"
shrink "$DIR/desktop.png"
echo "ok   desktop.png"

# every popup but clipboard (skipped: it would show real clipboard history)
shot_popup volume-popup   popup-volume
shot_popup control-center popup-control-center
shot_popup wifi-menu      popup-wifi
shot_popup power-popup    popup-power
shot_popup calculator     popup-calculator
shot_popup worldclock     popup-worldclock
shot_popup emoji-picker   popup-emoji
# the Actions tab: All shows your most used apps and recent files, which are private
shot_popup launcher       popup-launcher Tab Tab Tab Tab Tab
shot_popup displays       popup-displays
# minimize a window first (SUPER+A), so this card grid has something to show
shot_popup minimized-picker popup-minimized-picker

# every Settings page, then the theme editor
shot_settings theme         settings-theme
shot_settings wallpaper     settings-wallpaper
shot_settings fonts         settings-fonts
shot_settings displays      settings-displays
shot_settings wifi          settings-wifi
shot_settings bluetooth     settings-bluetooth
shot_settings sound         settings-sound
shot_settings power         settings-power
shot_settings battery       settings-battery
shot_settings notifications settings-notifications
shot_settings keyboard      settings-keyboard
shot_settings shortcuts     settings-shortcuts
shot_settings look          settings-look
shot_settings theme-new     theme-editor

settings_pid=$(hyprctl -j clients | jq -r '.[] | select(.class == "io.local.settings") | .pid' | head -1)
[[ -n "$settings_pid" ]] && kill "$settings_pid" 2>/dev/null
"$SCRIPTS/popup.sh" --close-all >/dev/null 2>&1

"$SCRIPTS/desk.sh" go "$before_desk" >/dev/null

exit $fail
