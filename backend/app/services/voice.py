"""Voice reporting pipeline: audio -> Sarvam STT -> English -> structured draft.

Live mode (SARVAM_API_KEY set):
  1. /speech-to-text in the spoken language (shown to the donor verbatim)
  2. /speech-to-text-translate to English
  3. sarvam-m chat completion for structured extraction, falling back to the
     deterministic rule-based extractor if the LLM call fails.

Demo mode (no key): returns a fixed, clearly-labelled sample Kannada report.
The returned payload always includes `simulated: true/false`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from . import sarvam
from .extraction import build_draft, rule_based_extract

log = logging.getLogger("festiveplate.voice")

DEMO_SAMPLES: Dict[str, Dict[str, str]] = {
    "kn": {
        "transcript": (
            "ನಮಸ್ಕಾರ, ನಾನು ಎಲೆಕ್ಟ್ರಾನಿಕ್ ಸಿಟಿಯ ಶುಭ ಕಲ್ಯಾಣ ಮಂಟಪದಿಂದ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. "
            "ಮದುವೆ ಊಟದಲ್ಲಿ ನೂರ ಐವತ್ತು ಸಸ್ಯಾಹಾರಿ ಊಟ ಉಳಿದಿದೆ - ಅನ್ನ, ಸಾಂಬಾರ್, ಪಲ್ಯ ಮತ್ತು ಪಾಯಸ. "
            "ಒಂದು ಗಂಟೆ ಹಿಂದೆ ತಯಾರಿಸಲಾಗಿದೆ, ಬಿಸಿಯಾಗಿ ಇಡಲಾಗಿದೆ. ದಯವಿಟ್ಟು ಮೂರು ಗಂಟೆಯೊಳಗೆ ತೆಗೆದುಕೊಂಡು ಹೋಗಿ."
        ),
        "english": (
            "Hello, I am speaking from Shubha Kalyana Mantapa in Electronic City. One hundred and fifty vegetarian "
            "meals are left over from the wedding dinner - rice, sambar, palya and payasa. They were prepared one "
            "hour ago and are being kept hot. Please pick up within three hours."
        ),
        "venue": "Shubha Kalyana Mantapa (DEMO)",
    },
    "hi": {
        "transcript": (
            "नमस्ते, मैं कोरमंगला के एक रेस्टोरेंट से बोल रहा हूँ। हमारे पास साठ शाकाहारी थाली बची हैं - दाल, चावल और रोटी। "
            "खाना दो घंटे पहले बना था और फ्रिज में रखा है। कृपया चार घंटे के अंदर ले जाइए।"
        ),
        "english": (
            "Hello, I am speaking from a restaurant in Koramangala. We have sixty vegetarian plates left - dal, rice "
            "and roti. The food was prepared two hours ago and is refrigerated. Please pick up within four hours."
        ),
        "venue": "Koramangala restaurant (DEMO)",
    },
    "en": {
        "transcript": (
            "Hi, this is a caterer in HSR Layout. We have eighty vegetarian meals of veg pulao and curd rice, "
            "prepared thirty minutes ago and kept hot. Please pick up within two hours."
        ),
        "english": (
            "Hi, this is a caterer in HSR Layout. We have eighty vegetarian meals of veg pulao and curd rice, "
            "prepared thirty minutes ago and kept hot. Please pick up within two hours."
        ),
        "venue": "HSR Layout caterer (DEMO)",
    },
}


def _extract(english: str, live: bool) -> Dict[str, Any]:
    method = "rule_based"
    raw: Dict[str, Any] = {}
    llm_error: Optional[str] = None
    if live:
        try:
            raw = sarvam.extract_fields_llm(english)
            method = "sarvam_llm"
        except sarvam.SarvamError as exc:
            llm_error = str(exc)
            log.warning("Sarvam extraction failed, using rule-based extractor: %s", exc)
    rules = rule_based_extract(english)
    # Fill gaps the LLM left empty with deterministic rule output (never invent values).
    for k, v in rules.items():
        if raw.get(k) in (None, "", "null"):
            raw[k] = v
    result = build_draft(raw)
    result["extraction_method"] = method if method == "sarvam_llm" else "rule_based"
    if llm_error:
        result["notes"].append("Sarvam LLM extraction failed; used rule-based extraction instead.")
        result["llm_error"] = llm_error
    return result


def demo_report(language: str) -> Dict[str, Any]:
    sample = DEMO_SAMPLES.get(language, DEMO_SAMPLES["kn"])
    result = _extract(sample["english"], live=False)
    result["draft"]["title"] = f"Surplus wedding meals from {sample['venue']}" if language == "kn" else f"Surplus food from {sample['venue']}"
    return {
        "simulated": True,
        "mode": "DEMO - sample input, Sarvam AI not called",
        "language": language,
        "transcript": sample["transcript"],
        "english_text": sample["english"],
        **result,
    }


def process_audio(audio: bytes, filename: str, content_type: str, language: Optional[str]) -> Dict[str, Any]:
    stt = sarvam.speech_to_text(audio, filename, content_type, language)
    eng = sarvam.speech_to_english(audio, filename, content_type)
    result = _extract(eng["transcript"], live=True)
    return {
        "simulated": False,
        "mode": "LIVE - Sarvam AI",
        "language": (stt.get("language_code") or language or "unknown"),
        "transcript": stt["transcript"],
        "english_text": eng["transcript"],
        **result,
    }


def process_text(text: str, language: str) -> Dict[str, Any]:
    """Typed report (any supported language). Non-English text is translated via Sarvam when configured."""
    live = sarvam.get_settings().sarvam_configured
    english = text
    translated_by = "none"
    if language != "en":
        if not live:
            return {
                "simulated": True,
                "mode": "DEMO - translation unavailable without SARVAM_API_KEY",
                "language": language,
                "transcript": text,
                "english_text": None,
                "draft": {},
                "missing_fields": [],
                "notes": ["Non-English text needs Sarvam translation. Configure SARVAM_API_KEY or type in English."],
                "extraction_method": "none",
            }
        english = sarvam.translate(text, language, "en")
        translated_by = "sarvam"
    result = _extract(english, live=live)
    return {
        "simulated": False,
        "mode": "LIVE - Sarvam AI" if live else "Rule-based extraction (no AI call)",
        "language": language,
        "transcript": text,
        "english_text": english,
        "translated_by": translated_by,
        **result,
    }
