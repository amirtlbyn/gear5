#!/usr/bin/env bash
# Volume keys with an on-screen bar (a swaync notification that replaces itself
# and is not kept in the notification center).
#   volume.sh up | down | mute | mic-mute
STEP=5
case "$1" in
  up)       wpctl set-mute @DEFAULT_AUDIO_SINK@ 0; wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ "$STEP%+" ;;
  down)     wpctl set-volume @DEFAULT_AUDIO_SINK@ "$STEP%-" ;;
  mute)     wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle ;;
  mic-mute) wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle ;;
esac

if [[ "$1" == mic-mute ]]; then
  if wpctl get-volume @DEFAULT_AUDIO_SOURCE@ | grep -q MUTED; then
    icon=microphone-sensitivity-muted; text="Microphone off"
  else
    icon=audio-input-microphone; text="Microphone on"
  fi
  notify-send -e -a Volume -t 1200 -i "$icon" \
    -h string:x-canonical-private-synchronous:osd-mic "$text"
  exit
fi

# "Volume: 0.45 [MUTED]"
read -r _ vol muted < <(wpctl get-volume @DEFAULT_AUDIO_SINK@)
pct=$(awk -v v="$vol" 'BEGIN { printf "%d", v * 100 + 0.5 }')
if [[ -n "$muted" || "$pct" -eq 0 ]]; then icon=audio-volume-muted; text="Muted"
elif (( pct < 34 )); then icon=audio-volume-low; text="$pct%"
elif (( pct < 67 )); then icon=audio-volume-medium; text="$pct%"
else icon=audio-volume-high; text="$pct%"
fi
[[ -n "$muted" ]] && pct=0
notify-send -e -a Volume -t 1200 -i "$icon" \
  -h string:x-canonical-private-synchronous:osd-volume -h "int:value:$pct" "Volume" "$text"
