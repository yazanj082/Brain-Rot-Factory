#!/usr/bin/env bash
# Legacy wrapper — delegates to start_recording.sh
exec "$(dirname "$0")/start_recording.sh"
