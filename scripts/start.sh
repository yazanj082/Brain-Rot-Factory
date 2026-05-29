#!/usr/bin/env bash
# Deprecated wrapper — use start-factory.sh or the desktop shortcut.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/start-factory.sh" "$@"
