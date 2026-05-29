"""
Brain-Rot Shorts Factory — FFmpeg Processing Engine
Takes a gameplay VOD + timestamp → outputs a vertical, deep-fried, music-overlaid Short.
"""

import logging
import os
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Title generation pool
# ──────────────────────────────────────────────
TITLE_TEMPLATES = [
    "HE WASN'T READY 💀🔥 #shorts #gaming",
    "Insane Outplay! 🔥 #shorts #gaming #overwatch",
    "They called me a hacker after this... 😱 #shorts",
    "This clip is ILLEGAL 🚨🔥 #shorts #gaming",
    "The lobby went SILENT 💀 #shorts #gaming",
    "POV: You hit the play of your life 🎯 #shorts",
    "How did I survive this?! 😳 #shorts #gaming",
    "That aim is NOT human 🤖🔥 #shorts",
    "Deleted from existence 💀 #shorts #gaming",
    "They rage quit after this 😂🔥 #shorts",
    "POTG material right here 🏆 #shorts #gaming",
    "When everything just CLICKS 🎯💥 #shorts",
    "Built different 💪🔥 #shorts #gaming",
    "One clip, zero mercy 😈 #shorts #gaming",
    "Calculated. 🧠 #shorts #gaming #overwatch",
]


def generate_title() -> str:
    """Pick a random brain-rot title from the pool."""
    return random.choice(TITLE_TEMPLATES)


def _pick_bg_music() -> Optional[Path]:
    """Select a random background track from the audio pool."""
    pool = config.AUDIO_POOL_DIR
    if not pool.exists():
        log.warning("Audio pool directory does not exist: %s", pool)
        return None
    tracks = [f for f in pool.iterdir() if f.suffix in (".mp3", ".ogg", ".wav", ".m4a", ".flac")]
    if not tracks:
        log.warning("No audio tracks found in %s", pool)
        return None
    choice = random.choice(tracks)
    log.info("Selected background track: %s", choice.name)
    return choice


def generate_short(video_path: Path, target_time: int) -> Optional[Path]:
    """
    Extract a clip centred on *target_time*, convert to 9:16 vertical,
    deep-fry the colour grading, mix in background music, and write
    the final Short to OUTPUT_DIR.

    Returns the output file path on success, None on failure.
    """
    start_time = max(0, target_time - config.CLIP_PRE_OFFSET)
    duration = config.CLIP_DURATION

    timestamp_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_name = f"short_{timestamp_tag}_t{target_time}s.mp4"
    output_path = config.OUTPUT_DIR / output_name

    bg_music = _pick_bg_music()

    # ── Build the FFmpeg command ──────────────────────────────
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", str(video_path),
    ]

    # Optionally add background music input
    if bg_music:
        cmd += ["-i", str(bg_music)]

    cmd += ["-t", str(duration)]

    # Video filter: centre-crop to 9:16 + deep-fry colour
    vf = (
        f"crop=ih*(9/16):ih,"
        f"eq=saturation={config.SATURATION}:contrast={config.CONTRAST}"
    )
    cmd += ["-vf", vf]

    # Audio filter: mix game audio + bg music (if available)
    if bg_music:
        af = (
            f"[0:a]volume=1.0[a1];"
            f"[1:a]volume={config.BG_MUSIC_VOLUME}[a2];"
            f"[a1][a2]amix=inputs=2:duration=first[aout]"
        )
        cmd += ["-filter_complex", af, "-map", "0:v", "-map", "[aout]"]
    else:
        cmd += ["-map", "0:v", "-map", "0:a"]

    # Encoding settings
    cmd += [
        "-c:v", "libx264",
        "-preset", config.PRESET,
        "-crf", str(config.CRF),
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    log.info("🎬 Generating short: %s", output_name)
    log.debug("FFmpeg command: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("FFmpeg failed (exit %d):\n%s", result.returncode, result.stderr[-800:])
        return None

    size_mb = output_path.stat().st_size / (1024 * 1024)
    log.info("✅ Short ready: %s (%.1f MB)", output_path, size_mb)
    return output_path


# ──────────────────────────────────────────────
# Standalone usage
# ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    if len(sys.argv) < 3:
        print("Usage: python brain_rot_factory.py <video.mp4> <timestamp_seconds>")
        sys.exit(1)

    result = generate_short(Path(sys.argv[1]), int(sys.argv[2]))
    if result:
        print(f"\n🔥 Output: {result}")
    else:
        print("\n❌ Processing failed.")
        sys.exit(1)
