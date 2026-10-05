#!/usr/bin/env bash
# Waybar: how many windows are minimized (SUPER+A). Empty (hidden) when none.
# The bar asks again on signal RTMIN+10, sent by hyprland.lua when windows move.
n=$(hyprctl -j clients 2>/dev/null | jq '[.[] | select(.workspace.name == "special:minimized")] | length' 2>/dev/null)
if [[ -z "$n" || "$n" == 0 ]]; then
  echo '{"text": ""}'
else
  printf '{"text": "󰖰 %s", "tooltip": "%s minimized · click for the picker · SUPER+- brings back the last one", "class": "has"}\n' "$n" "$n"
fi
