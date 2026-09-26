#!/bin/sh
# Layout of the main keyboard (the one you type on), not the first device in the list
hyprctl devices -j | jq -r '[.keyboards[] | select(.main)][0].active_keymap // ""' | grep -qi persian && echo "FA" || echo "EN"
