#!/usr/bin/env bash
# One clickable desk button on the bar (all screens show the same desk).
#   desk.sh N        JSON for waybar: active / occupied / empty
#   desk.sh go N     switch every screen to desk N
# Hyprland signals waybar (RTMIN+8) whenever the desk or the windows change.
#   desk.sh step ±1  previous / next desk (mouse wheel)
if [[ "$1" == go ]]; then
  exec hyprctl eval "desk($2)" >/dev/null
fi
if [[ "$1" == step ]]; then
  cur=$(hyprctl -j activeworkspace | jq '(.id - 1) % 10 + 1')
  exec hyprctl eval "desk($(( (cur - 1 + $2 + 10) % 10 + 1 )))" >/dev/null
fi
n=$1
# Every desk button (on every bar) runs this at the same moment. The first one to get
# the lock reads Hyprland once for all ten desks; the others reuse that answer when it
# was taken after they started (so it is never older than the signal that woke them).
started=${EPOCHREALTIME/./}
STATE="${XDG_RUNTIME_DIR:-/tmp}/desk-state"
exec 9>"$STATE.lock"
flock 9
[[ -r "$STATE" ]] && read -r taken classes < "$STATE"
if [[ -z "$taken" ]] || (( taken < started )); then
  taken=${EPOCHREALTIME/./}
  active=$(hyprctl -j activeworkspace | jq '(.id - 1) % 10 + 1')
  classes=$(hyprctl -j workspaces | jq -r --argjson a "$active" \
    '[range(1; 11) as $n | if $n == $a then "active"
      elif any(.[]; .id >= 1 and ((.id - 1) % 10 + 1) == $n and .windows > 0) then "occupied"
      else "empty" end] | join(" ")')
  echo "$taken $classes" > "$STATE"
fi
class=$(cut -d' ' -f"$n" <<< "$classes")
printf '{"text":"%s","class":"%s","tooltip":"Desk %s"}\n' "$n" "$class" "$n"
