#!/bin/sh
# SUPER+H: no gaps / normal gaps (values match hyprland.lua)
TOGGLE=$HOME/.toggle

if [ ! -e "$TOGGLE" ]; then
	touch "$TOGGLE"
	hyprctl eval 'hl.config({ general = { gaps_in = 0, gaps_out = 0 }, decoration = { rounding = 0 } })'
else
	rm "$TOGGLE"
	hyprctl eval 'hl.config({ general = { gaps_in = 10, gaps_out = 20 }, decoration = { rounding = 10 } })'
fi
