#!/usr/bin/env bash
# The one way to lock the screen (spec GIF-7): SUPER+L, hypridle, the launcher and
# the power popup all run this. A second lock while locked starts nothing.
# hyprlock plays no GIF; gif_player.py --lock flips its picture (SIGUSR2 per frame).
# The player is decoration: it never delays or blocks the lock (INV-4).
#   lock.sh refresh   a screen came while locked: hyprlock 0.9.6 draws nothing on it
#                     (Hyprland's lockdead picture, no key gets through), so replace the
#                     running hyprlock with a new one. Nothing happens when not locked.
if [[ "$1" == refresh ]]; then
  # screens come in bursts: one refresh, once they settle
  exec 9>"${XDG_RUNTIME_DIR:-/tmp}/hypr-lock-refresh.lock"
  flock -n 9 || exit 0
  sleep 2
  pid=$(pidof hyprlock) || exit 0
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
hyprlock &
pid=$!
"$HOME/.config/waybar/scripts/gif_player.py" --lock "$pid" >/dev/null 2>&1 &
wait "$pid"
