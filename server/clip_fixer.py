"""
Brain-Rot Shorts Factory — Trim replay/death segments from clips
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

import config
import clip_db
from frame_extractor import get_video_duration

log = logging.getLogger(__name__)


def apply_trim(clip: dict) -> Optional[Path]:
    """
    Trim clip based on trim_start_sec / trim_end_sec in DB record.
    Returns path to fixed file, or original path if no trim needed.
    """
    video_path = Path(clip["file_path"])
    if not video_path.exists():
        log.error("Clip file missing: %s", video_path)
        return None

    trim_start = float(clip.get("trim_start_sec") or 0)
    trim_end = float(clip.get("trim_end_sec") or 0)

    if trim_start <= 0 and trim_end <= 0:
        return video_path

    duration = get_video_duration(video_path)
    new_duration = duration - trim_start - trim_end
    if new_duration < 10:
        log.warning("Trim would leave clip too short (%.1fs) — rejecting", new_duration)
        clip_db.update_clip(
            clip["id"],
            status="rejected",
            reject_reason="Too much replay/death footage to trim",
        )
        return None

    fixed_name = video_path.stem + "_fixed.mp4"
    fixed_path = video_path.parent / fixed_name

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(trim_start),
        "-i", str(video_path),
        "-t", str(new_duration),
        "-c:v", "libx264",
        "-preset", config.PRESET,
        "-crf", str(config.CRF),
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(fixed_path),
    ]
    log.info("Trimming clip %s: start=%.1fs end=%.1fs", video_path.name, trim_start, trim_end)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("Trim failed: %s", result.stderr[-400:])
        return video_path

    clip_db.update_clip(
        clip["id"],
        file_path=str(fixed_path),
        trim_start_sec=0,
        trim_end_sec=0,
    )
    log.info("Fixed clip saved: %s", fixed_path.name)
    return fixed_path


def fix_clip_by_id(clip_id: int) -> Optional[Path]:
    clip = clip_db.get_clip(clip_id)
    if not clip:
        return None
    return apply_trim(clip)
