#!/usr/bin/env bash
# Stop Brain-Rot Factory completely: recorder, watcher, dashboard, and optionally Ollama.
set -euo pipefail

STOP_OLLAMA="${BRF_STOP_OLLAMA:-1}"

notify() {
  if command -v notify-send &>/dev/null; then
    notify-send -i process-stop "Brain-Rot Factory" "$1"
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

notify "Factory stopped. All services and Ollama are off."
echo "Brain-Rot Factory stopped."
