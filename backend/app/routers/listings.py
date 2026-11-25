from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..deps import audit, get_current_user, require_roles
from ..models import DeliveryConfirmation, FoodListing, PickupAssignment, User
from ..services import lifecycle, workflow
from ..services.presenter import access_level, active_assignment, listing_detail, listing_out, viewer_ngo
from ..services.storage import resolve, save_image

router = APIRouter(prefix="/api/listings", tags=["listings"])


def _load(db: Session, listing_id: int) -> FoodListing:
    lifecycle.expire_overdue(db)
    listing = db.get(FoodListing, listing_id)
    if listing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Donation not found")
    return listing


def _owned(db: Session, listing_id: int, user: User) -> FoodListing:
    listing = _load(db, listing_id)
    if listing.donor_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Donation not found")
    return listing


@router.post("", response_model=schemas.ListingDetail, status_code=201)
def create_listing(body: schemas.ListingCreate, request: Request, user: User = Depends(require_roles("DONOR")), db: Session = Depends(get_db)):
    """Create a DRAFT donation. It is screened and matched only when published."""
    data = body.model_dump(exclude={"voice_confirmed"})
    listing = FoodListing(donor_id=user.id, status="DRAFT", is_demo=user.is_demo, **data)
    db.add(listing)
    db.flush()
    lifecycle.record(db, listing, None, "DRAFT", user,
                     "Created from confirmed voice report" if body.source == "VOICE" else "Created manually")
    audit(db, user, "CREATE_LISTING", "food_listing", listing.id, {"source": body.source}, request)
    db.commit()
    db.refresh(listing)
    return listing_detail(db, listing, user)


@router.get("/mine", response_model=List[schemas.ListingOut])
def my_listings(status_filter: Optional[str] = Query(default=None, alias="status"), user: User = Depends(require_roles("DONOR")), db: Session = Depends(get_db)):
    lifecycle.expire_overdue(db)
    q = db.query(FoodListing).filter(FoodListing.donor_id == user.id)
    if status_filter:
        q = q.filter(FoodListing.status == status_filter)
    return [listing_out(db, l, user, "full") for l in q.order_by(FoodListing.created_at.desc()).all()]


@router.get("/mine/stats")
def my_stats(user: User = Depends(require_roles("DONOR")), db: Session = Depends(get_db)) -> Dict[str, Any]:
    lifecycle.expire_overdue(db)
    q = db.query(FoodListing).filter(FoodListing.donor_id == user.id)
    by_status = dict(q.with_entities(FoodListing.status, func.count()).group_by(FoodListing.status).all())
    delivered = (
        db.query(func.coalesce(func.sum(DeliveryConfirmation.delivered_portions), 0), func.coalesce(func.sum(DeliveryConfirmation.collected_portions), 0))
        .join(FoodListing, FoodListing.id == DeliveryConfirmation.listing_id)
        .filter(FoodListing.donor_id == user.id)
        .one()
    )
    active = sum(by_status.get(s, 0) for s in ("DRAFT", "PUBLISHED", "MATCHED", "FLAGGED", "ACCEPTED", "PICKUP_ASSIGNED", "PICKED_UP"))
    return {
        "by_status": by_status,
        "active_donations": active,
        "pending_pickups": by_status.get("ACCEPTED", 0) + by_status.get("PICKUP_ASSIGNED", 0),
        "completed_donations": by_status.get("DELIVERED", 0),
        "portions_delivered": int(delivered[0]),
        "portions_collected": int(delivered[1]),
        "note": "Rescued portions count only deliveries confirmed by a volunteer.",
    }


@router.get("/{listing_id}", response_model=schemas.ListingDetail)
def get_listing(listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return listing_detail(db, _load(db, listing_id), user)


@router.patch("/{listing_id}", response_model=schemas.ListingDetail)
def update_listing(listing_id: int, body: schemas.ListingUpdate, user: User = Depends(require_roles("DONOR")), db: Session = Depends(get_db)):
    listing = _owned(db, listing_id, user)
    if listing.status not in ("DRAFT", "FLAGGED"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only draft or flagged donations can be edited.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(listing, k, v)
    if listing.pickup_deadline <= listing.prepared_at:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "pickup_deadline must be after prepared_at")
    if listing.status == "FLAGGED":
        lifecycle.transition(db, listing, "DRAFT", user, "Donor edited flagged donation; it will be re-screened on publish")
    else:
        listing.version += 1
    db.commit()
    return listing_detail(db, listing, user)


@router.post("/{listing_id}/publish", response_model=schemas.PublishResult)
def publish_listing(listing_id: int, request: Request, user: User = Depends(require_roles("DONOR")), db: Session = Depends(get_db)):
    listing = _owned(db, listing_id, user)
    check, matches = workflow.publish(db, listing, user)
    audit(db, user, "PUBLISH_LISTING", "food_listing", listing.id, {"safety": check.result, "matches": len(matches)}, request)
    db.commit()
    db.refresh(listing)
    if check.result == "FLAGGED":
        msg = "Your donation was flagged for admin safety review and will not be shown to NGOs until reviewed."
    elif matches:
        msg = f"Published and matched with {len(matches)} verified NGO(s). They have been notified."
    else:
        msg = "Published. No verified NGO currently meets the criteria; we will keep looking."
    return schemas.PublishResult(listing=listing_detail(db, listing, user), safety_result=check.result,
                                 issues=check.issues, matches_found=len(matches), message=msg)


@router.post("/{listing_id}/image", response_model=schemas.ListingDetail)
async def upload_image(listing_id: int, file: UploadFile = File(...), user: User = Depends(require_roles("DONOR")), db: Session = Depends(get_db)):
    listing = _owned(db, listing_id, user)
    if listing.status not in ("DRAFT", "FLAGGED", "PUBLISHED", "MATCHED"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Photos can only be added before acceptance.")
    listing.image_path = await save_image(file, "listings")
    db.commit()
    return listing_detail(db, listing, user)


@router.get("/{listing_id}/image")
def get_image(listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = _load(db, listing_id)
    access_level(db, listing, user)  # raises 404 if unauthorised
    if not listing.image_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo")
    return FileResponse(resolve(listing.image_path), headers={"Cache-Control": "private, max-age=300"})


@router.get("/{listing_id}/proof")
def get_proof(listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = _load(db, listing_id)
    if access_level(db, listing, user) != "full":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    a = db.query(PickupAssignment).filter(PickupAssignment.listing_id == listing.id, PickupAssignment.collection_proof_path.isnot(None)).order_by(PickupAssignment.id.desc()).first()
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No proof uploaded")
    return FileResponse(resolve(a.collection_proof_path), headers={"Cache-Control": "private, max-age=300"})


@router.post("/{listing_id}/cancel", response_model=schemas.ListingDetail)
def cancel_listing(listing_id: int, body: schemas.DecisionRequest, request: Request, user: User = Depends(require_roles("DONOR", "ADMIN")), db: Session = Depends(get_db)):
    listing = _load(db, listing_id)
    if user.role == "DONOR" and listing.donor_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Donation not found")
    workflow.cancel(db, listing, user, body.reason)
    audit(db, user, "CANCEL_LISTING", "food_listing", listing.id, {"reason": body.reason}, request)
    db.commit()
    return listing_detail(db, listing, user)


@router.post("/{listing_id}/rematch", response_model=schemas.ListingDetail)
def rematch(listing_id: int, user: User = Depends(require_roles("DONOR", "ADMIN")), db: Session = Depends(get_db)):
    listing = _load(db, listing_id)
    if user.role == "DONOR" and listing.donor_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Donation not found")
    if listing.status not in ("PUBLISHED", "MATCHED"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only open donations can be re-matched.")
    workflow.match_and_notify(db, listing, user)
    return listing_detail(db, listing, user)


@router.get("/{listing_id}/receipt", response_model=schemas.ReceiptOut)
def receipt(listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = _load(db, listing_id)
    ngo = viewer_ngo(db, user)
    if not (user.role == "ADMIN" or listing.donor_id == user.id or (ngo and listing.accepted_ngo_id == ngo.id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Donation not found")
    dc = db.query(DeliveryConfirmation).filter(DeliveryConfirmation.listing_id == listing.id).one_or_none()
    if listing.status != "DELIVERED" or dc is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A receipt is generated only after delivery is confirmed.")
    a = db.get(PickupAssignment, dc.assignment_id)
    org = listing.donor.donor_profile.organization_name if listing.donor.donor_profile else listing.donor.full_name
    return schemas.ReceiptOut(
        receipt_number=dc.receipt_number, listing_id=listing.id, donor_organization=org, donor_name=listing.donor.full_name,
        ngo_name=listing.accepted_ngo.organization_name if listing.accepted_ngo else "-", volunteer_name=a.volunteer.full_name,
        food_type=listing.food_type, food_category=listing.food_category, portions_reported=listing.portions_reported,
        portions_collected=dc.collected_portions, portions_delivered=dc.delivered_portions, prepared_at=listing.prepared_at,
        picked_up_at=a.picked_up_at, delivered_at=dc.created_at, is_demo=listing.is_demo,
        statement=(
            "This receipt records portions reported by the donor, collected by the volunteer and confirmed as delivered. "
            "It is an acknowledgement of donation, not a food-safety certificate."
            + (" DEMO DATA - not a real donation." if listing.is_demo else "")
        ),
    )
