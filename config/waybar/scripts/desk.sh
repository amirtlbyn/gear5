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
active=$(hyprctl -j activeworkspace | jq '(.id - 1) % 10 + 1')
used=$(hyprctl -j workspaces | jq --argjson n "$n" \
  '[.[] | select(.id >= 1 and ((.id - 1) % 10 + 1) == $n and .windows > 0)] | length')
if [[ "$active" == "$n" ]]; then class=active
elif (( used > 0 )); then class=occupied
else class=empty
fi
printf '{"text":"%s","class":"%s","tooltip":"Desk %s"}\n' "$n" "$class" "$n"
