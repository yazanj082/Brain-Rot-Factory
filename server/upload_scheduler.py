"""
Brain-Rot Shorts Factory — Background upload scheduler
Runs inside vod_watcher; checks settings every 30s.
"""

import logging
import threading
import time

from daily_uploader import run_daily_upload
from settings import is_upload_time_now, load_settings

log = logging.getLogger(__name__)

_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()
_last_trigger_minute: str | None = None


def _scheduler_loop() -> None:
    global _last_trigger_minute
    log.info("Upload scheduler started")
    while not _stop_event.is_set():
        try:
            if is_upload_time_now():
                now_key = time.strftime("%Y-%m-%d %H:%M")
                if _last_trigger_minute != now_key:
                    _last_trigger_minute = now_key
                    log.info("Scheduled upload time reached — running daily uploader")
                    run_daily_upload(force=False)
        except Exception as exc:
            log.error("Scheduler error: %s", exc, exc_info=True)
        _stop_event.wait(30)
    log.info("Upload scheduler stopped")


def start_scheduler() -> None:
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, name="upload-scheduler", daemon=True)
    _scheduler_thread.start()
    s = load_settings()
    log.info(
        "Auto-upload: %s at %02d:%02d",
        "ON" if s.get("auto_upload_enabled") else "OFF",
        int(s["upload_hour"]),
        int(s["upload_minute"]),
    )


def stop_scheduler() -> None:
    _stop_event.set()
