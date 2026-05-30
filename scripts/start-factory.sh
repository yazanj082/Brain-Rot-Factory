#!/usr/bin/env bash
# Start Brain-Rot Factory: VOD watcher + Control Panel (Ollama starts after Stop Recording).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPEN_DASHBOARD="${BRF_OPEN_DASHBOARD:-1}"

notify() {
  if command -v notify-send &>/dev/null; then
    notify-send -i video-x-generic "Brain-Rot Factory" "$1"
  fi
}

systemctl --user daemon-reload 2>/dev/null || true

systemctl --user start vod-watcher.service review-dashboard.service

if [[ "$OPEN_DASHBOARD" == "1" ]] && command -v xdg-open &>/dev/null; then
  xdg-open "http://localhost:8069" 2>/dev/null || true
fi

notify "Factory running (Ollama starts after you stop recording).\nControl Panel: http://localhost:8069"
echo "Brain-Rot Factory started — Ollama is deferred until Stop Recording (saves RAM while gaming)."
