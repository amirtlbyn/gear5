#!/usr/bin/env bash
# Keeps Waybar running. Screens coming and going (unplugging, lid, waking up) can
# make Waybar quit; this starts it again a moment later.
#   bar.sh           (re)start the bar; replaces an older bar.sh
# Colors come from ~/.config/waybar/colors/current.css (see waybar/scripts/theme.py).
# Waybar's messages go to $XDG_RUNTIME_DIR/waybar.log.
RUN="${XDG_RUNTIME_DIR:-/tmp}"
KEEPER="$RUN/bar-keeper.pid"
LOG="$RUN/waybar.log"

# stop the previous keeper first, so it doesn't restart the bar we are replacing
if [[ -r "$KEEPER" ]]; then
  old=$(<"$KEEPER")
  [[ "$old" != "$$" ]] && kill "$old" 2>/dev/null
fi
echo $$ > "$KEEPER"
pkill -x waybar
trap 'kill "$child" 2>/dev/null; exit 0' TERM INT

# keep the log short: the last 300 lines of earlier runs
[[ -f "$LOG" ]] && tail -n 300 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"

while [[ "$(cat "$KEEPER" 2>/dev/null)" == "$$" ]]; do
  echo "--- $(date '+%F %T') starting waybar" >> "$LOG"
  waybar -c ~/.config/waybar/bar/config -s ~/.config/waybar/bar/style.css >> "$LOG" 2>&1 &
  child=$!
  wait "$child"
  rc=$?
  echo "--- $(date '+%F %T') waybar exited ($rc)" >> "$LOG"
  sleep 1
done
