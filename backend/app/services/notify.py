"""In-app notifications with optional Sarvam translation into the recipient's language.

Translation failures never drop a notification: the English text is delivered,
the row is marked FAILED with the error (so it shows in the health dashboard),
and an incident is recorded.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Notification, User
from . import sarvam
from .flags import flag_service
from .monitoring import metrics, record_incident

log = logging.getLogger("festiveplate.notify")


def notify(
    db: Session,
    user: User,
    *,
    type: str,
    title: str,
    body: str,
    listing_id: Optional[int] = None,
) -> Notification:
    """Create a notification row. Caller commits (incidents commit separately)."""
    if not user.notify_in_app:
        n = Notification(user_id=user.id, listing_id=listing_id, type=type, title=title, body=body, status="READ",
                         language="en", translation_source="none", error="Recipient disabled in-app notifications")
        db.add(n)
        return n

    lang = user.preferred_language or "en"
    text, original, source, status, error = body, None, "none", "SENT", None
    if lang != "en" and flag_service.is_enabled(db, "multilingual_notifications"):
        if get_settings().sarvam_configured:
            try:
                text = sarvam.translate(body, "en", lang)
                original, source = body, "sarvam"
                metrics.integration("sarvam_translate", "ok")
            except sarvam.SarvamError as exc:
                metrics.integration("sarvam_translate", "error")
                status, error, source = "FAILED", f"Translation to {lang} failed: {exc}"[:500], "failed"
                record_incident(
                    db,
                    fingerprint=f"notification-translation:{lang}",
                    category="NOTIFICATION_FAILURE",
                    severity="MEDIUM",
                    title=f"Notification translation to '{lang}' failed",
                    details={"user_id": user.id, "type": type, "error": str(exc)[:300]},
                )
        else:
            source = "unavailable"
            error = "Sarvam not configured; delivered in English"
    n = Notification(
        user_id=user.id, listing_id=listing_id, type=type, title=title, body=text, original_body=original,
        language=lang if source == "sarvam" else "en", translation_source=source, status=status, error=error,
    )
    db.add(n)
    if user.notify_sms:
        db.add(Notification(user_id=user.id, listing_id=listing_id, type=type, channel="SMS_SIMULATED", title=title,
                            body=text, language=n.language, translation_source=source, status="SENT",
                            error="SIMULATED channel - no SMS provider configured"))
    return n


def notify_many(db: Session, users: Iterable[User], **kwargs) -> None:
    for u in users:
        notify(db, u, **kwargs)
