#!/usr/bin/env bash
# The one way to lock the screen (spec GIF-7): SUPER+L, hypridle, the launcher and
# the power popup all run this. A second lock while locked starts nothing (QSL-2).
# The lock is the Quickshell config in ~/.config/quickshell/lock (spec QSL).
#   lock.sh refresh   the old hyprlock path, kept until the hyprlock removal (QSL-12):
#                     replace a running hyprlock with a new one only when it needs it
#                     (spec LOCKQ). Nothing happens when not locked.
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
# one locker at a time (QSL-2, INV-2): fd 8 stays open in the locker, so the lock file
# stays held even if this script is killed (no runtime folder: no lock file, never a
# file in the shared /tmp)
if [[ -n "$XDG_RUNTIME_DIR" ]]; then
  exec 8>"$XDG_RUNTIME_DIR/gear5-lock.lock"
  flock -n 8 || exit 0
fi
hyprctl switchxkblayout all 0
# the lock before this one stays in lock.log.1, so a lock that went wrong can still
# be read after the next one starts (QSL-11)
QSLOG="${XDG_RUNTIME_DIR:+$XDG_RUNTIME_DIR/lock.log}"
QSLOG="${QSLOG:-/dev/null}"
[[ "$QSLOG" != /dev/null && -f "$QSLOG" ]] && mv -f "$QSLOG" "$QSLOG.1"
lock() { qs -p "$HOME/.config/quickshell/lock" >> "$QSLOG" 2>&1; }
# exit 0 is an unlock; anything else (killed, crashed) is run once more, which takes
# the session lock over (QSL-7). Once, so a lock that dies at start does not loop.
if lock || lock; then exit 0; fi
# both starts failed (qs missing, a QML error, a crash): say so, and lock with hyprlock
# while it is installed, so a lock request never leaves the session open (QSL-13)
notify-send -u critical "Lock screen failed" "Quickshell did not start; see lock.log" 2>/dev/null
# exec: hyprlock itself holds fd 8, so a refresh that ends it frees the lock file at once
command -v hyprlock >/dev/null && exec hyprlock >> "$QSLOG" 2>&1
