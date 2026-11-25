from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..deps import audit, get_ngo_profile, require_verified_ngo
from ..models import DeliveryConfirmation, DonationAcceptance, FoodListing, NgoMatch, NgoProfile, PickupAssignment, VolunteerProfile
from ..services import lifecycle, workflow
from ..services.matching import capacity_used_today
from ..services.presenter import listing_detail, listing_out
from ..services.timegeo import utcnow

router = APIRouter(prefix="/api/ngo", tags=["ngo"])


@router.get("/profile", response_model=schemas.NgoProfileOut)
def profile(ngo: NgoProfile = Depends(get_ngo_profile)):
    return ngo


@router.patch("/profile", response_model=schemas.NgoProfileOut)
def update_profile(body: schemas.NgoProfileUpdate, request: Request, ngo: NgoProfile = Depends(get_ngo_profile), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(ngo, k, v)
    audit(db, ngo.user, "UPDATE_NGO_PROFILE", "ngo_profile", ngo.id, changes, request)
    db.commit()
    return ngo


@router.get("/listings/available", response_model=List[schemas.ListingOut])
def available(
    category: Optional[str] = None,
    max_distance_km: Optional[float] = Query(default=None, gt=0),
    min_portions: Optional[int] = Query(default=None, ge=1),
    ngo: NgoProfile = Depends(require_verified_ngo),
    db: Session = Depends(get_db),
):
    """Open donations matched to this NGO, best match first. Locations are approximate until acceptance."""
    lifecycle.expire_overdue(db)
    responded = db.query(DonationAcceptance.listing_id).filter(DonationAcceptance.ngo_id == ngo.id)
    q = (
        db.query(FoodListing, NgoMatch)
        .join(NgoMatch, NgoMatch.listing_id == FoodListing.id)
        .filter(NgoMatch.ngo_id == ngo.id, FoodListing.status.in_(lifecycle.OPEN_FOR_ACCEPTANCE), FoodListing.id.notin_(responded))
    )
    if category:
        q = q.filter(FoodListing.food_category == category)
    if max_distance_km:
        q = q.filter(NgoMatch.distance_km <= max_distance_km)
    if min_portions:
        q = q.filter(FoodListing.portions_reported >= min_portions)
    rows = q.order_by(FoodListing.emergency.desc(), NgoMatch.score.desc()).all()
    return [listing_out(db, l, ngo.user, "limited") for l, _m in rows]


@router.get("/listings/accepted", response_model=List[schemas.ListingOut])
def accepted(ngo: NgoProfile = Depends(get_ngo_profile), db: Session = Depends(get_db)):
    lifecycle.expire_overdue(db)
    rows = db.query(FoodListing).filter(FoodListing.accepted_ngo_id == ngo.id).order_by(FoodListing.accepted_at.desc()).all()
    return [listing_out(db, l, ngo.user, "full") for l in rows]


@router.get("/stats")
def stats(ngo: NgoProfile = Depends(get_ngo_profile), db: Session = Depends(get_db)) -> Dict[str, Any]:
    used = capacity_used_today(db, ngo.id, utcnow())
    delivered = (
        db.query(func.coalesce(func.sum(DeliveryConfirmation.delivered_portions), 0))
        .join(FoodListing, FoodListing.id == DeliveryConfirmation.listing_id)
        .filter(FoodListing.accepted_ngo_id == ngo.id)
        .scalar()
    )
    open_matches = (
        db.query(func.count(NgoMatch.id))
        .join(FoodListing, FoodListing.id == NgoMatch.listing_id)
        .filter(NgoMatch.ngo_id == ngo.id, FoodListing.status.in_(lifecycle.OPEN_FOR_ACCEPTANCE))
        .scalar()
    )
    in_progress = db.query(FoodListing).filter(FoodListing.accepted_ngo_id == ngo.id, FoodListing.status.in_(["ACCEPTED", "PICKUP_ASSIGNED", "PICKED_UP"])).count()
    return {
        "verification_status": ngo.verification_status,
        "daily_capacity": ngo.daily_capacity_portions,
        "capacity_used_today": used,
        "capacity_remaining_today": max(0, ngo.daily_capacity_portions - used),
        "open_matches": open_matches,
        "in_progress": in_progress,
        "portions_received": int(delivered or 0),
    }


@router.get("/volunteers", response_model=List[schemas.VolunteerOut])
def volunteers(ngo: NgoProfile = Depends(get_ngo_profile), db: Session = Depends(get_db)):
    out = []
    for vp in db.query(VolunteerProfile).filter(VolunteerProfile.ngo_id == ngo.id).all():
        active = db.query(PickupAssignment).filter(PickupAssignment.volunteer_id == vp.user_id, PickupAssignment.status.in_(["ASSIGNED", "PICKED_UP"])).count()
        out.append(schemas.VolunteerOut(user_id=vp.user_id, full_name=vp.user.full_name, phone=vp.user.phone,
                                        vehicle_type=vp.vehicle_type, area=vp.area, is_available=vp.is_available and vp.user.is_active,
                                        active_assignments=active))
    return out


def _listing(db: Session, listing_id: int) -> FoodListing:
    lifecycle.expire_overdue(db)
    l = db.get(FoodListing, listing_id)
    if l is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Donation not found")
    return l


@router.post("/listings/{listing_id}/accept", response_model=schemas.ListingDetail)
def accept(listing_id: int, body: schemas.DecisionRequest, request: Request, ngo: NgoProfile = Depends(require_verified_ngo), db: Session = Depends(get_db)):
    _listing(db, listing_id)
    listing = workflow.accept(db, listing_id, ngo, ngo.user, body.reason)
    audit(db, ngo.user, "ACCEPT_DONATION", "food_listing", listing_id, {}, request)
    db.commit()
    return listing_detail(db, listing, ngo.user)


@router.post("/listings/{listing_id}/reject")
def reject(listing_id: int, body: schemas.DecisionRequest, request: Request, ngo: NgoProfile = Depends(require_verified_ngo), db: Session = Depends(get_db)):
    listing = _listing(db, listing_id)
    workflow.reject(db, listing, ngo, ngo.user, body.reason)
    audit(db, ngo.user, "REJECT_DONATION", "food_listing", listing_id, {"reason": body.reason}, request)
    db.commit()
    return {"ok": True}


@router.post("/listings/{listing_id}/assign", response_model=schemas.ListingDetail)
def assign(listing_id: int, body: schemas.AssignRequest, request: Request, ngo: NgoProfile = Depends(require_verified_ngo), db: Session = Depends(get_db)):
    listing = _listing(db, listing_id)
    workflow.assign_volunteer(db, listing, ngo, ngo.user, body.volunteer_user_id)
    audit(db, ngo.user, "ASSIGN_VOLUNTEER", "food_listing", listing_id, {"volunteer_user_id": body.volunteer_user_id}, request)
    db.commit()
    return listing_detail(db, listing, ngo.user)


@router.post("/listings/{listing_id}/unassign", response_model=schemas.ListingDetail)
def unassign(listing_id: int, ngo: NgoProfile = Depends(require_verified_ngo), db: Session = Depends(get_db)):
    listing = _listing(db, listing_id)
    workflow.unassign_volunteer(db, listing, ngo, ngo.user)
    return listing_detail(db, listing, ngo.user)


@router.post("/listings/{listing_id}/acknowledge", response_model=schemas.ListingDetail)
def acknowledge(listing_id: int, ngo: NgoProfile = Depends(get_ngo_profile), db: Session = Depends(get_db)):
    listing = _listing(db, listing_id)
    workflow.acknowledge_delivery(db, listing, ngo, ngo.user)
    return listing_detail(db, listing, ngo.user)
