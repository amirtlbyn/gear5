#!/usr/bin/env bash
# Live check of SUPER+SHIFT+Escape (spec UNSTICK) on the running desktop: open the
# calculator, pause it with SIGSTOP (it keeps its layer and the keyboard), run
# `popup.sh --unstick`, and check that it is gone, a new one waits hidden, and that
# one opens. Uses the installed ~/.config/waybar/scripts/popup.sh.
#   tests/live_unstick.sh
popup=~/.config/waybar/scripts/popup.sh
marks="${XDG_RUNTIME_DIR:-/tmp}/popups"
fail=0
check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }
layer_pid() {   # the pid of the calculator's layer, or nothing
  hyprctl layers -j | jq -r '[.[].levels[][] | select(.namespace == "calculator")][0].pid // empty'
}
wait_layer() {   # wait up to 3 s for the layer to be there ($1 = yes) or gone ($1 = no)
  for _ in {1..30}; do
    if [[ $1 == yes ]]; then [[ -n $(layer_pid) ]] && return; else [[ -z $(layer_pid) ]] && return; fi
    sleep 0.1
  done
  return 1
}

"$popup" calculator
check "calculator opens" "wait_layer yes"
old=$(layer_pid)
[[ -n "$old" ]] || { echo "FAIL no calculator layer to pause"; exit 1; }
kill -STOP "$old"

began=$(date +%s%N)
"$popup" --unstick
took=$(( ($(date +%s%N) - began) / 1000000 ))
echo "     --unstick took $took ms"
check "the paused calculator is gone" "[[ ! -e /proc/$old ]] || [[ \$(awk '{print \$3}' /proc/$old/stat) == Z ]]"
check "its layer is gone" "wait_layer no"
check "its mark is gone" "[[ ! -e $marks/io.local.calculator ]]"
check "it took 2 s or less" "(( took <= 2000 ))"
sleep 1   # the new one starts hidden
new=$(pgrep -f "$HOME/.config/waybar/scripts/calculator.py .*--hidden" | head -1)
check "a new calculator waits hidden" "[[ -n '$new' && '$new' != '$old' ]]"
"$popup" calculator
check "the new calculator opens" "wait_layer yes && [[ \$(layer_pid) == '$new' ]]"
"$popup" --close-all
exit $fail
