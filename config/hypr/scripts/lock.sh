#!/usr/bin/env bash
# The one way to lock the screen (spec GIF-7): SUPER+L, hypridle, the launcher and
# the power popup all run this. A second lock while locked starts nothing.
# hyprlock plays no GIF; gif_player.py --lock flips its picture (SIGUSR2 per frame).
# The player is decoration: it never delays or blocks the lock (INV-4).
#   lock.sh refresh   a screen came while locked: replace the running hyprlock with a
#                     new one only when it needs it (spec LOCKQ). Nothing happens when
#                     not locked.
# hyprlock's log of the current lock: the refresh reads it (LOCKQ-1)
# (no runtime folder: no log, never a file in the shared /tmp)
LOG="${XDG_RUNTIME_DIR:+$XDG_RUNTIME_DIR/hyprlock.log}"
LOG="${LOG:-/dev/null}"

# hyprlock is fine as it is: it locked and is now unlocking (ending it shows Hyprland's
# "lockscreen app died" page), or it locked and has a lock surface on every active
# screen. A screen it knew before it locked is covered; one that came later is covered
# once hyprlock logs a new lock surface for it (0.9.6 does that for a screen that returns).
leave_alone() {
  local age names name
  if ! grep -q 'onLockLocked called' "$LOG" 2>/dev/null; then
    # not locked yet: wait out Hyprland's own 5 s, then it is stuck, even when it
    # logged an unlock it could not finish
    age=$(ps -o etimes= -p "$1") || return 1
    age=${age//[^0-9]/}
    if (( age < 5 )); then sleep $((5 - age)); fi
    grep -q 'onLockLocked called' "$LOG" 2>/dev/null || return 1
  fi
  # an accepted password logs "authenticated for" before the fade-out, "Unlocking
  # session" after it; only lines after the lock count
  awk '/onLockLocked called/ { l = 1 } l && /Unlocking|authenticated for/ { f = 1 } END { exit !f }' "$LOG" \
    && return 0
  names=$(hyprctl monitors | awk '/^Monitor /{print $2}')
  [[ -n "$names" ]] || return 1  # the screens cannot be listed: replace, as before
  for name in $names; do
    awk -v n="$name" '
      /onLockLocked called/ { locked = 1 }
      /output [0-9]+ description / && index($0, "(" n ")") {
        match($0, /output [0-9]+ /); id = substr($0, RSTART + 7, RLENGTH - 8); ok = !locked; seen = 1
      }
      id != "" && index($0, "output " id " creating a new lock surface") { ok = 1 }
      END { exit !(seen && ok) }' "$LOG" || return 1
  done
}

if [[ "$1" == refresh ]]; then
  # screens come in bursts: one refresh, once they settle
  exec 9>"${XDG_RUNTIME_DIR:-/tmp}/hypr-lock-refresh.lock"
  flock -n 9 || exit 0
  sleep 2
  pid=$(pidof hyprlock) || exit 0
  leave_alone "$pid" && exit 0
  # SIGTERM, never SIGUSR1: hyprlock does not catch it, so it ends without unlocking
  # and Hyprland keeps the session locked (allow_session_lock_restore) for the new one
  kill -TERM $pid
  # at most 5 s; a locker that will not end is killed, still without an unlock
  for _ in {1..50}; do kill -0 $pid 2>/dev/null || break; sleep 0.1; done
  kill -KILL $pid 2>/dev/null
  exec 9>&-
  exec "$0"
fi
pidof hyprlock >/dev/null && exit 0
hyprctl switchxkblayout all 0
hyprlock > "$LOG" 2>&1 &
pid=$!
"$HOME/.config/waybar/scripts/gif_player.py" --lock "$pid" >/dev/null 2>&1 &
wait "$pid"
