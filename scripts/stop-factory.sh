#!/usr/bin/env bash
# Stop Brain-Rot Factory completely: recorder, watcher, dashboard, and optionally Ollama.
set -euo pipefail

STOP_OLLAMA="${BRF_STOP_OLLAMA:-1}"

notify() {
  if command -v notify-send &>/dev/null; then
    notify-send -i process-stop "Brain-Rot Factory" "$1"
  fi
}

mem_available_kb() {
  awk '/^MemAvailable:/ { print $2; exit }' /proc/meminfo 2>/dev/null || echo 0
}

swap_used_percent() {
  local total free used
  total=$(awk '/^SwapTotal:/ { print $2; exit }' /proc/meminfo 2>/dev/null || echo 0)
  free=$(awk '/^SwapFree:/ { print $2; exit }' /proc/meminfo 2>/dev/null || echo 0)
  if [[ "$total" -le 0 ]]; then
    echo 0
    return
  fi
  used=$((total - free))
  echo $((used * 100 / total))
}

kill_leftovers() {
  pkill -f gpu-screen-recorder 2>/dev/null || true
  pkill -f vod_watcher 2>/dev/null || true
  pkill -f review_dashboard 2>/dev/null || true
  pkill -f 'ffmpeg.*RawGameplay' 2>/dev/null || true
}

print_memory_status() {
  echo ""
  free -h
  local pct avail_kb
  pct=$(swap_used_percent)
  avail_kb=$(mem_available_kb)
  if [[ "$pct" -ge 80 ]]; then
    echo ""
    echo "WARNING: Swap is ${pct}% full (${avail_kb} kB MemAvailable)."
    echo "Stopping the factory does not empty swap. Quit Overwatch/heavy apps, reboot,"
    echo "or run: $(dirname "$0")/free-memory.sh --swap (only if enough free RAM)."
  fi
}

echo "Stopping Brain-Rot Factory services..."

systemctl --user stop game-recorder.service 2>/dev/null || true
systemctl --user stop vod-watcher.service review-dashboard.service 2>/dev/null || true

if [[ "$STOP_OLLAMA" == "1" ]]; then
  systemctl --user stop ollama.service 2>/dev/null || true
  systemctl --user stop ollama 2>/dev/null || true
  if pgrep -x ollama &>/dev/null; then
    echo "Stopping ollama process..."
    pkill -x ollama 2>/dev/null || true
    sleep 1
  fi
else
  echo "BRF_STOP_OLLAMA=0 — leaving Ollama running"
fi

kill_leftovers

notify "Factory stopped. All services and Ollama are off."
echo "Brain-Rot Factory stopped."
print_memory_status
