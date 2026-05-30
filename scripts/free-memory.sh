#!/usr/bin/env bash
# Stop factory leftovers, show memory, optionally reclaim swap (safe checks only).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIN_AVAIL_KB_FOR_SWAP="${BRF_MIN_AVAIL_KB_FOR_SWAP:-$((4 * 1024 * 1024))}"
DO_SWAP=false
DO_DROP_CACHES=false

usage() {
  cat <<'EOF'
Usage: free-memory.sh [options]

Stops Brain-Rot services and stray processes, then prints memory/swap status.

Options:
  --swap         Try to clear swap (sudo swapoff/swapon). Requires ~4 GB MemAvailable.
  --drop-caches  Drop Linux file caches (sudo). Minor help; needs root.
  -h, --help     Show this help.

Swap often stays full after Stop Factory until you close games or reboot — that is normal.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --swap) DO_SWAP=true; shift ;;
    --drop-caches) DO_DROP_CACHES=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

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

print_memory() {
  echo ""
  echo "── Memory (free -h) ──"
  free -h
  local avail_kb pct
  avail_kb=$(mem_available_kb)
  pct=$(swap_used_percent)
  echo ""
  echo "MemAvailable: $((avail_kb / 1024)) MB"
  if [[ "$pct" -ge 80 ]]; then
    echo "WARNING: Swap is ${pct}% full. Stopping the factory does not empty swap."
    echo "  → Quit Overwatch/heavy apps, reboot, or run: $0 --swap (only if MemAvailable is high enough)"
  fi
}

kill_leftovers() {
  pkill -f gpu-screen-recorder 2>/dev/null || true
  pkill -f vod_watcher 2>/dev/null || true
  pkill -f review_dashboard 2>/dev/null || true
  pkill -x ollama 2>/dev/null || true
  pkill -f 'ffmpeg.*RawGameplay' 2>/dev/null || true
}

echo "Brain-Rot — free memory helper"
print_memory

echo ""
echo "Stopping factory services..."
"$SCRIPT_DIR/stop-factory.sh" 2>/dev/null || true
kill_leftovers
sleep 1

if [[ "$DO_DROP_CACHES" == true ]]; then
  echo ""
  echo "Dropping file caches (sudo)..."
  sync
  sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
fi

if [[ "$DO_SWAP" == true ]]; then
  avail_kb=$(mem_available_kb)
  if [[ "$avail_kb" -lt "$MIN_AVAIL_KB_FOR_SWAP" ]]; then
    echo ""
    echo "ERROR: MemAvailable is only $((avail_kb / 1024)) MB."
    echo "Need at least $((MIN_AVAIL_KB_FOR_SWAP / 1024 / 1024)) GB before clearing swap."
    echo "Close Overwatch and other heavy apps first, or reboot."
    exit 1
  fi
  echo ""
  echo "Clearing swap (sudo swapoff/swapon)..."
  sync
  sudo swapoff -a && sudo swapon -a
fi

echo ""
echo "After cleanup:"
print_memory
echo ""
echo "Note: Swap can stay full until you close games or reboot — this is normal Linux behavior."
