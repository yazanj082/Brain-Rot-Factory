"""
Brain-Rot Shorts Factory — Daily best-clip uploader
"""

import logging
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Optional

import config
import clip_db
from clip_fixer import apply_trim
from clip_scorer import score_pending_clips
from metadata_generator import generate_metadata
from settings import already_uploaded_today, get_min_hype_score, mark_auto_upload_done
from yt_uploader import upload_to_youtube

log = logging.getLogger(__name__)


def run_daily_upload(force: bool = False) -> dict[str, Any]:
    """
    Pick best scored clip, fix, generate metadata, upload.

    Args:
        force: Skip once-per-day guard (for manual testing).

    Returns dict with success, video_id, clip_id, error.
    """
    if not force and already_uploaded_today():
        log.info("Already uploaded today — skipping scheduled run")
        return {"success": False, "error": "Already uploaded today", "skipped": True}

    score_pending_clips()

    min_hype = get_min_hype_score()
    clip = clip_db.get_best_scored(min_hype)
    if not clip:
        log.info("No eligible clips in queue (min hype %.1f)", min_hype)
        return {"success": False, "error": "No clips ready to upload"}

    clip_id = clip["id"]
    log.info("Selected clip %s (hype=%.1f): %s", clip_id, clip.get("hype_score", 0), clip.get("file_path"))

    fixed_path = apply_trim(clip)
    if fixed_path is None:
        return {"success": False, "error": "Clip could not be fixed", "clip_id": clip_id}

    clip = clip_db.get_clip(clip_id) or clip
    summary = clip.get("summary") or ""
    hype = float(clip.get("hype_score") or 0)
    meta = generate_metadata(summary, hype)

    clip_db.update_clip(
        clip_id,
        title=meta["title"],
        description=meta["description"],
        tags=meta["tags"],
        status="queued",
    )

    video_path = Path(clip.get("file_path", fixed_path))
    if not video_path.exists():
        video_path = fixed_path

    video_id = upload_to_youtube(
        video_path,
        title=meta["title"],
        description=meta["description"],
        tags=meta["tags"],
        clip_id=clip_id,
    )

    if not video_id:
        clip_db.update_clip(clip_id, status="scored")
        return {"success": False, "error": "YouTube upload failed", "clip_id": clip_id}

    config.UPLOADED_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.UPLOADED_DIR / video_path.name
    try:
        if video_path.exists() and video_path.parent != config.UPLOADED_DIR:
            shutil.move(str(video_path), str(dest))
            clip_db.update_clip(clip_id, file_path=str(dest))
    except OSError as exc:
        log.warning("Could not move uploaded file: %s", exc)

    if not force:
        mark_auto_upload_done()

    url = f"https://youtube.com/shorts/{video_id}"
    _notify(f"Uploaded best clip!\n{meta['title']}\n{url}")

    log.info("Daily upload complete: %s", url)
    return {
        "success": True,
        "video_id": video_id,
        "url": url,
        "clip_id": clip_id,
        "title": meta["title"],
    }


def _notify(message: str) -> None:
    try:
        subprocess.run(
            ["notify-send", "-i", "video-x-generic", "Brain-Rot Factory", message],
            check=False,
        )
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    force = "--force" in sys.argv
    result = run_daily_upload(force=force)
    print(result)
