#!/usr/bin/env bash
# Re-score scored and rejected clips with current hype logic (audio spike + vision blend).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python3" ]]; then
  echo "Missing venv. Run ./setup_workstation.sh first." >&2
  exit 1
fi

export PYTHONUNBUFFERED=1
"$ROOT/.venv/bin/python3" << 'PY'
import sys
sys.path.insert(0, "server")

from clip_scorer import rescore_clips, score_all_pending, recover_orphan_clips
from ollama_client import is_ollama_available
import clip_db

if not is_ollama_available():
    print("Ollama is not running. Start the factory first (Brain-Rot Start shortcut).")
    sys.exit(1)

n = rescore_clips(("scored", "rejected"))
print(f"Queued {n} clip(s) for re-scoring...")

recover_orphan_clips()
total = score_all_pending()
print(f"Done. Re-scored {total} clip(s).")

for s in ("scored", "rejected", "pending_score"):
    print(f"  {s}: {len(clip_db.list_clips(status=s) or [])}")
PY
