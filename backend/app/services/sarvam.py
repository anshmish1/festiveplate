"""Sarvam AI client (speech-to-text, speech-to-text-translate, translation, chat).

Credentials come only from the backend environment (SARVAM_API_KEY). When the key
is absent, callers must use the clearly-labelled demo mode instead - this module
never fabricates a successful Sarvam response.

API reference: https://docs.sarvam.ai/api-reference-docs
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import httpx

from ..config import get_settings

log = logging.getLogger("festiveplate.sarvam")

LANG_CODES = {"en": "en-IN", "kn": "kn-IN", "hi": "hi-IN"}


class SarvamError(RuntimeError):
    pass


class SarvamNotConfigured(SarvamError):
    pass


def _headers() -> Dict[str, str]:
    s = get_settings()
    if not s.sarvam_api_key:
        raise SarvamNotConfigured("SARVAM_API_KEY is not configured")
    return {"api-subscription-key": s.sarvam_api_key}


def _url(path: str) -> str:
    return get_settings().sarvam_base_url.rstrip("/") + path


def _post(path: str, **kwargs: Any) -> Dict[str, Any]:
    s = get_settings()
    try:
        resp = httpx.post(_url(path), headers=_headers(), timeout=s.sarvam_timeout_seconds, **kwargs)
    except httpx.HTTPError as exc:
        raise SarvamError(f"Sarvam request to {path} failed: {exc}") from exc
    if resp.status_code >= 400:
        raise SarvamError(f"Sarvam {path} returned HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise SarvamError(f"Sarvam {path} returned non-JSON response") from exc


def speech_to_text(audio: bytes, filename: str, content_type: str, language: Optional[str]) -> Dict[str, Any]:
    """Transcribe in the spoken language (Kannada / Hindi / English)."""
    s = get_settings()
    data = {"model": s.sarvam_stt_model, "language_code": LANG_CODES.get(language or "", "unknown")}
    out = _post("/speech-to-text", files={"file": (filename, audio, content_type)}, data=data)
    if "transcript" not in out:
        raise SarvamError("Sarvam speech-to-text response missing 'transcript'")
    return out


def speech_to_english(audio: bytes, filename: str, content_type: str) -> Dict[str, Any]:
    """Transcribe and translate speech directly into English (used for field extraction)."""
    s = get_settings()
    out = _post(
        "/speech-to-text-translate",
        files={"file": (filename, audio, content_type)},
        data={"model": s.sarvam_stt_translate_model},
    )
    if "transcript" not in out:
        raise SarvamError("Sarvam speech-to-text-translate response missing 'transcript'")
    return out


def translate(text: str, source: str, target: str) -> str:
    if source == target or not text.strip():
        return text
    s = get_settings()
    out = _post(
        "/translate",
        json={
            "input": text[:1000],
            "source_language_code": LANG_CODES.get(source, "auto"),
            "target_language_code": LANG_CODES[target],
            "model": s.sarvam_translate_model,
            "mode": "formal",
        },
    )
    translated = out.get("translated_text")
    if not translated:
        raise SarvamError("Sarvam translate response missing 'translated_text'")
    return translated


EXTRACTION_PROMPT = """You convert a food donor's spoken report (already translated to English) into JSON.
Return ONLY a JSON object with these keys (use null when the speaker did not say it - never guess):
  food_type (string), food_category (one of VEG, NON_VEG, EGG, MIXED),
  portions (integer), prepared_hours_ago (number), prepared_at_local_time (string HH:MM 24h),
  pickup_within_hours (number), pickup_deadline_local_time (string HH:MM 24h),
  storage_condition (one of HOT_HELD, REFRIGERATED, ROOM_TEMPERATURE, FROZEN),
  location (string), venue_name (string), allergens (string).
"""


def extract_fields_llm(english_text: str) -> Dict[str, Any]:
    s = get_settings()
    out = _post(
        "/v1/chat/completions",
        json={
            "model": s.sarvam_chat_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": english_text[:2000]},
            ],
        },
    )
    try:
        content = out["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SarvamError("Unexpected Sarvam chat response shape") from exc
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < 0:
        raise SarvamError("Sarvam chat response did not contain JSON")
    try:
        return json.loads(content[start : end + 1])
    except ValueError as exc:
        raise SarvamError("Sarvam chat response JSON could not be parsed") from exc
