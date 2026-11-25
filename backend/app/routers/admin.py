from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..deps import audit, require_roles
from ..models import (
    ApplicationIncident,
    AuditLog,
    FeatureFlagAudit,
    FeatureFlagOverride,
    FoodListing,
    FoodSafetyCheck,
    NgoProfile,
    Notification,
    User,
)
from ..services import lifecycle, workflow
from ..services.flags import FLAG_DEFINITIONS, flag_service
from ..services.monitoring import SIMULATED_NUDGEBEE_INSIGHTS, incident_summary, metrics, nudgebee_status
from ..services.notify import notify
from ..services.presenter import listing_detail, listing_out
from ..services.timegeo import utcnow

router = APIRouter(prefix="/api/admin", tags=["admin"])
Admin = Depends(require_roles("ADMIN"))


# ---------- Users ----------
@router.get("/users", response_model=List[schemas.UserOut])
def users(role: Optional[str] = None, q: Optional[str] = None, admin: User = Admin, db: Session = Depends(get_db)):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(func.lower(User.email).like(like) | func.lower(User.full_name).like(like))
    return query.order_by(User.created_at.desc()).limit(500).all()


@router.patch("/users/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, body: schemas.UserAdminUpdate, request: Request, admin: User = Admin, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if u.id == admin.id and not body.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate your own account.")
    u.is_active = body.is_active
    audit(db, admin, "SET_USER_ACTIVE", "user", u.id, {"is_active": body.is_active}, request)
    db.commit()
    return u


# ---------- NGO verification ----------
@router.get("/ngos", response_model=List[schemas.NgoProfileOut])
def ngos(verification_status: Optional[str] = None, admin: User = Admin, db: Session = Depends(get_db)):
    q = db.query(NgoProfile)
    if verification_status:
        q = q.filter(NgoProfile.verification_status == verification_status)
    return q.order_by(NgoProfile.created_at.desc()).all()


@router.post("/ngos/{ngo_id}/verify", response_model=schemas.NgoProfileOut)
def verify_ngo(ngo_id: int, body: schemas.VerifyNgoRequest, request: Request, admin: User = Admin, db: Session = Depends(get_db)):
    ngo = db.get(NgoProfile, ngo_id)
    if ngo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NGO not found")
    old = ngo.verification_status
    ngo.verification_status = body.decision
    ngo.verification_notes = body.notes
    ngo.verified_by = admin.id
    ngo.verified_at = utcnow()
    audit(db, admin, "VERIFY_NGO", "ngo_profile", ngo.id, {"from": old, "to": body.decision, "notes": body.notes}, request)
    db.commit()
    messages = {
        "VERIFIED": "Your organisation has been verified. You can now receive matched donations.",
        "REJECTED": f"Your verification was not approved. Notes: {body.notes or '-'}",
        "SUSPENDED": f"Your organisation has been suspended from receiving donations. Notes: {body.notes or '-'}",
    }
    notify(db, ngo.user, type="NGO_VERIFICATION", title=f"Verification status: {body.decision}", body=messages[body.decision])
    db.commit()
    if body.decision == "VERIFIED":
        # Newly verified NGO may be a good match for currently open donations.
        for l in db.query(FoodListing).filter(FoodListing.status.in_(lifecycle.OPEN_FOR_ACCEPTANCE)).all():
            workflow.match_and_notify(db, l, admin)
    return ngo


# ---------- Listings & safety ----------
@router.get("/listings", response_model=List[schemas.ListingOut])
def listings(status_filter: Optional[str] = Query(default=None, alias="status"), admin: User = Admin, db: Session = Depends(get_db)):
    lifecycle.expire_overdue(db)
    q = db.query(FoodListing)
    if status_filter:
        q = q.filter(FoodListing.status == status_filter)
    return [listing_out(db, l, admin, "full") for l in q.order_by(FoodListing.created_at.desc()).limit(500).all()]


@router.get("/safety-flags")
def safety_flags(admin: User = Admin, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    lifecycle.expire_overdue(db)
    out = []
    for l in db.query(FoodListing).filter(FoodListing.status == "FLAGGED").order_by(FoodListing.created_at.desc()).all():
        check = l.safety_checks[-1] if l.safety_checks else None
        out.append({"listing": listing_out(db, l, admin, "full").model_dump(mode="json"),
                    "issues": check.issues if check else [], "check_id": check.id if check else None})
    return out


@router.post("/listings/{listing_id}/safety-review", response_model=schemas.ListingDetail)
def safety_review(listing_id: int, body: schemas.SafetyReviewRequest, request: Request, admin: User = Admin, db: Session = Depends(get_db)):
    lifecycle.expire_overdue(db)
    l = db.get(FoodListing, listing_id)
    if l is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Donation not found")
    workflow.review_safety(db, l, admin, body.decision, body.notes)
    audit(db, admin, "SAFETY_REVIEW", "food_listing", l.id, {"decision": body.decision, "notes": body.notes}, request)
    db.commit()
    return listing_detail(db, l, admin)


# ---------- Analytics ----------
@router.get("/analytics")
def analytics(admin: User = Admin, db: Session = Depends(get_db)) -> Dict[str, Any]:
    by_status = dict(db.query(FoodListing.status, func.count()).group_by(FoodListing.status).all())
    by_role = dict(db.query(User.role, func.count()).group_by(User.role).all())
    by_ngo = dict(db.query(NgoProfile.verification_status, func.count()).group_by(NgoProfile.verification_status).all())
    by_area = [
        {"area": a, "listings": c}
        for a, c in db.query(FoodListing.area, func.count()).group_by(FoodListing.area).order_by(func.count().desc()).limit(10).all()
    ]
    flags_open = db.query(FoodListing).filter(FoodListing.status == "FLAGGED").count()
    checks_flagged = db.query(FoodSafetyCheck).filter(FoodSafetyCheck.result == "FLAGGED").count()
    return {
        "listings_by_status": by_status,
        "users_by_role": by_role,
        "ngos_by_verification": by_ngo,
        "top_areas": by_area,
        "open_safety_flags": flags_open,
        "total_safety_flags_raised": checks_flagged,
        "failed_notifications": db.query(Notification).filter(Notification.status == "FAILED").count(),
    }


@router.get("/audit-logs")
def audit_logs(limit: int = 100, admin: User = Admin, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(max(1, min(limit, 500))).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.id.in_({r.actor_id for r in rows if r.actor_id})).all()}
    return [
        {"id": r.id, "actor": names.get(r.actor_id, "anonymous"), "action": r.action, "entity_type": r.entity_type,
         "entity_id": r.entity_id, "details": r.details, "created_at": schemas._ser_utc(r.created_at)}
        for r in rows
    ]


# ---------- Feature flags ----------
@router.get("/flags")
def flags(admin: User = Admin, db: Session = Depends(get_db)) -> Dict[str, Any]:
    audit_rows = db.query(FeatureFlagAudit).order_by(FeatureFlagAudit.created_at.desc()).limit(50).all()
    return {
        "connection": flag_service.connection_status(),
        "flags": flag_service.evaluate_all(db),
        "audit": [
            {"flag_name": a.flag_name, "old_value": a.old_value, "new_value": a.new_value, "source": a.source,
             "reason": a.reason, "changed_by": a.changed_by, "created_at": schemas._ser_utc(a.created_at)}
            for a in audit_rows
        ],
    }


@router.put("/flags/{name}/override")
def set_override(name: str, body: schemas.FlagOverrideRequest, admin: User = Admin, db: Session = Depends(get_db)):
    if name not in FLAG_DEFINITIONS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown flag")
    old = flag_service.is_enabled(db, name)
    o = db.get(FeatureFlagOverride, name)
    if o is None:
        o = FeatureFlagOverride(flag_name=name, enabled=body.enabled, updated_by=admin.id)
        db.add(o)
    else:
        o.enabled, o.updated_by = body.enabled, admin.id
    db.add(FeatureFlagAudit(flag_name=name, old_value=old, new_value=body.enabled, source="local_override", changed_by=admin.id, reason=body.reason))
    db.commit()
    return {"ok": True, "flags": flag_service.evaluate_all(db)}


@router.delete("/flags/{name}/override")
def clear_override(name: str, admin: User = Admin, db: Session = Depends(get_db)):
    o = db.get(FeatureFlagOverride, name)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No override set")
    old = o.enabled
    db.delete(o)
    db.flush()
    new = flag_service.is_enabled(db, name)
    db.add(FeatureFlagAudit(flag_name=name, old_value=old, new_value=new, source="override_cleared", changed_by=admin.id,
                            reason="Override removed; value now from Flagsmith or default"))
    db.commit()
    return {"ok": True, "flags": flag_service.evaluate_all(db)}


# ---------- System health / incidents ----------
@router.get("/system/health")
def system_health(admin: User = Admin, db: Session = Depends(get_db)) -> Dict[str, Any]:
    from ..config import get_settings

    s = get_settings()
    failed = db.query(Notification).filter(Notification.status == "FAILED").order_by(Notification.created_at.desc()).limit(20).all()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "backend": {**metrics.snapshot(), "database_ok": db_ok, "environment": s.app_env},
        "integrations": {
            "sarvam": {"configured": s.sarvam_configured, "mode": "LIVE" if s.sarvam_configured else "DEMO (simulated sample inputs)"},
            "flagsmith": flag_service.connection_status(),
            "nudgebee": nudgebee_status(),
        },
        "notifications": {
            "failed_total": db.query(Notification).filter(Notification.status == "FAILED").count(),
            "recent_failures": [schemas.NotificationOut.model_validate(n).model_dump(mode="json") for n in failed],
        },
        "incident_summary": incident_summary(db),
        "simulated_ai_insights": [] if nudgebee_status()["live"] else SIMULATED_NUDGEBEE_INSIGHTS,
    }


@router.get("/incidents", response_model=List[schemas.IncidentOut])
def incidents(status_filter: Optional[str] = Query(default=None, alias="status"), admin: User = Admin, db: Session = Depends(get_db)):
    q = db.query(ApplicationIncident)
    if status_filter:
        q = q.filter(ApplicationIncident.status == status_filter)
    return q.order_by(ApplicationIncident.last_seen.desc()).limit(200).all()


@router.post("/incidents/{incident_id}/resolve", response_model=schemas.IncidentOut)
def resolve_incident(incident_id: int, request: Request, admin: User = Admin, db: Session = Depends(get_db)):
    inc = db.get(ApplicationIncident, incident_id)
    if inc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    inc.status, inc.resolved_at, inc.resolved_by = "RESOLVED", utcnow(), admin.id
    audit(db, admin, "RESOLVE_INCIDENT", "application_incident", inc.id, {}, request)
    db.commit()
    return inc


@router.post("/notifications/{notification_id}/retry", response_model=schemas.NotificationOut)
def retry_notification(notification_id: int, admin: User = Admin, db: Session = Depends(get_db)):
    """Investigate/retry a failed notification: re-run translation and re-deliver."""
    n = db.get(Notification, notification_id)
    if n is None or n.status != "FAILED":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Failed notification not found")
    user = db.get(User, n.user_id)
    new = notify(db, user, type=n.type, title=n.title, body=n.original_body or n.body, listing_id=n.listing_id)
    n.error = (n.error or "") + " | retried"
    n.status = "READ"  # superseded by retry
    db.commit()
    return new
