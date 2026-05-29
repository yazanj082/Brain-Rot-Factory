"""
Brain-Rot Shorts Factory — Highlight Detector
Finds high-action moments in gameplay VODs via audio amplitude spike analysis.
"""

import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np
import scipy.io.wavfile as wav

import config

log = logging.getLogger(__name__)


def wait_for_stable_file(path: Path) -> bool:
    """Block until the file size stops changing (Syncthing finished writing)."""
    prev_size = -1
    stable_count = 0
    while stable_count < config.FILE_STABLE_CHECKS:
        try:
            current_size = path.stat().st_size
        except FileNotFoundError:
            log.warning("File disappeared while waiting: %s", path)
            return False
        if current_size == prev_size and current_size > 0:
            stable_count += 1
        else:
            stable_count = 0
        prev_size = current_size
        time.sleep(config.FILE_STABLE_INTERVAL)
    log.info("File is stable at %d bytes: %s", prev_size, path)
    return True


def _extract_audio(video_path: Path, out_wav: Path) -> bool:
    """Extract mono 16 kHz WAV audio from a video file using FFmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",                # no video
        "-ac", "1",           # mono
        "-ar", "16000",       # 16 kHz sample rate
        "-f", "wav",
        str(out_wav),
    ]
    log.info("Extracting audio: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("FFmpeg audio extraction failed:\n%s", result.stderr[-500:])
        return False
    return True


HighlightSpike = Tuple[int, float]


def detect_highlights(video_path: Path) -> List[HighlightSpike]:
    """
    Analyze the audio track of *video_path* and return highlight spikes as
    (timestamp_sec, peak_ratio) where peak_ratio = window_energy / mean_energy.

    Returns at most TOP_N_SPIKES entries, each separated by at least
    SPIKE_MIN_DISTANCE_SEC seconds.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
        tmp_wav = Path(tmp.name)

    # Extract audio to temp file
    if not _extract_audio(video_path, tmp_wav):
        return []

    try:
        sample_rate, data = wav.read(str(tmp_wav))
    except Exception as exc:
        log.error("Failed to read extracted WAV: %s", exc)
        return []
    finally:
        tmp_wav.unlink(missing_ok=True)

    if data.size == 0:
        log.warning("Extracted audio is empty for %s", video_path)
        return []

    # Normalise to float so int16 / int32 don't cause overflow
    data = data.astype(np.float64)
    amplitudes = np.abs(data)

    # Sliding-window RMS energy (non-overlapping windows)
    window_samples = sample_rate * config.AUDIO_WINDOW_SEC
    num_windows = len(amplitudes) // window_samples
    if num_windows == 0:
        log.warning("Video too short for analysis: %s", video_path)
        return []

    # Trim to exact multiple and reshape for vectorised mean
    trimmed = amplitudes[: num_windows * window_samples]
    energy = trimmed.reshape(num_windows, window_samples).mean(axis=1)

    mean_energy = energy.mean()
    threshold = mean_energy * config.MIN_SPIKE_THRESHOLD
    log.info(
        "Audio stats — windows: %d, mean energy: %.1f, threshold: %.1f",
        num_windows, mean_energy, threshold,
    )

    # Rank windows by energy, pick top spikes that are far enough apart
    ranked_indices = np.argsort(energy)[::-1]  # descending
    selected: List[HighlightSpike] = []
    selected_ts: List[int] = []

    for idx in ranked_indices:
        if energy[idx] < threshold:
            break
        ts = int(idx * config.AUDIO_WINDOW_SEC)
        ratio = float(energy[idx] / mean_energy) if mean_energy > 0 else 1.0
        if all(abs(ts - s) >= config.SPIKE_MIN_DISTANCE_SEC for s in selected_ts):
            selected.append((ts, ratio))
            selected_ts.append(ts)
        if len(selected) >= config.TOP_N_SPIKES:
            break

    selected.sort(key=lambda x: x[0])
    log.info(
        "Detected %d highlight(s): %s",
        len(selected),
        [(t, f"{r:.2f}x") for t, r in selected],
    )
    return selected


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python highlight_detector.py <video.mp4>")
        sys.exit(1)
    highlights = detect_highlights(Path(sys.argv[1]))
    for ts, ratio in highlights:
        m, s = divmod(ts, 60)
        print(f"  ⚡ Highlight at {m}m{s:02d}s (t={ts}s, peak={ratio:.2f}x)")
