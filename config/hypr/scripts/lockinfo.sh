#!/usr/bin/env bash
# The lock screen's status line (hyprlock runs it every 5 s): the battery and what
# is playing, e.g. "󰂀 72%   ♪ Artist — Title". A part is left out when there is
# nothing to show. It always prints one line and exits 0, so hyprlock never shows
# an error (spec LOCK).
#   LOCKINFO_POWER=DIR   read the batteries from DIR, not /sys/class/power_supply (tests)
shopt -u patsub_replacement 2>/dev/null   # a "&" in a replacement stays a "&"
power=${LOCKINFO_POWER:-/sys/class/power_supply}
parts=()

for bat in "$power"/BAT*; do
  [[ -r "$bat/capacity" ]] || continue
  cap=$(<"$bat/capacity")
  [[ "$cap" =~ ^[0-9]+$ ]] || continue
  status=$(cat "$bat/status" 2>/dev/null)
  if [[ "$status" == Charging ]]; then
    icon=󰂄
  else
    icons=(󰂎 󰁺 󰁻 󰁼 󰁽 󰁾 󰁿 󰂀 󰂁 󰂂 󰁹)
    i=$((cap / 10)); ((i > 10)) && i=10
    icon=${icons[$i]}
  fi
  parts+=("$icon $cap%")
  break
done

if command -v playerctl >/dev/null 2>&1; then
  state=$(timeout 1 playerctl status 2>/dev/null)
  if [[ "$state" == Playing || "$state" == Paused ]]; then
    now=$(timeout 1 playerctl metadata --format '{{artist}}	{{title}}' 2>/dev/null)
    artist=${now%%	*}
    title=${now#*	}
    if [[ -n "$title" ]]; then
      text=${artist:+$artist — }$title
      ((${#text} > 60)) && text="${text:0:59}…"
      # the label is Pango markup: these three would break it
      text=${text//&/&amp;}; text=${text//</&lt;}; text=${text//>/&gt;}
      parts+=("♪ $text")
    fi
  fi
fi

out=""
for p in "${parts[@]}"; do out+="${out:+   }$p"; done
echo "$out"
exit 0
