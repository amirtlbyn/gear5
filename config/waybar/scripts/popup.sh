#!/usr/bin/env bash
# Open or close a popup instantly: the popup keeps running hidden in the background,
# so this only sends it a D-Bus message (no Python start-up). If it isn't running
# yet, start it, and it opens.
#   popup.sh volume-popup|control-center|wifi-menu|calendar-popup|power-popup|calculator|worldclock|emoji-picker|clipboard|launcher|displays|minimized-picker [THEME]
#   popup.sh --restart [THEME]    (re)start them all hidden, e.g. at login or on theme change
# THEME is a file name in ~/.config/hypr/themes/; without one, the theme in use.
#   popup.sh --close-all          close whatever popup is open (desk switch, new window, ...)
#   popup.sh launcher --minimized  open the launcher on its list of minimized windows (kept for
#                                  the launcher's own Minimized tab; SUPER+SHIFT+- and the bar's
#                                  counter open minimized-picker instead)
dir=~/.config/waybar/scripts
all="volume-popup control-center wifi-menu calendar-popup power-popup calculator worldclock emoji-picker clipboard launcher displays minimized-picker"
# each open popup leaves a mark here (see popup_backdrop.py)
marks="${XDG_RUNTIME_DIR:-/tmp}/popups"

close_open() {   # close every open popup except $1
  local mark id
  for mark in "$marks"/*; do
    [[ -e "$mark" ]] || continue
    id=${mark##*/}
    [[ "$id" == "$1" ]] && continue
    gdbus call --session --dest "$id" --object-path "/${id//.//}" \
      --method org.freedesktop.Application.ActivateAction close-popup '[]' '{}' >/dev/null 2>&1 \
      || rm -f "$mark"   # it isn't running any more
  done
}

if [[ "$1" == --restart ]]; then
  # one restart at a time (a theme switch and a reload can both ask for one)
  exec 9>"${XDG_RUNTIME_DIR:-/tmp}/popups-restart.lock"
  flock 9
  for p in $all; do pkill -f "$dir/$p.py"; done
  rm -rf "$marks"
  # wait until the old ones are really gone: a new popup that still finds the old
  # one on D-Bus hands it an "open" instead of starting hidden
  for _ in {1..30}; do
    pgrep -f "$dir/($(tr ' ' '|' <<<"$all"))\.py" >/dev/null || break
    sleep 0.1
  done
  pkill -9 -f "$dir/($(tr ' ' '|' <<<"$all"))\.py"
  for p in $all; do
    setsid "$dir/$p.py" "$2" --hidden >/dev/null 2>&1 9>&- &   # 9>&-: the popup must not keep the lock
  done
  exit
fi
if [[ "$1" == --close-all ]]; then
  close_open
  exit
fi
case "$1" in
  volume-popup)   id=io.local.volumepopup ;;
  control-center) id=io.local.controlcenter ;;
  wifi-menu)      id=io.local.wifimenu ;;
  calendar-popup) id=io.local.calendarpopup ;;
  power-popup)    id=io.local.powerpopup ;;
  calculator)     id=io.local.calculator ;;
  worldclock)     id=io.local.worldclock ;;
  emoji-picker)   id=io.local.emojipicker ;;
  clipboard)      id=io.local.clipboard ;;
  launcher)       id=io.local.launcher ;;
  displays)       id=io.local.displays ;;
  minimized-picker) id=io.local.minimizedpicker ;;
  *) exit 1 ;;
esac
# only one popup at a time
close_open "$id"
if [[ "$1" == launcher && "$2" == --minimized ]]; then
  gdbus call --session --dest "$id" --object-path "/${id//.//}" \
    --method org.freedesktop.Application.ActivateAction show-minimized '[]' '{}' >/dev/null 2>&1 && exit
  exec "$dir/launcher.py" "" --minimized
fi
gdbus call --session --dest "$id" --object-path "/${id//.//}" \
  --method org.freedesktop.Application.Activate '{}' >/dev/null 2>&1 && exit
exec "$dir/$1.py" "$2"
