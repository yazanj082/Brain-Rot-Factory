#!/usr/bin/env bash
# Backward-compatible alias — runs the main setup script.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup.sh" "$@"
