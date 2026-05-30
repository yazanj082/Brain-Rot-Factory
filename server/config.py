"""
Brain-Rot Shorts Factory — Configuration
All settings are configurable via environment variables with sensible defaults.
"""

import os
from pathlib import Path

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
HOME = Path.home()

WATCH_DIR: Path = Path(os.getenv("BRF_WATCH_DIR", HOME / "Videos" / "RawGameplay"))
OUTPUT_DIR: Path = Path(os.getenv("BRF_OUTPUT_DIR", HOME / "Videos" / "ProcessedShorts"))
PROCESSED_DIR: Path = Path(os.getenv("BRF_PROCESSED_DIR", WATCH_DIR / "processed"))
AUDIO_POOL_DIR: Path = Path(os.getenv("BRF_AUDIO_POOL", HOME / "shorts_assets" / "audio_tracks"))
SECRETS_FILE: Path = Path(os.getenv("BRF_SECRETS_FILE", HOME / "shorts_assets" / "client_secrets.json"))
OAUTH_FILE: Path = Path(os.getenv("BRF_OAUTH_FILE", HOME / "shorts_assets" / "oauth.json"))
LOG_FILE: Path = Path(os.getenv("BRF_LOG_FILE", HOME / ".local" / "log" / "brain-rot-factory.log"))

# ──────────────────────────────────────────────
# Clip extraction
# ──────────────────────────────────────────────
CLIP_DURATION: int = int(os.getenv("BRF_CLIP_DURATION", "40"))
CLIP_PRE_OFFSET: int = int(os.getenv("BRF_CLIP_PRE_OFFSET", "15"))

# ──────────────────────────────────────────────
# Highlight detection
# ──────────────────────────────────────────────
MIN_SPIKE_THRESHOLD: float = float(os.getenv("BRF_SPIKE_THRESHOLD", "1.5"))
TOP_N_SPIKES: int = int(os.getenv("BRF_TOP_N_SPIKES", "3"))
SPIKE_MIN_DISTANCE_SEC: int = int(os.getenv("BRF_SPIKE_MIN_DISTANCE", "60"))
AUDIO_WINDOW_SEC: int = int(os.getenv("BRF_AUDIO_WINDOW", "2"))

# ──────────────────────────────────────────────
# FFmpeg "deep-fry" parameters
# ──────────────────────────────────────────────
SATURATION: float = float(os.getenv("BRF_SATURATION", "1.6"))
CONTRAST: float = float(os.getenv("BRF_CONTRAST", "1.1"))
BG_MUSIC_VOLUME: float = float(os.getenv("BRF_BG_MUSIC_VOL", "0.25"))
CRF: int = int(os.getenv("BRF_CRF", "22"))
PRESET: str = os.getenv("BRF_PRESET", "superfast")

# ──────────────────────────────────────────────
# Upload
# ──────────────────────────────────────────────
PRIVACY_STATUS: str = os.getenv("BRF_PRIVACY", "unlisted")  # unlisted for safety; change to public
CATEGORY_ID: str = "20"  # Gaming

# ──────────────────────────────────────────────
# Database & AI pipeline
# ──────────────────────────────────────────────
DB_PATH: Path = Path(os.getenv("BRF_DB_PATH", HOME / "shorts_assets" / "clips.db"))
SETTINGS_FILE: Path = Path(os.getenv("BRF_SETTINGS_FILE", HOME / "shorts_assets" / "settings.json"))
OLLAMA_HOST: str = os.getenv("BRF_OLLAMA_HOST", "http://127.0.0.1:11434")
VISION_MODEL: str = os.getenv("BRF_VISION_MODEL", "moondream")
VISION_FALLBACK_MODEL: str = os.getenv("BRF_VISION_FALLBACK_MODEL", "qwen2.5vl:7b")
TEXT_MODEL: str = os.getenv("BRF_TEXT_MODEL", "qwen2.5:7b")
MIN_HYPE_SCORE: float = float(os.getenv("BRF_MIN_HYPE_SCORE", "6"))
GAME_NAME: str = os.getenv("BRF_GAME_NAME", "Overwatch")
SCORE_FRAMES: int = int(os.getenv("BRF_SCORE_FRAMES", "2"))
VISION_MAX_IMAGES: int = int(os.getenv("BRF_VISION_MAX_IMAGES", "1"))
VISION_FRAME_WIDTH: int = int(os.getenv("BRF_VISION_FRAME_WIDTH", "512"))
OLLAMA_TIMEOUT: float = float(os.getenv("BRF_OLLAMA_TIMEOUT", "90"))
OLLAMA_MAX_RETRIES: int = int(os.getenv("BRF_OLLAMA_MAX_RETRIES", "2"))
SCORE_CLIPS_PER_CYCLE: int = int(os.getenv("BRF_SCORE_CLIPS_PER_CYCLE", "2"))
PHASH_THRESHOLD: int = int(os.getenv("BRF_PHASH_THRESHOLD", "8"))
DAILY_UPLOAD_HOUR: int = int(os.getenv("BRF_DAILY_UPLOAD_HOUR", "22"))
DAILY_UPLOAD_MINUTE: int = int(os.getenv("BRF_DAILY_UPLOAD_MINUTE", "0"))
REJECTED_DIR: Path = Path(os.getenv("BRF_REJECTED_DIR", OUTPUT_DIR / "rejected"))
UPLOADED_DIR: Path = Path(os.getenv("BRF_UPLOADED_DIR", OUTPUT_DIR / "uploaded"))
MIN_SCORE_MEM_KB: int = int(os.getenv("BRF_MIN_SCORE_MEM_KB", str(1 * 1024 * 1024)))

# ──────────────────────────────────────────────
# Recording (gpu-screen-recorder)
# ──────────────────────────────────────────────
RECORD_FPS: int = int(os.getenv("BRF_RECORD_FPS", "30"))
RECORD_QUALITY: str = os.getenv("BRF_RECORD_QUALITY", "high")

# ──────────────────────────────────────────────
# File-stability check (wait for Syncthing to finish writing)
# ──────────────────────────────────────────────
FILE_STABLE_CHECKS: int = int(os.getenv("BRF_STABLE_CHECKS", "3"))
FILE_STABLE_INTERVAL: float = float(os.getenv("BRF_STABLE_INTERVAL", "5.0"))

# ──────────────────────────────────────────────
# Ensure directories exist at import time
# ──────────────────────────────────────────────
for d in (WATCH_DIR, OUTPUT_DIR, PROCESSED_DIR, AUDIO_POOL_DIR, LOG_FILE.parent,
          REJECTED_DIR, UPLOADED_DIR, DB_PATH.parent, SETTINGS_FILE.parent):
    d.mkdir(parents=True, exist_ok=True)
