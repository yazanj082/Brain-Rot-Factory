"""
Brain-Rot Shorts Factory — Ollama HTTP client
"""

import base64
import io
import json
import logging
import re
from pathlib import Path
from typing import Any, List, Optional

import httpx

import config

log = logging.getLogger(__name__)

_HTTP_TIMEOUT = httpx.Timeout(
    connect=15.0,
    read=config.OLLAMA_TIMEOUT,
    write=60.0,
    pool=15.0,
)

_installed_models: Optional[set[str]] = None


def is_ollama_available() -> bool:
    try:
        r = httpx.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False


def list_models() -> set[str]:
    global _installed_models
    if _installed_models is not None:
        return _installed_models
    try:
        r = httpx.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5.0)
        r.raise_for_status()
        _installed_models = {m["name"] for m in r.json().get("models", [])}
    except Exception:
        _installed_models = set()
    return _installed_models


def model_available(model: str) -> bool:
    models = list_models()
    if model in models:
        return True
    # ollama tags may omit :latest
    base = model.split(":")[0]
    return any(m == model or m.startswith(base + ":") for m in models)


def _encode_image(path: Path) -> str:
    data = path.read_bytes()
    return base64.b64encode(data).decode("utf-8")


def _unwrap_json_object(parsed: Any) -> dict[str, Any]:
    """Ensure vision scoring always gets a dict."""
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                log.warning("Ollama returned a JSON array; using first object element")
                return item
    raise TypeError(f"Expected JSON object, got {type(parsed).__name__}")


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise json.JSONDecodeError("Empty response", text, 0)

    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()

    decoder = json.JSONDecoder()

    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start < 0:
            continue
        try:
            parsed, _end = decoder.raw_decode(text, start)
            return _unwrap_json_object(parsed)
        except (json.JSONDecodeError, TypeError):
            pass

    end = text.rfind("}")
    start = text.find("{")
    if start >= 0 and end > start:
        return _unwrap_json_object(json.loads(text[start : end + 1]))

    parsed = json.loads(text)
    return _unwrap_json_object(parsed)


def chat(
    model: str,
    prompt: str,
    images: Optional[List[Path]] = None,
    system: Optional[str] = None,
) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    user_msg: dict[str, Any] = {"role": "user", "content": prompt}
    if images:
        user_msg["images"] = [_encode_image(p) for p in images]
    messages.append(user_msg)

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_predict": 512,
            "temperature": 0.2,
        },
    }

    url = f"{config.OLLAMA_HOST}/api/chat"
    log.info(
        "Ollama request: model=%s images=%d timeout=%ss",
        model, len(images or []), config.OLLAMA_TIMEOUT,
    )
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    content = data.get("message", {}).get("content", "")
    log.info("Ollama response from %s (%d chars)", model, len(content))
    return content


def chat_json(
    model: str,
    prompt: str,
    images: Optional[List[Path]] = None,
    system: Optional[str] = None,
) -> str:
    """Chat with Ollama JSON mode enabled (single object response)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    user_msg: dict[str, Any] = {"role": "user", "content": prompt}
    if images:
        user_msg["images"] = [_encode_image(p) for p in images]
    messages.append(user_msg)

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "num_predict": 512,
            "temperature": 0.2,
        },
    }

    url = f"{config.OLLAMA_HOST}/api/chat"
    log.info(
        "Ollama JSON request: model=%s images=%d timeout=%ss",
        model, len(images or []), config.OLLAMA_TIMEOUT,
    )
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    content = data.get("message", {}).get("content", "")
    log.info("Ollama JSON response from %s (%d chars)", model, len(content))
    return content


def generate_json(
    model: str,
    prompt: str,
    images: Optional[List[Path]] = None,
    system: Optional[str] = None,
) -> dict[str, Any]:
    last_error: Optional[Exception] = None
    strict_prompt = (
        prompt
        + "\n\nRespond with ONE JSON object only (not an array). "
        "Required keys: is_live_gameplay, has_replay_or_death_cam, player_doing_well, "
        "hype_score, trim_start_sec, trim_end_sec, reject, reject_reason, summary."
    )

    for attempt in range(config.OLLAMA_MAX_RETRIES):
        try:
            use_prompt = strict_prompt if attempt > 0 else prompt
            try:
                raw = chat_json(model, use_prompt, images, system)
            except httpx.HTTPError:
                raw = chat(model, use_prompt, images, system)
            return _parse_json_response(raw)
        except (json.JSONDecodeError, TypeError, httpx.HTTPError, KeyError, RuntimeError) as exc:
            last_error = exc
            log.warning(
                "Ollama JSON attempt %d/%d (%s) failed: %s",
                attempt + 1,
                config.OLLAMA_MAX_RETRIES,
                model,
                exc,
            )

    raise RuntimeError(f"Ollama failed after {config.OLLAMA_MAX_RETRIES} retries: {last_error}")
