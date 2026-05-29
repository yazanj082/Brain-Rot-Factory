"""
Brain-Rot Shorts Factory — Delete all local VODs and clips to free disk space.
Preserves OAuth secrets, settings, and background music pool.
"""

import logging
from pathlib import Path

import config
import clip_db

log = logging.getLogger(__name__)

MEDIA_SUFFIXES = {
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv", ".ts", ".part",
}


def _delete_media_files(root: Path, *, include_subdirs: bool = True) -> tuple[int, int]:
    """Remove video files under root. Returns (file_count, bytes_freed)."""
    if not root.exists():
        return 0, 0
    count = 0
    freed = 0
    iterator = root.rglob("*") if include_subdirs else root.iterdir()
    for path in iterator:
        if not path.is_file():
            continue
        if path.suffix.lower() not in MEDIA_SUFFIXES:
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            count += 1
            freed += size
            log.info("Deleted %s", path)
        except OSError as exc:
            log.warning("Could not delete %s: %s", path, exc)
    return count, freed


def cleanup_all_local_media() -> dict:
    """
    Delete raw VODs, processed archives, all shorts (scored/rejected/uploaded),
    and clear the clip registry. Does not remove OAuth, settings, or music pool.
    """
    total_files = 0
    total_bytes = 0

    for directory in (config.WATCH_DIR, config.OUTPUT_DIR):
        n, b = _delete_media_files(directory, include_subdirs=True)
        total_files += n
        total_bytes += b

    cleared = clip_db.clear_all_clip_records()

    return {
        "ok": True,
        "files_deleted": total_files,
        "bytes_freed": total_bytes,
        "mb_freed": round(total_bytes / (1024 * 1024), 1),
        "db_rows_cleared": cleared,
        "kept": [
            str(config.SECRETS_FILE.parent),
            "settings.json",
            "audio_tracks/",
        ],
    }
