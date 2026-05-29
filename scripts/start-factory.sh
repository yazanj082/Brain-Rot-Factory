#!/usr/bin/env bash
# Start Brain-Rot Factory: Ollama + VOD watcher + Control Panel (not the game recorder).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OPEN_DASHBOARD="${BRF_OPEN_DASHBOARD:-1}"

notify() {
  if command -v notify-send &>/dev/null; then
    notify-send -i video-x-generic "Brain-Rot Factory" "$1"
  fi
}

start_ollama() {
  if systemctl --user is-active ollama.service &>/dev/null; then
    echo "Ollama already running"
    return 0
  fi
  if systemctl --user start ollama.service 2>/dev/null; then
    echo "Started ollama.service"
    return 0
  fi
  if systemctl --user start ollama 2>/dev/null; then
    echo "Started ollama"
    return 0
  fi
  if pgrep -x ollama &>/dev/null; then
    echo "Ollama process already running"
    return 0
  fi
  echo "Starting ollama serve in background..."
  nohup ollama serve >>"$HOME/.local/log/ollama-serve.log" 2>&1 &
  sleep 2
}

wait_for_ollama() {
  local i
  for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
      echo "Ollama ready"
      return 0
    fi
    sleep 1
  done
  echo "Warning: Ollama did not respond within 30s — scoring may queue until it is up" >&2
  return 1
}

systemctl --user daemon-reload 2>/dev/null || true

start_ollama
wait_for_ollama || true

systemctl --user start vod-watcher.service review-dashboard.service

if [[ "$OPEN_DASHBOARD" == "1" ]] && command -v xdg-open &>/dev/null; then
  xdg-open "http://localhost:8069" 2>/dev/null || true
fi

notify "Factory running.\nControl Panel: http://localhost:8069\nUse Start Gaming Session when ready to record."
echo "Brain-Rot Factory started (recorder not started — use Control Panel when gaming)."
