from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..deps import audit, get_current_user
from ..models import DonorProfile, NgoProfile, Notification, User, VolunteerProfile
from ..services.flags import flag_service
from ..services.timegeo import utcnow

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Dict[str, Any]:
    out: Dict[str, Any] = {"user": schemas.UserOut.model_validate(user).model_dump(mode="json")}
    if user.role == "DONOR":
        p = db.query(DonorProfile).filter(DonorProfile.user_id == user.id).one_or_none()
        out["donor_profile"] = schemas.DonorProfileOut.model_validate(p).model_dump(mode="json") if p else None
    elif user.role == "NGO":
        p = db.query(NgoProfile).filter(NgoProfile.user_id == user.id).one_or_none()
        out["ngo_profile"] = schemas.NgoProfileOut.model_validate(p).model_dump(mode="json") if p else None
    elif user.role == "VOLUNTEER":
        p = db.query(VolunteerProfile).filter(VolunteerProfile.user_id == user.id).one_or_none()
        out["volunteer_profile"] = (
            {"ngo_id": p.ngo_id, "ngo_name": p.ngo.organization_name, "vehicle_type": p.vehicle_type,
             "area": p.area, "is_available": p.is_available}
            if p else None
        )
    out["features"] = flag_service.enabled_map(db)
    return out


@router.patch("/settings", response_model=schemas.UserOut)
def update_settings(body: schemas.SettingsUpdate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(user, k, v)
    audit(db, user, "UPDATE_SETTINGS", "user", user.id, {"fields": sorted(changes)}, request)
    db.commit()
    return user


@router.patch("/availability")
def set_availability(available: bool, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "VOLUNTEER":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only volunteers have availability.")
    p = db.query(VolunteerProfile).filter(VolunteerProfile.user_id == user.id).one()
    p.is_available = available
    db.commit()
    return {"is_available": p.is_available}


@router.get("/notifications", response_model=List[schemas.NotificationOut])
def my_notifications(limit: int = 50, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    return (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.channel == "IN_APP")
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )


@router.post("/notifications/{notification_id}/read", response_model=schemas.NotificationOut)
def mark_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    if n.status == "SENT":
        n.status = "READ"
    n.read_at = n.read_at or utcnow()
    db.commit()
    return n


@router.post("/notifications/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = utcnow()
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.read_at.is_(None))
        .update({"read_at": now}, synchronize_session=False)
    )
    db.query(Notification).filter(Notification.user_id == user.id, Notification.status == "SENT").update(
        {"status": "READ"}, synchronize_session=False
    )
    db.commit()
    return {"marked": count}
