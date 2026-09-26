#!/usr/bin/env bash
# Open or close a popup instantly: the popup keeps running hidden in the background,
# so this only sends it a D-Bus message (no Python start-up). If it isn't running
# yet, start it, and it opens.
#   popup.sh volume-popup|control-center|wifi-menu|calendar-popup|power-popup|calculator|worldclock|emoji-picker|clipboard|launcher THEME
#   popup.sh --restart THEME      (re)start them all hidden, e.g. at login or on theme change
#   popup.sh --close-all          close whatever popup is open (desk switch, new window, ...)
dir=~/.config/waybar/scripts
all="volume-popup control-center wifi-menu calendar-popup power-popup calculator worldclock emoji-picker clipboard launcher"
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
  for p in $all; do pkill -f "$dir/$p.py"; done
  rm -rf "$marks"
  sleep 0.3
  for p in $all; do
    setsid "$dir/$p.py" "$2" --hidden >/dev/null 2>&1 &
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
  *) exit 1 ;;
esac
# only one popup at a time
close_open "$id"
gdbus call --session --dest "$id" --object-path "/${id//.//}" \
  --method org.freedesktop.Application.Activate '{}' >/dev/null 2>&1 && exit
exec "$dir/$1.py" "$2"
