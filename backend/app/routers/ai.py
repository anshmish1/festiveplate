from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from .. import schemas
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import FoodListing, User
from ..ratelimit import rate_limit
from ..services import sarvam, voice
from ..services.flags import flag_service
from ..services.matching import rank_ngos
from ..services.monitoring import metrics, record_incident
from ..services.prediction import predict_surplus
from ..services.presenter import access_level
from ..services.storage import read_audio

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(rate_limit("ai"))])


def _utc_draft(out: Dict[str, Any]) -> Dict[str, Any]:
    """Draft datetimes are naive UTC internally; send them as explicit UTC ISO strings."""
    draft = out.get("draft") or {}
    for k, v in list(draft.items()):
        if isinstance(v, datetime):
            draft[k] = schemas._ser_utc(v)
    return out


def _require_flag(db: Session, name: str) -> None:
    if not flag_service.is_enabled(db, name):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Feature '{name}' is currently disabled.")


@router.get("/status")
def ai_status(user: User = Depends(get_current_user)) -> Dict[str, Any]:
    s = get_settings()
    return {
        "sarvam_configured": s.sarvam_configured,
        "mode": "LIVE" if s.sarvam_configured else "DEMO",
        "message": "Sarvam AI connected via backend credentials." if s.sarvam_configured
        else "SARVAM_API_KEY not set: voice uses clearly-labelled DEMO sample inputs.",
        "models": {"stt": s.sarvam_stt_model, "stt_translate": s.sarvam_stt_translate_model,
                   "translate": s.sarvam_translate_model, "chat": s.sarvam_chat_model},
    }


def _sarvam_failure(db: Session, exc: Exception, op: str) -> HTTPException:
    metrics.integration(f"sarvam_{op}", "error")
    record_incident(db, fingerprint=f"sarvam:{op}", category="INTEGRATION", severity="MEDIUM",
                    title=f"Sarvam {op} call failed", details={"error": str(exc)[:300]})
    return HTTPException(status.HTTP_502_BAD_GATEWAY, f"Sarvam AI {op} failed. You can enter details manually. ({exc})")


@router.post("/voice/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: Optional[str] = Form(default="kn", pattern="^(en|kn|hi)$"),
    user: User = Depends(require_roles("DONOR")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Speech -> structured DRAFT. Nothing is published until the donor confirms."""
    _require_flag(db, "voice_reporting")
    data = await read_audio(audio)
    if not get_settings().sarvam_configured:
        out = voice.demo_report(language or "kn")
        out["notes"].insert(0, "Your recording was received but NOT sent anywhere: Sarvam AI is not configured, so a DEMO sample transcript is shown.")
        return _utc_draft(out)
    try:
        out = voice.process_audio(data, audio.filename or "audio.webm", (audio.content_type or "audio/webm").split(";")[0], language)
        metrics.integration("sarvam_stt", "ok")
        return _utc_draft(out)
    except sarvam.SarvamError as exc:
        raise _sarvam_failure(db, exc, "speech-to-text")


@router.post("/voice/demo")
def voice_demo(language: str = "kn", user: User = Depends(require_roles("DONOR")), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Clearly-labelled DEMO: returns a sample report without calling any external service."""
    _require_flag(db, "voice_reporting")
    if language not in voice.DEMO_SAMPLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "language must be en, kn or hi")
    return _utc_draft(voice.demo_report(language))


@router.post("/extract")
def extract_text(body: schemas.TextReportRequest, user: User = Depends(require_roles("DONOR")), db: Session = Depends(get_db)) -> Dict[str, Any]:
    _require_flag(db, "voice_reporting")
    try:
        return _utc_draft(voice.process_text(body.text, body.language))
    except sarvam.SarvamError as exc:
        raise _sarvam_failure(db, exc, "translate")


@router.post("/translate")
def translate(body: schemas.TranslateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Dict[str, Any]:
    if not get_settings().sarvam_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Translation requires SARVAM_API_KEY (not configured in this demo).")
    try:
        text = sarvam.translate(body.text, body.source, body.target)
        metrics.integration("sarvam_translate", "ok")
        return {"translated_text": text, "source": body.source, "target": body.target, "provider": "sarvam"}
    except sarvam.SarvamError as exc:
        raise _sarvam_failure(db, exc, "translate")


@router.post("/predict-surplus")
def predict(body: schemas.PredictRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Dict[str, Any]:
    _require_flag(db, "surplus_prediction")
    return predict_surplus(
        event_type=body.event_type, planned_servings=body.planned_servings, expected_attendance=body.expected_attendance,
        actual_attendance=body.actual_attendance, historical=[h.model_dump() for h in body.historical],
    )


@router.get("/explain-match/{listing_id}")
def explain_match(listing_id: int, user: User = Depends(require_roles("DONOR", "ADMIN")), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Plain-language explanation of matching for this listing, including why NGOs were excluded."""
    l = db.get(FoodListing, listing_id)
    if l is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Donation not found")
    if access_level(db, l, user) != "full":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Donation not found")
    eligible, excluded, emergency = rank_ngos(db, l, flag_service.is_enabled(db, "emergency_matching"))
    return {
        "emergency_mode": emergency,
        "method": "Deterministic weighted scoring (distance 35, capacity 20, reachability 20, availability 10, preference 10, vehicle 5). Only administrator-verified NGOs are considered.",
        "ranked": [{"ngo": c.ngo.organization_name, "score": c.score, "distance_km": c.distance_km, "explanation": c.explanation} for c in eligible],
        "excluded": [{"ngo": c.ngo.organization_name, "reasons": c.exclusion_reasons} for c in excluded],
    }
