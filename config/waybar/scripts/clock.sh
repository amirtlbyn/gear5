#!/usr/bin/env bash
# Bar clock with pinned timezones (edit them in the world clock popup: click the clock).
#   clock.sh            keep printing the clock for waybar (only when it changes)
#   clock.sh next|prev  show the next / previous pinned zone on the bar (mouse wheel)
#   clock.sh now +FMT   print `date +FMT` in the zone the bar shows (the lock screen)
STATE=~/.config/waybar/clock-zones.json
LOCAL=$(readlink -f /etc/localtime | sed 's|.*/zoneinfo/||')

city() {  # Asia/Tehran → Tehran, America/New_York → New York
  local z=$1; [[ $z == local ]] && z=$LOCAL
  z=${z##*/}; echo "${z//_/ }"
}

zone_shown() {  # the zone the bar shows: the active pinned one, "local" = the system's
  local z; z=$(jq -r '.active // "local"' "$STATE" 2>/dev/null || echo local)
  [[ $z == local || -z $z ]] && z=$LOCAL; echo "$z"
}

if [[ "$1" == now ]]; then
  TZ=$(zone_shown) date "$2"
  exit
fi

if [[ "$1" == next || "$1" == prev ]]; then
  step=1; [[ "$1" == prev ]] && step=-1
  tmp=$(mktemp)
  jq --argjson s "$step" '(.active // "local") as $a | .pinned as $p | (($p | index($a)) // 0) as $i
      | .active = $p[(($i + $s) % ($p | length) + ($p | length)) % ($p | length)]' "$STATE" > "$tmp" \
    && mv "$tmp" "$STATE"
  exit
fi

emit() {
  local active zone text tip=""
  active=$(jq -r '.active // "local"' "$STATE" 2>/dev/null || echo local)
  zone=$active; [[ $zone == local ]] && zone=$LOCAL
  text=" $(TZ=$zone date +%H:%M)"
  # the full dates (Gregorian + Jalali) from the date pill's script, above the zones
  tip="$(python3 "$(dirname "$0")/dates.py" | jq -r .tooltip)"$'\n'
  while read -r z; do
    local tz=$z; [[ $tz == local ]] && tz=$LOCAL
    tip+=$(printf '%-14s %s' "$(city "$z")" "$(TZ=$tz date '+%H:%M  %a')")$'\n'
  done < <(jq -r '.pinned[]' "$STATE" 2>/dev/null)
  jq -cn --arg t "$text" --arg tip "${tip%$'\n'}" --arg c "$([[ $active == local ]] && echo local || echo other)" \
    '{text: $t, tooltip: $tip, class: $c}'
}

last=""
while :; do
  key="$(date +%H:%M)$(stat -c %Y "$STATE" 2>/dev/null)"
  if [[ "$key" != "$last" ]]; then emit; last=$key; fi
  sleep 1
done
