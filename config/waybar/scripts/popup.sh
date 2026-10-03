#!/usr/bin/env bash
# Open or close a popup instantly: the popup keeps running hidden in the background,
# so this only sends it a D-Bus message (no Python start-up). If it isn't running
# yet, start it, and it opens.
#   popup.sh volume-popup|control-center|wifi-menu|power-popup|calculator|worldclock|emoji-picker|clipboard|launcher|displays|minimized-picker|overview [THEME]
#   popup.sh --restart [THEME]    (re)start them all hidden, e.g. at login or on theme change;
#                                 also stops a hidden popup whose script is gone (removed in an update)
# THEME is a file name in ~/.config/hypr/themes/; without one, the theme in use.
#   popup.sh --close-all          close whatever popup is open (desk switch, new window, ...)
#   popup.sh --unstick            kill an open popup that hangs and holds the keyboard, and
#                                 start it again hidden (SUPER+SHIFT+Escape)
#   popup.sh launcher --minimized  open the launcher on its list of minimized windows (kept for
#                                  the launcher's own Minimized tab; SUPER+SHIFT+- and the bar's
#                                  counter open minimized-picker instead)
dir=~/.config/waybar/scripts
all="volume-popup control-center wifi-menu power-popup calculator worldclock emoji-picker clipboard launcher displays minimized-picker overview"
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

app_id() {   # the popup's D-Bus name, which also names its mark
  case "$1" in
    volume-popup)   echo io.local.volumepopup ;;
    control-center) echo io.local.controlcenter ;;
    wifi-menu)      echo io.local.wifimenu ;;
    power-popup)    echo io.local.powerpopup ;;
    calculator)     echo io.local.calculator ;;
    worldclock)     echo io.local.worldclock ;;
    emoji-picker)   echo io.local.emojipicker ;;
    clipboard)      echo io.local.clipboard ;;
    launcher)       echo io.local.launcher ;;
    displays)       echo io.local.displays ;;
    minimized-picker) echo io.local.minimizedpicker ;;
    overview)       echo io.local.overview ;;
    *) return 1 ;;
  esac
}

if [[ "$1" == --restart ]]; then
  # one restart at a time (a theme switch and a reload can both ask for one)
  exec 9>"${XDG_RUNTIME_DIR:-/tmp}/popups-restart.lock"
  flock 9
  for p in $all; do pkill -f "$dir/$p.py"; done
  # a hidden popup whose script is gone (removed or renamed in an update) is in no
  # list: stop it too, or it keeps its memory until the next login
  for pid in $(pgrep -f -- "$dir/[^ ]+\.py( .*)? --hidden"); do
    mapfile -d '' args < "/proc/$pid/cmdline" 2>/dev/null || continue
    for a in "${args[@]}"; do
      if [[ "$a" == "$dir/"*.py ]]; then
        [[ -e "$a" ]] || kill "$pid" 2>/dev/null
        break
      fi
    done
  done
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
if [[ "$1" == --unstick ]]; then
  # SUPER+SHIFT+Escape. An open popup holds the keyboard (its layer is exclusive); if
  # it hangs or is paused, it answers neither keys nor D-Bus. Kill each popup that has
  # a layer on a screen (-9: a paused process acts on SIGTERM only after SIGCONT) and
  # start it again hidden. Hidden popups have no layer; other layers are not ours.
  for pid in $(hyprctl layers -j | jq '.[].levels[][].pid' | sort -u); do
    mapfile -d '' args < "/proc/$pid/cmdline" 2>/dev/null || continue
    for a in "${args[@]}"; do
      [[ "$a" == "$dir/"*.py ]] || continue
      p=${a#"$dir/"}; p=${p%.py}
      [[ " $all " == *" $p "* ]] || break
      kill -9 "$pid"
      rm -f "$marks/$(app_id "$p")"
      # wait until it is really gone: a new popup that still finds the old one on
      # D-Bus hands it an "open" instead of starting hidden
      for _ in {1..20}; do [[ -e /proc/$pid ]] || break; sleep 0.1; done
      setsid "$dir/$p.py" "" --hidden >/dev/null 2>&1 &
      break
    done
  done
  exit
fi
if [[ "$1" == --close-all ]]; then
  close_open
  exit
fi
id=$(app_id "$1") || exit 1
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
