#!/usr/bin/env bash
# Deprecated wrapper — use stop-factory.sh or the desktop shortcut.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stop-factory.sh" "$@"
