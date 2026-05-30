"""
Brain-Rot Shorts Factory — systemd service control (whitelisted units only)
"""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

FACTORY_ROOT = Path(__file__).resolve().parent.parent

ServiceName = Literal["recorder", "watcher", "dashboard"]

UNIT_MAP = {
    "recorder": "game-recorder.service",
    "watcher": "vod-watcher.service",
    "dashboard": "review-dashboard.service",
}


def _run_systemctl(action: str, unit: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["systemctl", "--user", action, unit],
            capture_output=True,
            text=True,
            timeout=30,
        )
        ok = result.returncode == 0
        msg = (result.stderr or result.stdout or "").strip()
        return ok, msg
    except Exception as exc:
        return False, str(exc)


def is_active(service: ServiceName) -> bool:
    unit = UNIT_MAP[service]
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False


def get_status(service: ServiceName) -> dict:
    unit = UNIT_MAP[service]
    active = is_active(service)
    return {"service": service, "unit": unit, "active": active}


def start(service: ServiceName) -> tuple[bool, str]:
    return _run_systemctl("start", UNIT_MAP[service])


def stop(service: ServiceName) -> tuple[bool, str]:
    return _run_systemctl("stop", UNIT_MAP[service])


def is_recording() -> bool:
    return is_active("recorder")


def start_gaming_session() -> dict:
    """Start recorder; ensure watcher is running. Stops Ollama first to free RAM (unless BRF_KEEP_OLLAMA=1)."""
    results = {}
    if not is_active("watcher"):
        ok, msg = start("watcher")
        results["watcher"] = {"ok": ok, "msg": msg}

    keep_ollama = os.getenv("BRF_KEEP_OLLAMA", "").lower() in ("1", "true", "yes")
    if not keep_ollama and _ollama_ready():
        ok, msg = stop_ollama(True)
        results["ollama"] = {"ok": ok, "msg": msg or "Stopped Ollama to free RAM for gaming"}

    # Restart (not just start) so portal token is cleared and picker runs again
    ok, msg = _run_systemctl("restart", UNIT_MAP["recorder"])
    results["recorder"] = {
        "ok": ok,
        "msg": msg or "Look for the screen/window picker dialog on your desktop",
    }
    return results


def stop_recording() -> dict:
    ok, msg = stop("recorder")
    results = {"recorder": {"ok": ok, "msg": msg}}
    if ok:
        oll_ok, oll_msg = start_ollama()
        results["ollama"] = {"ok": oll_ok, "msg": oll_msg}
        if oll_ok:
            try:
                from clip_scorer import vision_models_ready

                if not vision_models_ready():
                    results["ollama"]["vision_warning"] = (
                        "No vision model loaded. Run: ollama pull moondream"
                    )
            except Exception as exc:
                log.warning("Vision model check failed: %s", exc)

        try:
            from clip_scorer import run_post_recording_scoring
            import threading

            def _score():
                run_post_recording_scoring()

            threading.Thread(target=_score, name="post-recording-score", daemon=True).start()
            results["scoring"] = {
                "ok": True,
                "msg": "Ollama starting — clips will score after VOD processing",
            }
        except Exception as exc:
            log.warning("Could not start post-recording scoring: %s", exc)
    return results


def _ollama_ready() -> bool:
    try:
        import httpx
        r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def start_ollama() -> tuple[bool, str]:
    if _ollama_ready():
        return True, "Ollama already running"
    for unit in ("ollama.service", "ollama"):
        ok, msg = _run_systemctl("start", unit)
        if ok:
            for _ in range(30):
                if _ollama_ready():
                    return True, f"Started {unit}"
                time.sleep(1)
            return True, f"Started {unit} (waiting for API)"
    try:
        log_dir = Path.home() / ".local" / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "ollama-serve.log"
        with open(log_file, "a", encoding="utf-8") as fh:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        for _ in range(30):
            if _ollama_ready():
                return True, "Started ollama serve"
            time.sleep(1)
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.warning("ollama serve fallback failed: %s", exc)
    return False, "Could not start Ollama (install ollama.service or run ollama serve)"


def stop_ollama(stop: bool = True) -> tuple[bool, str]:
    if not stop:
        return True, "Ollama left running"
    for unit in ("ollama.service", "ollama"):
        _run_systemctl("stop", unit)
    try:
        subprocess.run(["pkill", "-x", "ollama"], check=False, timeout=5)
    except Exception:
        pass
    return True, "Ollama stop requested"


def start_factory(open_dashboard: bool = False) -> dict:
    """Start watcher and dashboard — not Ollama or the game recorder (lazy Ollama saves RAM)."""
    results: dict = {}
    results["ollama"] = {
        "ok": True,
        "msg": "Lazy start — Ollama runs after Stop Recording to save RAM while gaming",
    }
    for svc in ("watcher", "dashboard"):
        ok, msg = start(svc)
        results[svc] = {"ok": ok, "msg": msg}
    results["recorder"] = {"ok": True, "msg": "Not started — use Start Gaming Session"}
    if open_dashboard:
        try:
            subprocess.run(["xdg-open", "http://localhost:8069"], check=False, timeout=5)
        except Exception:
            pass
    return results


def stop_factory(stop_ollama: bool = True) -> dict:
    """Stop recorder, watcher, dashboard, and optionally Ollama."""
    results: dict = {}
    for svc in ("recorder", "watcher", "dashboard"):
        ok, msg = stop(svc)
        results[svc] = {"ok": ok, "msg": msg}
    ok, msg = stop_ollama(stop_ollama)
    results["ollama"] = {"ok": ok, "msg": msg}
    return results


def all_status() -> dict:
    from ollama_client import is_ollama_available
    from clip_scorer import vision_models_ready
    import clip_db
    from settings import load_settings, next_upload_datetime, seconds_until_next_upload

    counts = clip_db.count_by_status()
    last = clip_db.get_last_upload()
    pick = clip_db.get_tonights_pick()
    s = load_settings()

    return {
        "recorder": get_status("recorder"),
        "watcher": get_status("watcher"),
        "dashboard": get_status("dashboard"),
        "ollama": {
            "active": is_ollama_available(),
            "vision_ready": vision_models_ready() if is_ollama_available() else False,
            "lazy_mode": True,
        },
        "queue": {
            "scored": counts.get("scored", 0),
            "pending_score": counts.get("pending_score", 0),
            "rejected": counts.get("rejected", 0),
            "uploaded": counts.get("uploaded", 0),
        },
        "schedule": {
            "auto_upload_enabled": s.get("auto_upload_enabled", True),
            "upload_hour": int(s["upload_hour"]),
            "upload_minute": int(s["upload_minute"]),
            "next_upload": next_upload_datetime().isoformat(),
            "seconds_until": seconds_until_next_upload(),
        },
        "tonights_pick": pick,
        "last_upload": last,
    }
