#!/usr/bin/env bash
# Start gameplay recording with Wayland portal picker (choose monitor or window).
# Must run in your graphical session so the KDE/Wayland share dialog appears.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$ROOT/.venv"

UID_NUM="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$UID_NUM}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
export XDG_SESSION_TYPE="${XDG_SESSION_TYPE:-wayland}"
export XDG_CURRENT_DESKTOP="${XDG_CURRENT_DESKTOP:-KDE}"

# Dashboard settings.json, then env BRF_* overrides
RECORD_FPS="30"
RECORD_QUALITY="high"
if [[ -x "$VENV/bin/python3" ]]; then
  while IFS='=' read -r key val; do
    [[ -n "$key" ]] || continue
    case "$key" in
      RECORD_FPS) RECORD_FPS="$val" ;;
      RECORD_QUALITY) RECORD_QUALITY="$val" ;;
    esac
  done < <("$VENV/bin/python3" -c "
import sys
sys.path.insert(0, '$ROOT/server')
from settings import load_settings
s = load_settings()
print('RECORD_FPS=' + str(int(s.get('record_fps', 30))))
print('RECORD_QUALITY=' + str(s.get('record_quality', 'high')))
")
fi
RECORD_FPS="${BRF_RECORD_FPS:-$RECORD_FPS}"
RECORD_QUALITY="${BRF_RECORD_QUALITY:-$RECORD_QUALITY}"

TOKEN_DIR="$HOME/.config/gpu-screen-recorder"
mkdir -p "$TOKEN_DIR"

# Force the portal picker every session (don't reuse old screen/window choice)
rm -f "$TOKEN_DIR/portal-session-token"

OUTPUT_DIR="$HOME/Videos/RawGameplay"
mkdir -p "$OUTPUT_DIR"

notify-send -i video-x-generic "Brain-Rot Factory" \
    "Pick what to record in the dialog (your game window or screen)." 2>/dev/null || true

exec gpu-screen-recorder \
    -w portal \
    -restore-portal-session no \
    -f "$RECORD_FPS" \
    -k hevc \
    -q "$RECORD_QUALITY" \
    -a default_output \
    -o "${OUTPUT_DIR}/gameplay_$(date +%Y-%m-%d_%H-%M-%S).mp4"
