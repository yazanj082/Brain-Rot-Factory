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
}


def load_settings() -> dict[str, Any]:
    path = config.SETTINGS_FILE
    if not path.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(path.read_text())
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load settings: %s — using defaults", exc)
        return dict(DEFAULTS)


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
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
