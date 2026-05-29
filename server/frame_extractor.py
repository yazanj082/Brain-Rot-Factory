"""
Brain-Rot Shorts Factory — Frame extraction for vision scoring
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List

import config

log = logging.getLogger(__name__)


def get_video_duration(video_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return float(config.CLIP_DURATION)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return float(config.CLIP_DURATION)


def extract_frames(video_path: Path, count: int | None = None) -> List[Path]:
    """
    Extract evenly spaced JPEG frames from a short clip.
    Returns list of paths to temporary JPEG files.
    """
    count = count or config.SCORE_FRAMES
    duration = get_video_duration(video_path)
    if duration <= 0:
        duration = float(config.CLIP_DURATION)

    out_dir = Path(tempfile.mkdtemp(prefix="brf_frames_"))
    # fps filter: count frames spread across duration (avoid t=0 only)
    interval = max(duration / (count + 1), 0.5)
    fps_val = 1.0 / interval

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"fps={fps_val}",
        "-frames:v", str(count),
        "-q:v", "3",
        str(out_dir / "frame_%03d.jpg"),
    ]
    log.debug("Extracting %d frames: %s", count, video_path.name)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("Frame extraction failed: %s", result.stderr[-400:])
        return []

    frames = sorted(out_dir.glob("frame_*.jpg"))
    if len(frames) < count:
        # Fallback: extract at explicit timestamps
        frames = []
        for i in range(count):
            t = (i + 1) * duration / (count + 1)
            out = out_dir / f"frame_{i:03d}.jpg"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", str(t), "-i", str(video_path),
                    "-frames:v", "1", "-q:v", "3", str(out),
                ],
                capture_output=True,
            )
            if out.exists():
                frames.append(out)

    log.info("Extracted %d frames from %s", len(frames), video_path.name)
    return frames


def prepare_vision_frames(frames: List[Path]) -> List[Path]:
    """
    Resize and limit frames before sending to Ollama.
    Large multi-image payloads cause qwen2.5vl to hang on 8GB GPUs.
    """
    if not frames:
        return []

    try:
        from PIL import Image
    except ImportError:
        return frames[: config.VISION_MAX_IMAGES]

    max_w = config.VISION_FRAME_WIDTH
    max_n = config.VISION_MAX_IMAGES
    # Prefer middle frame(s) — most representative
    if len(frames) > max_n:
        mid = len(frames) // 2
        start = max(0, mid - max_n // 2)
        selected = frames[start : start + max_n]
    else:
        selected = frames[:max_n]

    out: List[Path] = []
    out_dir = selected[0].parent
    for i, src in enumerate(selected):
        try:
            img = Image.open(src)
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize((max_w, max(1, int(img.height * ratio))), Image.Resampling.LANCZOS)
            dest = out_dir / f"vision_{i:02d}.jpg"
            img.convert("RGB").save(dest, "JPEG", quality=75, optimize=True)
            out.append(dest)
        except Exception as exc:
            log.warning("Could not resize frame %s: %s", src.name, exc)
            out.append(src)
    log.info("Prepared %d vision frame(s) (max width %dpx)", len(out), max_w)
    return out


def compute_phash(frame_path: Path) -> str | None:
    """Perceptual hash of a single frame for deduplication."""
    try:
        import imagehash
        from PIL import Image
        img = Image.open(frame_path)
        return str(imagehash.phash(img))
    except Exception as exc:
        log.warning("phash failed for %s: %s", frame_path, exc)
        return None


def phash_from_video(video_path: Path) -> str | None:
    """Hash middle frame of clip for dedup."""
    duration = get_video_duration(video_path)
    mid = max(0.5, duration / 2)
    out_dir = Path(tempfile.mkdtemp(prefix="brf_phash_"))
    out = out_dir / "mid.jpg"
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(mid), "-i", str(video_path),
            "-frames:v", "1", "-q:v", "3", str(out),
        ],
        capture_output=True,
    )
    if not out.exists():
        return None
    return compute_phash(out)
