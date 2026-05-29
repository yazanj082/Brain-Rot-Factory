"""
Brain-Rot Shorts Factory — OCR prefilter for obvious bad clips
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

BAD_KEYWORDS = (
    "REPLAY", "PLAY OF THE GAME", "PLAY OF GAME", "DEFEAT", "VICTORY",
    "ELIMINATED", "YOU DIED", "RESPAWN", "GAME OVER", "SPECTATING",
    "HERO SELECT", "MATCH COMPLETE",
)


def _ocr_frame(frame_path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
        text = pytesseract.image_to_string(Image.open(frame_path))
        return text.upper()
    except ImportError:
        return ""
    except Exception as exc:
        log.debug("OCR skip %s: %s", frame_path.name, exc)
        return ""


def check_frames(frames: List[Path]) -> Tuple[bool, Optional[str]]:
    """
    Returns (should_reject, reason).
    Rejects if bad keywords found on multiple frames.
    """
    if not frames:
        return False, None

    hits = 0
    found_kw = None
    for frame in frames[:4]:
        text = _ocr_frame(frame)
        for kw in BAD_KEYWORDS:
            if kw in text:
                hits += 1
                found_kw = kw
                break

    if hits >= 2:
        return True, f"OCR detected '{found_kw}' on {hits} frames"
    if hits == 1 and len(frames) <= 4:
        return True, f"OCR detected '{found_kw}'"
    return False, None
