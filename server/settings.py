"""
Brain-Rot Shorts Factory — User settings (upload schedule, thresholds)
Persisted to ~/shorts_assets/settings.json and editable from Control Panel.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

import config

log = logging.getLogger(__name__)

# gpu-screen-recorder -q values (see: man gpu-screen-recorder)
GSR_QUALITY_PRESETS = frozenset({"medium", "high", "very_high", "ultra"})
# Legacy dashboard aliases → GSR preset
QUALITY_ALIASES: dict[str, str] = {
    "ultralow": "medium",
    "ultra_low": "medium",
    "low": "medium",
    "veryhigh": "very_high",
    "very-high": "very_high",
}
RECORD_QUALITY_PRESETS = GSR_QUALITY_PRESETS
RECORD_FPS_MIN = 15
RECORD_FPS_MAX = 60

DEFAULTS: dict[str, Any] = {
    "auto_upload_enabled": True,
    "upload_hour": config.DAILY_UPLOAD_HOUR,
    "upload_minute": config.DAILY_UPLOAD_MINUTE,
    "last_auto_upload_date": None,
    "min_hype_score": config.MIN_HYPE_SCORE,
    "game_name": config.GAME_NAME,
    "vision_model": config.VISION_MODEL,
    "vision_fallback_model": config.VISION_FALLBACK_MODEL,
    "text_model": config.TEXT_MODEL,
    "record_fps": config.RECORD_FPS,
    "record_quality": config.RECORD_QUALITY,
}


def _coerce_recording_settings(data: dict[str, Any]) -> None:
    """Normalize recording fields after merge (invalid JSON values fall back)."""
    try:
        fps = int(float(data.get("record_fps", config.RECORD_FPS)))
        data["record_fps"] = max(RECORD_FPS_MIN, min(RECORD_FPS_MAX, fps))
    except (TypeError, ValueError):
        data["record_fps"] = config.RECORD_FPS

    data["record_quality"] = _normalize_record_quality(
        str(data.get("record_quality", config.RECORD_QUALITY))
    )


def _normalize_record_quality(raw: str) -> str:
    q = str(raw).strip().lower().replace("-", "_")
    q = QUALITY_ALIASES.get(q, q)
    return q if q in GSR_QUALITY_PRESETS else config.RECORD_QUALITY


def quality_for_gpu_screen_recorder(raw: str | None = None) -> str:
    """Preset string passed to gpu-screen-recorder -q."""
    if raw is None:
        return _normalize_record_quality(str(load_settings().get("record_quality", config.RECORD_QUALITY)))
    return _normalize_record_quality(str(raw))


def normalize_recording_updates(updates: dict[str, Any]) -> dict[str, Any]:
    """Validate and return recording keys from a settings PATCH."""
    out: dict[str, Any] = {}
    if "record_fps" in updates:
        try:
            fps = int(float(updates["record_fps"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("record_fps must be a number") from exc
        out["record_fps"] = max(RECORD_FPS_MIN, min(RECORD_FPS_MAX, fps))
    if "record_quality" in updates:
        q = _normalize_record_quality(str(updates["record_quality"]))
        if q not in GSR_QUALITY_PRESETS:
            allowed = ", ".join(sorted(GSR_QUALITY_PRESETS))
            raise ValueError(f"record_quality must be one of: {allowed}")
        out["record_quality"] = q
    return out


def load_settings() -> dict[str, Any]:
    path = config.SETTINGS_FILE
    if not path.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(path.read_text())
        merged = dict(DEFAULTS)
        merged.update(data)
        _coerce_recording_settings(merged)
        return merged
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load settings: %s — using defaults", exc)
        return dict(DEFAULTS)


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    updates = {**updates, **normalize_recording_updates(updates)}
    current = load_settings()
    current.update(updates)
    config.SETTINGS_FILE.write_text(json.dumps(current, indent=2))
    log.info("Settings saved: %s", config.SETTINGS_FILE)
    return current


def get_min_hype_score() -> float:
    return float(load_settings().get("min_hype_score", config.MIN_HYPE_SCORE))


def mark_auto_upload_done() -> None:
    save_settings({"last_auto_upload_date": date.today().isoformat()})


def already_uploaded_today() -> bool:
    last = load_settings().get("last_auto_upload_date")
    return last == date.today().isoformat()


def next_upload_datetime() -> datetime:
    s = load_settings()
    now = datetime.now()
    target = now.replace(
        hour=int(s["upload_hour"]),
        minute=int(s["upload_minute"]),
        second=0,
        microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)
    return target


def seconds_until_next_upload() -> int:
    delta = next_upload_datetime() - datetime.now()
    return max(0, int(delta.total_seconds()))


def is_upload_time_now() -> bool:
    s = load_settings()
    if not s.get("auto_upload_enabled", True):
        return False
    now = datetime.now()
    return now.hour == int(s["upload_hour"]) and now.minute == int(s["upload_minute"])
