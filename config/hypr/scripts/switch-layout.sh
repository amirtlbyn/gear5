#!/usr/bin/env bash
# Switch every keyboard to the next layout together, starting from the layout
# of the main keyboard (the one you type on), so all devices stay in sync.
read -r idx count < <(hyprctl devices -j | jq -r '[.keyboards[] | select(.main)][0] | "\(.active_layout_index) \(.layout | split(",") | length)"')
hyprctl switchxkblayout all $(( (${idx:-0} + 1) % ${count:-2} )) >/dev/null
