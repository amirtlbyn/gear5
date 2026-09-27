#!/usr/bin/env bash
# Layout of the main keyboard (the one you type on), not the first device in the list.
# The bar starts this once: it prints the layout, then again only when it changes,
# following Hyprland's event socket instead of asking every second.
sock="$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock"

layout() {  # FA or EN. Fails when Hyprland can't be asked (e.g. while it restarts).
  local keymap
  keymap=$(hyprctl devices -j 2>/dev/null | jq -er '[.keyboards[] | select(.main)][0].active_keymap // ""' 2>/dev/null) || return 1
  [[ ${keymap,,} == *persian* ]] && echo FA || echo EN
}

last=""
emit() {
  local now
  now=$(layout) || return
  [[ "$now" == "$last" ]] && return
  echo "$now"
  last=$now
}

emit
while :; do
  while read -r event; do
    [[ "$event" == activelayout\>\>* ]] && emit
  done < <(socat -U - "UNIX-CONNECT:$sock" 2>/dev/null)
  sleep 1   # the socket closed: connect again
  emit
done
