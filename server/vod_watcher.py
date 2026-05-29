#!/usr/bin/env python3
"""
Brain-Rot Shorts Factory — VOD Watcher Daemon
Monitors a directory for new gameplay VODs, detects highlights,
generates brain-rot shorts, scores them with Ollama, and queues for upload.
"""

import argparse
import logging
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import config
import clip_db
from highlight_detector import detect_highlights, wait_for_stable_file
from brain_rot_factory import generate_short
from clip_scorer import (
    register_and_score,
    score_pending_clips,
    recover_orphan_clips,
    normalize_vod_scores,
)
from service_manager import is_recording
from upload_scheduler import start_scheduler, stop_scheduler
from settings import load_settings

# ──────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────
def _setup_logging(log_level: str = "INFO") -> None:
    fmt = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(config.LOG_FILE)),
    ]
    logging.basicConfig(level=getattr(logging, log_level), format=fmt, handlers=handlers)

log = logging.getLogger("vod_watcher")


def _move_rejected(short_path: Path) -> None:
    try:
        from clip_actions import move_to_rejected
        move_to_rejected(short_path)
    except OSError as exc:
        log.warning("Could not move rejected clip: %s", exc)


# ──────────────────────────────────────────────
# Watchdog event handler
# ──────────────────────────────────────────────
class VODHandler(FileSystemEventHandler):
    """React to new .mp4 files appearing in the watch directory."""

    def __init__(self) -> None:
        super().__init__()
        self.processing_files = set()
        self.lock = threading.Lock()

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".mp4":
            return
        if "processed" in path.parts:
            return
        log.info("New VOD detected via watchdog: %s", path.name)
        self.process_vod_async(path)

    def process_vod_async(self, path: Path) -> None:
        path = path.resolve()
        with self.lock:
            if path in self.processing_files:
                return
            self.processing_files.add(path)

        def run():
            try:
                self._process_vod(path)
            except Exception as exc:
                log.error("Error processing VOD %s: %s", path.name, exc, exc_info=True)
            finally:
                with self.lock:
                    self.processing_files.discard(path)

        t = threading.Thread(target=run, name=f"process-{path.name}", daemon=True)
        t.start()

    def scan_existing(self, watch_dir: Path) -> None:
        try:
            for path in watch_dir.glob("*.mp4"):
                if path.is_file() and "processed" not in path.parts:
                    self.process_vod_async(path)
        except Exception as exc:
            log.error("Error scanning directory %s: %s", watch_dir, exc)

    def _process_vod(self, vod_path: Path) -> None:
        log.info("Waiting for file to stabilise...")
        if not wait_for_stable_file(vod_path):
            log.error("File disappeared or is empty, skipping.")
            return

        log.info("Analysing VOD for highlights...")
        highlights = detect_highlights(vod_path)
        if not highlights:
            log.info("No highlights found — moving VOD to processed/")
            self._archive(vod_path)
            return

        log.info("Found %d highlight(s): %s", len(highlights), highlights)

        scored_count = 0
        rejected_count = 0
        pending_count = 0
        best_hype = 0.0

        for ts, spike_energy in highlights:
            log.info("━" * 50)
            log.info("Processing highlight at t=%ds (audio peak %.2fx)", ts, spike_energy)
            short_path = generate_short(vod_path, ts)
            if short_path is None:
                log.warning("Failed to generate short for t=%ds, skipping.", ts)
                continue

            try:
                clip_id = register_and_score(
                    short_path, vod_path, ts,
                    spike_energy=spike_energy,
                    score_now=not is_recording(),
                )
            except Exception as exc:
                log.error("Failed to register/score clip at t=%ds: %s", ts, exc, exc_info=True)
                continue

            if clip_id is None:
                log.warning("Clip duplicate or registration failed for t=%ds", ts)
                try:
                    short_path.unlink(missing_ok=True)
                except OSError:
                    pass
                continue

            clip = clip_db.get_clip(clip_id)
            if clip and clip.get("status") == "rejected":
                rejected_count += 1
                _move_rejected(short_path)
            elif clip and clip.get("status") == "scored":
                scored_count += 1
                hype = float(clip.get("hype_score") or 0)
                best_hype = max(best_hype, hype)
            elif clip and clip.get("status") == "pending_score":
                pending_count += 1

        if not is_recording() and (scored_count > 0 or pending_count > 0):
            normalize_vod_scores(vod_path)
            scored_count = 0
            rejected_count = 0
            pending_count = 0
            best_hype = 0.0
            for clip in clip_db.list_clips_by_source(vod_path):
                st = clip.get("status")
                if st == "rejected":
                    rejected_count += 1
                    rp = Path(clip.get("file_path", ""))
                    if rp.exists() and config.OUTPUT_DIR in rp.parents:
                        _move_rejected(rp)
                elif st == "scored":
                    scored_count += 1
                    best_hype = max(best_hype, float(clip.get("hype_score") or 0))
                elif st == "pending_score":
                    pending_count += 1

        log.info("━" * 50)
        log.info(
            "Done: %d scored, %d pending, %d rejected from %s",
            scored_count, pending_count, rejected_count, vod_path.name,
        )

        if scored_count > 0 or rejected_count > 0 or pending_count > 0:
            s = load_settings()
            hh, mm = int(s["upload_hour"]), int(s["upload_minute"])
            msg = f"{scored_count} ready"
            if pending_count:
                msg += f", {pending_count} waiting for AI score"
            msg += f", {rejected_count} rejected"
            if scored_count:
                msg += f"\nBest hype: {best_hype:.0f}/10"
            msg += f"\nAuto-upload at {hh:02d}:{mm:02d} or use Control Panel."
            try:
                subprocess.run([
                    "notify-send", "-i", "video-x-generic",
                    "New Clips Ready!",
                    msg,
                ], check=False)
            except FileNotFoundError:
                pass

        self._archive(vod_path)

    @staticmethod
    def _archive(vod_path: Path) -> None:
        dest = config.PROCESSED_DIR / vod_path.name
        try:
            vod_path.rename(dest)
            log.info("Archived VOD → %s", dest)
        except OSError as exc:
            log.error("Failed to archive %s: %s", vod_path, exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Brain-Rot Shorts Factory — VOD Watcher")
    parser.add_argument(
        "--upload", action="store_true",
        help="Deprecated: uploads are handled by daily scheduler / Control Panel",
    )
    parser.add_argument("--watch-dir", type=str, default=None)
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    if args.upload:
        log.warning("--upload is deprecated; use Control Panel or daily_uploader.py")

    _setup_logging(args.log_level)

    watch_dir = Path(args.watch_dir) if args.watch_dir else config.WATCH_DIR
    watch_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("Brain-Rot Shorts Factory — VOD Watcher")
    log.info("=" * 60)
    log.info("Watch directory : %s", watch_dir)
    log.info("Output directory: %s", config.OUTPUT_DIR)
    log.info("Top N spikes    : %d", config.TOP_N_SPIKES)
    log.info("Clip duration   : %ds", config.CLIP_DURATION)
    log.info("=" * 60)

    start_scheduler()
    recover_orphan_clips()
    if not is_recording():
        score_pending_clips()

    handler = VODHandler()
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)

    shutdown = False

    def _signal_handler(signum, frame):
        nonlocal shutdown
        log.info("Received signal %d — shutting down...", signum)
        shutdown = True
        observer.stop()
        stop_scheduler()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    observer.start()
    log.info("Watching for new VODs...")
    handler.scan_existing(watch_dir)

    try:
        last_scan = time.time()
        last_pending = time.time()
        while not shutdown:
            time.sleep(1)
            if time.time() - last_scan >= 10:
                handler.scan_existing(watch_dir)
                last_scan = time.time()
            if time.time() - last_pending >= 60:
                if not is_recording():
                    recover_orphan_clips()
                    score_pending_clips()
                last_pending = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        stop_scheduler()
        log.info("VOD Watcher stopped.")


if __name__ == "__main__":
    main()
