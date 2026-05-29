"""
Brain-Rot Shorts Factory — Manual clip approve/reject and file moves
"""

import logging
import shutil
from pathlib import Path

import config
import clip_db

log = logging.getLogger(__name__)


def resolve_clip_path(filename: str) -> Path | None:
    """Find clip file in output or rejected folder."""
    for base in (config.OUTPUT_DIR, config.REJECTED_DIR):
        p = base / filename
        if p.is_file():
            return p
    return None


def move_to_rejected(short_path: Path) -> Path:
    """Move mp4 to rejected folder and update DB file_path."""
    config.REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.REJECTED_DIR / short_path.name
    if short_path.resolve() != dest.resolve():
        if dest.exists():
            dest.unlink()
        shutil.move(str(short_path), str(dest))
    clip = clip_db.get_clip_by_path(short_path)
    if clip:
        clip_db.update_clip(clip["id"], file_path=str(dest))
    return dest


def move_to_output(short_path: Path) -> Path:
    """Move mp4 back to ProcessedShorts and update DB file_path."""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.OUTPUT_DIR / short_path.name
    if short_path.resolve() != dest.resolve():
        if dest.exists():
            dest.unlink()
        shutil.move(str(short_path), str(dest))
    clip = clip_db.get_clip_by_path(short_path)
    if clip:
        clip_db.update_clip(clip["id"], file_path=str(dest))
    return dest


def manual_reject(filename: str, reason: str | None = None) -> dict:
    path = resolve_clip_path(filename)
    if not path:
        return {"ok": False, "error": "File not found"}

    clip = clip_db.get_clip_by_path(path)
    if not clip:
        return {"ok": False, "error": "Clip not in database"}

    msg = reason.strip() if reason else "Rejected from dashboard"
    reject_reason = f"Manual: {msg}" if not msg.startswith("Manual:") else msg

    move_to_rejected(path)
    clip_db.update_clip(
        clip["id"],
        status="rejected",
        reject_reason=reject_reason,
        manual_override=1,
    )
    log.info("Manually rejected clip %s: %s", clip["id"], reject_reason)
    return {"ok": True, "status": "rejected", "reject_reason": reject_reason}


def manual_approve(filename: str) -> dict:
    path = resolve_clip_path(filename)
    if not path:
        return {"ok": False, "error": "File not found"}

    clip = clip_db.get_clip_by_path(path)
    if not clip:
        return {"ok": False, "error": "Clip not in database"}

    move_to_output(path)
    clip_db.update_clip(
        clip["id"],
        status="scored",
        reject_reason=None,
        manual_override=1,
    )
    if not clip.get("description"):
        try:
            from clip_scorer import _generate_metadata_async

            _generate_metadata_async(
                clip["id"],
                clip.get("summary") or "Gameplay highlight",
                float(clip.get("hype_score") or 5),
            )
        except Exception as exc:
            log.warning("Could not queue metadata for clip %s: %s", clip["id"], exc)
    log.info("Manually approved clip %s", clip["id"])
    return {"ok": True, "status": "scored"}
