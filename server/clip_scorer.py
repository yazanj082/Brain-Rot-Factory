"""
Brain-Rot Shorts Factory — Ollama vision clip scorer (Overwatch-tuned)
"""

import logging
import math
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any, Optional

import config
import clip_db
from frame_extractor import extract_frames, phash_from_video, prepare_vision_frames
from ocr_prefilter import check_frames
from ollama_client import generate_json, is_ollama_available, model_available

log = logging.getLogger(__name__)

MIN_MEM_KB = int(getattr(config, "MIN_SCORE_MEM_KB", 2 * 1024 * 1024))

VISION_HYPE_WEIGHT = 0.35
SPIKE_HYPE_WEIGHT = 0.65
RANK_BLEND_WEIGHT = 0.5

SCORE_PROMPT = """Analyze this {game} gameplay short clip frame(s). Reply with ONLY one JSON object, no markdown.

Use the FULL 1-10 range for hype_score (do NOT default to 8):
- 1-4: boring, menus, walking, no action
- 5-6: average fight
- 7-8: solid kills / team fight
- 9-10: exceptional (team wipe, huge ult, clutch win)

Overwatch rules — NOT death cam / replay:
- First-person while YOU are alive and fighting
- Killing enemies, kill feed, damage numbers, eliminations on opponents
- Brief kill effects when enemies die

IS death cam / replay (set has_replay_or_death_cam=true ONLY for these):
- Third-person spectator after YOU died
- "YOU DIED", respawn timer, grey death screen
- Play of the Game replay, full match replay
- Hero select, scoreboard, defeat/victory screen, menus dominating the clip

Set reject=true if the clip is mostly bad footage OR you died / spectating / replay.
If has_replay_or_death_cam is true, you should usually set reject=true and explain why in reject_reason.
Enemy deaths and kill UI alone are GOOD — do not set has_replay_or_death_cam for those.

JSON fields (use real booleans true/false, not strings):
- is_live_gameplay (bool): active match from your live POV
- has_replay_or_death_cam (bool): true only if YOU are dead/spectating/replay — NOT when enemies die
- player_doing_well (bool): you winning fights / getting kills
- hype_score (int 1-10)
- trim_start_sec (number): cut replay/death at start if any
- trim_end_sec (number): cut replay/death at end if any
- reject (bool)
- reject_reason (string or null)
- summary (string, one short sentence)"""


def _as_bool(value: Any, default: bool = False) -> bool:
    """Parse model booleans; JSON strings like \"false\" must not be truthy."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "1"):
            return True
        if v in ("false", "no", "0", ""):
            return False
        return default
    return bool(value)


def _parse_vision_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Normalized booleans from vision JSON."""
    return {
        "reject": _as_bool(result.get("reject"), default=False),
        "is_live_gameplay": _as_bool(result.get("is_live_gameplay"), default=True),
        "has_replay_or_death_cam": _as_bool(result.get("has_replay_or_death_cam"), default=False),
        "player_doing_well": _as_bool(result.get("player_doing_well"), default=True),
        "reject_reason": result.get("reject_reason"),
        "summary": result.get("summary") or "",
        "trim_start_sec": float(result.get("trim_start_sec", 0) or 0),
        "trim_end_sec": float(result.get("trim_end_sec", 0) or 0),
    }


def _clamp_vision_hype(raw: Any) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 5.0
    return max(1.0, min(10.0, round(v, 1)))


def spike_to_hype(ratio: float) -> float:
    """Map audio peak ratio (vs session mean) to 1-10 hype."""
    if ratio <= 0:
        return 5.0
    score = 3.0 + 2.5 * math.log2(max(ratio, 1.0))
    return max(1.0, min(10.0, round(score, 1)))


def compute_blended_hype(vision_hype: float, spike_energy: Optional[float]) -> float:
    spike_h = spike_to_hype(spike_energy or 1.5)
    raw = VISION_HYPE_WEIGHT * vision_hype + SPIKE_HYPE_WEIGHT * spike_h
    return max(1.0, min(10.0, round(raw, 1)))


def _rank_hype_for_position(rank_index: int, n: int) -> float:
    """rank_index 0 = loudest spike in VOD batch."""
    if n <= 1:
        return 8.0
    spread_top = 9.5
    spread_bottom = 6.0
    return spread_bottom + (spread_top - spread_bottom) * (n - 1 - rank_index) / (n - 1)


def normalize_vod_scores(source_vod: Path | str) -> int:
    """
    Re-rank scored clips from one VOD by spike_energy so scores spread out.
    Rejects clips below min_hype after normalization.
    """
    min_hype = config.MIN_HYPE_SCORE
    try:
        from settings import get_min_hype_score
        min_hype = get_min_hype_score()
    except Exception:
        pass

    clips = clip_db.list_clips_by_source(source_vod, statuses=("scored",))
    if not clips:
        return 0

    spikes = [float(c.get("spike_energy") or 0) for c in clips]
    if not any(s > 0 for s in spikes):
        log.debug("Skip normalize for %s — no spike_energy data", Path(source_vod).name)
        return 0

    # Sort by spike_energy (fallback to current hype)
    clips.sort(
        key=lambda c: (
            float(c.get("spike_energy") or 0),
            float(c.get("hype_score") or 0),
        ),
        reverse=True,
    )

    n = len(clips)
    updated = 0
    for rank_index, clip in enumerate(clips):
        raw = float(clip.get("hype_score") or 5.0)
        rank_hype = _rank_hype_for_position(rank_index, n)
        if n >= 2:
            final = round(
                (1 - RANK_BLEND_WEIGHT) * raw + RANK_BLEND_WEIGHT * rank_hype, 1
            )
        else:
            final = raw

        clip_id = clip["id"]
        if final < min_hype:
            clip_db.update_clip(
                clip_id,
                status="rejected",
                hype_score=final,
                reject_reason=f"Normalize: Ranked below minimum hype ({final:.1f} < {min_hype})",
            )
            log.info("Clip %s rejected after normalize: hype=%.1f", clip_id, final)
        else:
            clip_db.update_clip(clip_id, hype_score=final)
            log.info(
                "Clip %s normalized: hype=%.1f (rank %d/%d, spike=%.2fx)",
                clip_id,
                final,
                rank_index + 1,
                n,
                float(clip.get("spike_energy") or 0),
            )
        updated += 1
    return updated


def _mem_available_kb() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    except OSError:
        pass
    return 999_999_999


def _can_run_ollama() -> bool:
    from service_manager import is_recording

    if is_recording():
        log.debug("Recorder active — deferring Ollama scoring")
        return False
    avail = _mem_available_kb()
    if avail < MIN_MEM_KB:
        log.warning("Low memory (%d MB free) — deferring Ollama scoring", avail // 1024)
        return False
    return True


def _safe_phash(video_path: Path) -> Optional[str]:
    try:
        return phash_from_video(video_path)
    except Exception as exc:
        log.warning("phash failed for %s: %s", video_path.name, exc)
        return None


def _coerce_vision_result(result: Any) -> dict[str, Any]:
    """Normalize Ollama output to a dict (moondream sometimes returns a list)."""
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                log.warning("Vision result was a list; using first dict element")
                return item
    raise TypeError(f"Invalid vision result type: {type(result).__name__}")


def _build_reject_reason(parsed: dict[str, Any], prefix: str = "AI") -> str:
    """Always return a non-empty reject explanation."""
    raw = parsed.get("reject_reason")
    if raw and str(raw).strip():
        text = str(raw).strip()
        if text.startswith(("AI:", "OCR:", "Normalize:", "Manual:")):
            return text
        if text.lower() not in ("flagged for rejection", "model rejected clip"):
            return f"{prefix}: {text}"

    if parsed.get("has_replay_or_death_cam"):
        return f"{prefix}: Death cam or replay detected (you died or spectating)"
    if not parsed.get("is_live_gameplay", True):
        return f"{prefix}: Not live gameplay (menus, scoreboard, or hero select)"
    if not parsed.get("player_doing_well", True):
        return f"{prefix}: Player not performing well in this clip"
    if parsed.get("reject"):
        return f"{prefix}: Model marked clip as low quality"
    return f"{prefix}: Clip did not pass quality check"


def _apply_quality_policy(parsed: dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Reject death cam, menus, and explicit model rejects; use Approve for false positives."""
    if parsed["reject"]:
        return True, _build_reject_reason(parsed, "AI")

    if not parsed["is_live_gameplay"]:
        return True, _build_reject_reason(parsed, "AI")

    if parsed["has_replay_or_death_cam"]:
        return True, _build_reject_reason(parsed, "AI")

    return False, None


def _generate_metadata_async(clip_id: int, summary: str, hype: float) -> None:
    """Background human caption/title for dashboard and upload."""

    def run() -> None:
        try:
            import json
            from metadata_generator import generate_metadata

            meta = generate_metadata(summary, hype)
            tags = meta.get("tags", [])
            clip_db.update_clip(
                clip_id,
                title=meta.get("title"),
                description=meta.get("description"),
                tags=json.dumps(tags) if isinstance(tags, list) else tags,
            )
            log.info("Generated metadata for clip %s", clip_id)
        except Exception as exc:
            log.warning("Metadata generation failed for clip %s: %s", clip_id, exc)

    threading.Thread(target=run, name=f"meta-{clip_id}", daemon=True).start()


def _vision_models_to_try() -> list[str]:
    models: list[str] = []
    try:
        from settings import load_settings
        s = load_settings()
        primary = s.get("vision_model", config.VISION_MODEL)
        fallback = s.get("vision_fallback_model", config.VISION_FALLBACK_MODEL)
    except Exception:
        primary = config.VISION_MODEL
        fallback = config.VISION_FALLBACK_MODEL

    for name in ("moondream", primary, fallback):
        if name and name not in models and model_available(name):
            models.append(name)
    if not models:
        for name in ("qwen2.5vl:7b",):
            if model_available(name):
                models.append(name)
    return models


def _call_vision_json(model: str, prompt: str, images: list[Path]) -> dict[str, Any]:
    """Run Ollama vision with a hard wall-clock timeout."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(generate_json, model, prompt, images)
        try:
            return fut.result(timeout=config.OLLAMA_TIMEOUT + 15)
        except FuturesTimeout as exc:
            raise TimeoutError(f"Ollama vision timed out after {config.OLLAMA_TIMEOUT}s") from exc


def _run_vision_scoring(prompt: str, ocr_frames: list[Path]) -> dict[str, Any]:
    vision_frames = prepare_vision_frames(ocr_frames)
    if not vision_frames:
        raise RuntimeError("No vision frames prepared")

    errors: list[str] = []
    for model in _vision_models_to_try():
        try:
            log.info("Scoring with %s (%d image(s))", model, len(vision_frames))
            return _call_vision_json(model, prompt, vision_frames)
        except Exception as exc:
            msg = f"{model}: {exc}"
            log.warning("Vision model failed — %s", msg)
            errors.append(msg)
    raise RuntimeError("; ".join(errors) or "No vision models available")


def score_clip(
    video_path: Path,
    clip_id: int,
    source_vod: Optional[Path] = None,
    highlight_ts: Optional[int] = None,
) -> dict[str, Any]:
    """
    Score a rendered short. Updates clip_db.
    Returns dict with status, scores, reject_reason.
    """
    if not _can_run_ollama():
        clip_db.update_clip(clip_id, status="pending_score", reject_reason="Deferred — recording or low memory")
        return {"status": "pending_score", "error": "deferred"}

    db_clip = clip_db.get_clip(clip_id)
    if db_clip and db_clip.get("manual_override"):
        log.debug("Skipping clip %s — manual override", clip_id)
        return {"status": db_clip.get("status"), "skipped": "manual_override"}

    spike_energy = float(db_clip.get("spike_energy") or 0) if db_clip else 0.0

    frames = extract_frames(video_path, count=config.SCORE_FRAMES)
    if not frames:
        clip_db.update_clip(clip_id, status="pending_score", reject_reason="Frame extraction failed")
        return {"status": "pending_score", "error": "no frames"}

    ocr_reject, ocr_reason = check_frames(frames)
    if ocr_reject:
        reason = ocr_reason or "Bad footage detected"
        if not str(reason).startswith("OCR:"):
            reason = f"OCR: {reason}"
        clip_db.update_clip(
            clip_id,
            status="rejected",
            reject_reason=reason,
            hype_score=0,
        )
        try:
            from clip_actions import move_to_rejected
            if video_path.exists():
                move_to_rejected(video_path)
        except Exception as exc:
            log.warning("Could not move rejected clip: %s", exc)
        return {"status": "rejected", "reject_reason": reason}

    if not is_ollama_available():
        clip_db.update_clip(clip_id, status="pending_score", reject_reason="Ollama offline")
        log.warning("Ollama offline — clip %s queued for later scoring", clip_id)
        return {"status": "pending_score", "error": "ollama offline"}

    game = config.GAME_NAME
    try:
        from settings import load_settings
        game = load_settings().get("game_name", game)
    except Exception:
        pass

    prompt = SCORE_PROMPT.format(game=game)

    try:
        raw_result = _run_vision_scoring(prompt, frames)
        result = _coerce_vision_result(raw_result)
    except (TypeError, AttributeError) as exc:
        log.error("Invalid vision JSON for clip %s: %s", clip_id, exc)
        clip_db.update_clip(clip_id, status="pending_score", reject_reason=str(exc)[:200])
        return {"status": "pending_score", "error": str(exc)}
    except Exception as exc:
        log.error("Vision scoring failed for clip %s: %s", clip_id, exc)
        clip_db.update_clip(clip_id, status="pending_score", reject_reason=str(exc)[:200])
        return {"status": "pending_score", "error": str(exc)}

    parsed = _parse_vision_fields(result)
    reject, reason = _apply_quality_policy(parsed)
    vision_hype = _clamp_vision_hype(result.get("hype_score", 5))
    blended = compute_blended_hype(vision_hype, spike_energy or None)

    fields = {
        "hype_score": blended,
        "is_live_gameplay": 1 if parsed["is_live_gameplay"] else 0,
        "has_replay": 1 if parsed["has_replay_or_death_cam"] else 0,
        "is_positive_outcome": 1 if parsed["player_doing_well"] else 0,
        "trim_start_sec": parsed["trim_start_sec"],
        "trim_end_sec": parsed["trim_end_sec"],
        "summary": parsed["summary"],
        "scored_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }

    if reject:
        fields["status"] = "rejected"
        fields["reject_reason"] = reason
        fields["hype_score"] = blended
    else:
        fields["status"] = "scored"
        fields["reject_reason"] = None

    clip_db.update_clip(clip_id, **fields)

    if fields["status"] == "rejected":
        try:
            from clip_actions import move_to_rejected
            if video_path.exists():
                move_to_rejected(video_path)
        except Exception as exc:
            log.warning("Could not move rejected clip: %s", exc)
    elif fields["status"] == "scored":
        _generate_metadata_async(clip_id, parsed["summary"], blended)

    log.info(
        "Clip %s scored: hype=%.1f (vision=%.1f spike=%.2fx→%.1f) status=%s%s",
        clip_id,
        fields["hype_score"],
        vision_hype,
        spike_energy,
        spike_to_hype(spike_energy or 1.5),
        fields["status"],
        f" reason={reason}" if reason else "",
    )
    return {"status": fields["status"], **result, "reject_reason": reason, "hype_score": blended}


def register_clip_only(
    short_path: Path,
    source_vod: Path,
    highlight_ts: int,
    spike_energy: Optional[float] = None,
) -> Optional[int]:
    """Register clip in DB with phash; status pending_score until Ollama runs."""
    phash = _safe_phash(short_path)
    clip_id = clip_db.register_clip(
        short_path, source_vod, highlight_ts, phash=phash, spike_energy=spike_energy
    )
    if clip_id is None:
        return None
    clip_db.update_clip(clip_id, status="pending_score")
    return clip_id


def register_and_score(
    short_path: Path,
    source_vod: Path,
    highlight_ts: int,
    *,
    spike_energy: Optional[float] = None,
    score_now: bool = True,
) -> Optional[int]:
    """Register clip; optionally score immediately if resources allow."""
    clip_id = register_clip_only(short_path, source_vod, highlight_ts, spike_energy=spike_energy)
    if clip_id is None:
        return None
    if score_now and _can_run_ollama():
        score_clip(short_path, clip_id, source_vod, highlight_ts)
    return clip_id


def _find_source_vod(source_vod: str, highlight_ts: int) -> Optional[Path]:
    """Locate archived or raw VOD for spike backfill."""
    name = Path(source_vod).name
    candidates = [
        Path(source_vod),
        config.PROCESSED_DIR / name,
        config.WATCH_DIR / name,
        config.WATCH_DIR / "processed" / name,
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def backfill_spike_energy(clip_id: int) -> Optional[float]:
    """Re-derive spike_energy from source VOD if missing."""
    clip = clip_db.get_clip(clip_id)
    if not clip:
        return None
    existing = float(clip.get("spike_energy") or 0)
    if existing > 0:
        return existing

    ts = int(clip.get("highlight_ts") or 0)
    vod = _find_source_vod(clip.get("source_vod", ""), ts)
    if not vod:
        return None

    from highlight_detector import detect_highlights

    for spike_ts, ratio in detect_highlights(vod):
        if spike_ts == ts:
            clip_db.update_clip(clip_id, spike_energy=ratio)
            log.info("Backfilled spike_energy=%.2f for clip %s from %s", ratio, clip_id, vod.name)
            return ratio
    return None


def score_pending_clips(limit: Optional[int] = None) -> int:
    """Score pending clips; default limit from config (use limit=None for all)."""
    if not _can_run_ollama():
        return 0
    if not is_ollama_available():
        return 0

    batch_limit = max(1, config.SCORE_CLIPS_PER_CYCLE) if limit is None else limit
    pending = clip_db.list_clips(status="pending_score", limit=500)
    count = 0
    touched_sources: set[str] = set()
    processed = 0

    for clip in pending:
        if processed >= batch_limit:
            break
        path = Path(clip["file_path"])
        if not path.exists():
            clip_db.update_clip(
                clip["id"],
                status="rejected",
                reject_reason="Video file not found",
                hype_score=0,
            )
            processed += 1
            count += 1
            continue

        backfill_spike_energy(clip["id"])
        log.info("Scoring pending clip id=%s %s", clip["id"], path.name)
        result = score_clip(path, clip["id"])
        processed += 1
        if result.get("status") != "pending_score":
            count += 1
            src = clip.get("source_vod")
            if src:
                touched_sources.add(src)

    for src in touched_sources:
        normalize_vod_scores(src)

    if pending:
        remain = max(0, len(pending) - processed)
        log.info(
            "Scored %d pending clip(s) this cycle (%d remain in queue)",
            count,
            remain,
        )
    return count


def score_all_pending() -> int:
    """Score entire pending queue (for rescore script)."""
    total = 0
    while True:
        batch = score_pending_clips(limit=999)
        if batch == 0:
            pending = clip_db.list_clips(status="pending_score", limit=1)
            if not pending:
                break
            # Stuck queue (e.g. Ollama offline)
            break
        total += batch
        pending_left = clip_db.list_clips(status="pending_score", limit=1)
        if not pending_left:
            break
    return total


def _parse_highlight_ts(filename: str) -> int:
    match = re.search(r"_t(\d+)s\.mp4$", filename)
    return int(match.group(1)) if match else 0


def recover_orphan_clips() -> int:
    """Register unscored mp4 files in OUTPUT_DIR that have no DB record."""
    if not config.OUTPUT_DIR.exists():
        return 0
    count = 0
    for f in config.OUTPUT_DIR.glob("*.mp4"):
        if clip_db.get_clip_by_path(f):
            continue
        ts = _parse_highlight_ts(f.name)
        clip_id = clip_db.register_clip(
            f,
            source_vod=f,
            highlight_ts=ts,
            phash=_safe_phash(f),
            content_key_override=clip_db.file_content_key(f.name),
        )
        if clip_id is None:
            log.debug("Could not register orphan %s (duplicate or skip)", f.name)
            continue
        clip_db.update_clip(clip_id, status="pending_score")
        log.info("Recovered orphan clip: %s (id=%s)", f.name, clip_id)
        count += 1
    return count


def rescore_clips(statuses: tuple[str, ...] = ("scored", "rejected")) -> int:
    """Reset clips to pending_score for re-scoring with current logic."""
    total = 0
    for status in statuses:
        clips = clip_db.list_clips(status=status, limit=500)
        for clip in clips:
            if clip.get("manual_override"):
                continue
            clip_db.update_clip(
                clip["id"],
                status="pending_score",
                hype_score=None,
                reject_reason=None,
                scored_at=None,
                manual_override=0,
            )
            total += 1
    return total


def generate_metadata_for_clip(clip_id: int) -> bool:
    """Sync metadata generation for one clip (dashboard refresh caption)."""
    clip = clip_db.get_clip(clip_id)
    if not clip:
        return False
    try:
        import json
        from metadata_generator import generate_metadata

        summary = clip.get("summary") or "Gameplay highlight"
        hype = float(clip.get("hype_score") or 5)
        meta = generate_metadata(summary, hype)
        tags = meta.get("tags", [])
        clip_db.update_clip(
            clip_id,
            title=meta.get("title"),
            description=meta.get("description"),
            tags=json.dumps(tags) if isinstance(tags, list) else tags,
        )
        return True
    except Exception as exc:
        log.error("Metadata regen failed for clip %s: %s", clip_id, exc)
        return False


def rescore_all_scored() -> int:
    """Reset scored clips only (legacy helper)."""
    return rescore_clips(("scored",))


def run_post_recording_scoring() -> int:
    """Recover orphans and score pending clips (call after recording stops)."""
    recovered = recover_orphan_clips()
    scored = score_pending_clips()
    log.info("Post-recording scoring: %d recovered, %d scored", recovered, scored)
    return scored
