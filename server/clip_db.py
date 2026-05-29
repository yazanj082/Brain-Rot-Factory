"""
Brain-Rot Shorts Factory — Clip registry (SQLite)
Tracks clips, scores, metadata, and upload history with deduplication.
"""

import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import config

log = logging.getLogger(__name__)

STATUSES = ("pending", "pending_score", "scored", "queued", "uploaded", "rejected")


def content_key(source_vod: str, highlight_ts: int) -> str:
    raw = f"{Path(source_vod).name}:{highlight_ts}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def file_content_key(filename: str) -> str:
    """Unique key per output file — used for orphan recovery."""
    return hashlib.sha256(f"file:{filename}".encode()).hexdigest()[:32]


@contextmanager
def _connect():
    conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                source_vod TEXT NOT NULL,
                highlight_ts INTEGER NOT NULL,
                content_key TEXT NOT NULL UNIQUE,
                phash TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                hype_score REAL,
                is_live_gameplay INTEGER,
                has_replay INTEGER,
                is_positive_outcome INTEGER,
                reject_reason TEXT,
                trim_start_sec REAL DEFAULT 0,
                trim_end_sec REAL DEFAULT 0,
                summary TEXT,
                title TEXT,
                description TEXT,
                tags TEXT,
                youtube_id TEXT,
                created_at TEXT NOT NULL,
                uploaded_at TEXT,
                scored_at TEXT,
                spike_energy REAL
            )
        """)
        _migrate_schema(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_status ON clips(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_hype ON clips(hype_score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_content ON clips(content_key)")


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(clips)").fetchall()}
    if "spike_energy" not in cols:
        conn.execute("ALTER TABLE clips ADD COLUMN spike_energy REAL")
        log.info("Migrated clips table: added spike_energy column")
    if "manual_override" not in cols:
        conn.execute("ALTER TABLE clips ADD COLUMN manual_override INTEGER DEFAULT 0")
        log.info("Migrated clips table: added manual_override column")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    if d.get("tags"):
        try:
            d["tags"] = json.loads(d["tags"])
        except json.JSONDecodeError:
            pass
    return d


def is_duplicate_content(source_vod: str, highlight_ts: int) -> bool:
    key = content_key(source_vod, highlight_ts)
    with _connect() as conn:
        row = conn.execute(
            "SELECT status FROM clips WHERE content_key = ? AND status = 'uploaded'",
            (key,),
        ).fetchone()
    return row is not None


def is_duplicate_phash(phash: str, threshold: int = 8) -> bool:
    if not phash:
        return False
    try:
        import imagehash
        new_hash = imagehash.hex_to_hash(phash)
    except Exception:
        return False
    with _connect() as conn:
        rows = conn.execute(
            "SELECT phash FROM clips WHERE status = 'uploaded' AND phash IS NOT NULL"
        ).fetchall()
    for row in rows:
        try:
            existing = imagehash.hex_to_hash(row["phash"])
            if new_hash - existing < threshold:
                return True
        except Exception:
            continue
    return False


def register_clip(
    file_path: Path,
    source_vod: Path,
    highlight_ts: int,
    phash: Optional[str] = None,
    content_key_override: Optional[str] = None,
    spike_energy: Optional[float] = None,
) -> Optional[int]:
    key = content_key_override or content_key(str(source_vod), highlight_ts)
    if is_duplicate_content(str(source_vod), highlight_ts):
        log.warning("Duplicate content already uploaded: %s @ %ds", source_vod.name, highlight_ts)
        return None
    if phash and is_duplicate_phash(phash):
        log.warning("Duplicate perceptual hash for %s", file_path.name)
        return None

    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO clips (
                    file_path, source_vod, highlight_ts, content_key, phash,
                    status, created_at, spike_energy
                )
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (str(file_path), str(source_vod), highlight_ts, key, phash, now, spike_energy),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            log.warning("Clip already registered: %s", key)
            row = conn.execute(
                "SELECT id, file_path FROM clips WHERE content_key = ?", (key,)
            ).fetchone()
            if row and row["file_path"] == str(file_path):
                return row["id"]
            return None


def update_clip(clip_id: int, **fields) -> None:
    if not fields:
        return
    if "tags" in fields and isinstance(fields["tags"], list):
        fields["tags"] = json.dumps(fields["tags"])
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [clip_id]
    with _connect() as conn:
        conn.execute(f"UPDATE clips SET {cols} WHERE id = ?", vals)


def get_clip(clip_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_clip_by_path(file_path: Path) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM clips WHERE file_path = ? ORDER BY id DESC LIMIT 1",
            (str(file_path),),
        ).fetchone()
        if row:
            return _row_to_dict(row)
        row = conn.execute(
            "SELECT * FROM clips WHERE file_path LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%{file_path.name}",),
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_best_scored(min_hype: Optional[float] = None) -> Optional[dict]:
    min_hype = min_hype if min_hype is not None else config.MIN_HYPE_SCORE
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM clips
            WHERE status = 'scored' AND hype_score >= ?
            ORDER BY hype_score DESC, created_at ASC
            LIMIT 1
            """,
            (min_hype,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_clips(status: Optional[str] = None, limit: int = 100) -> list[dict]:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM clips WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM clips ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_clips_by_source(source_vod: str | Path, statuses: Optional[tuple[str, ...]] = None) -> list[dict]:
    """Clips from one VOD, optionally filtered by status."""
    path = str(source_vod)
    with _connect() as conn:
        if statuses:
            placeholders = ",".join("?" * len(statuses))
            rows = conn.execute(
                f"""
                SELECT * FROM clips
                WHERE source_vod = ? AND status IN ({placeholders})
                ORDER BY spike_energy DESC, highlight_ts ASC
                """,
                (path, *statuses),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM clips WHERE source_vod = ? ORDER BY spike_energy DESC",
                (path,),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_scored_pending() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM clips WHERE status = 'scored'
            ORDER BY hype_score DESC, created_at ASC
            """
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_uploaded(limit: int = 10) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM clips WHERE status = 'uploaded'
            ORDER BY uploaded_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_by_status() -> dict[str, int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM clips GROUP BY status"
        ).fetchall()
    return {r["status"]: r["cnt"] for r in rows}


def count_rejected() -> int:
    counts = count_by_status()
    return counts.get("rejected", 0)


def get_tonights_pick(min_hype: Optional[float] = None) -> Optional[dict]:
    return get_best_scored(min_hype)


def mark_uploaded(clip_id: int, youtube_id: str, title: str, description: str, tags: list) -> None:
    now = datetime.now(timezone.utc).isoformat()
    update_clip(
        clip_id,
        status="uploaded",
        youtube_id=youtube_id,
        title=title,
        description=description,
        tags=tags,
        uploaded_at=now,
    )


def get_last_upload() -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM clips WHERE status = 'uploaded' ORDER BY uploaded_at DESC LIMIT 1"
        ).fetchone()
    return _row_to_dict(row) if row else None


def delete_clip_record(clip_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))


def clear_all_clip_records() -> int:
    """Remove every clip row (after media files were deleted)."""
    with _connect() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM clips")
        count = int(cur.fetchone()[0])
        conn.execute("DELETE FROM clips")
    return count


init_db()
