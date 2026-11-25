from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..deps import audit, require_roles
from ..models import PickupAssignment, User
from ..services import lifecycle, workflow
from ..services.presenter import listing_detail, listing_out
from ..services.storage import save_image

router = APIRouter(prefix="/api/volunteer", tags=["volunteer"])


@router.get("/assignments")
def assignments(user: User = Depends(require_roles("VOLUNTEER")), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    lifecycle.expire_overdue(db)
    rows = db.query(PickupAssignment).filter(PickupAssignment.volunteer_id == user.id).order_by(PickupAssignment.created_at.desc()).all()
    out = []
    for a in rows:
        level = "full" if a.status in ("ASSIGNED", "PICKED_UP") and a.listing.status in ("PICKUP_ASSIGNED", "PICKED_UP") else "limited"
        out.append({
            "assignment_id": a.id,
            "assignment_status": a.status,
            "collected_portions": a.collected_portions,
            "picked_up_at": schemas._ser_utc(a.picked_up_at) if a.picked_up_at else None,
            "delivered_at": schemas._ser_utc(a.delivered_at) if a.delivered_at else None,
            "ngo_name": a.ngo.organization_name,
            "ngo_address": a.ngo.address,
            "ngo_latitude": a.ngo.latitude,
            "ngo_longitude": a.ngo.longitude,
            "listing": listing_out(db, a.listing, user, level).model_dump(mode="json"),
        })
    return out


@router.post("/assignments/{assignment_id}/pickup", response_model=schemas.ListingDetail)
async def confirm_pickup(
    assignment_id: int,
    request: Request,
    collected_portions: int = Form(..., gt=0, le=100000),
    notes: Optional[str] = Form(default=None, max_length=1000),
    proof: Optional[UploadFile] = File(default=None),
    user: User = Depends(require_roles("VOLUNTEER")),
    db: Session = Depends(get_db),
):
    lifecycle.expire_overdue(db)
    proof_path = await save_image(proof, "proofs") if proof is not None and proof.filename else None
    a = workflow.confirm_pickup(db, assignment_id, user, collected_portions, notes, proof_path)
    audit(db, user, "CONFIRM_PICKUP", "food_listing", a.listing_id, {"collected": collected_portions, "proof": bool(proof_path)}, request)
    db.commit()
    return listing_detail(db, a.listing, user)


@router.post("/assignments/{assignment_id}/deliver", response_model=schemas.ListingDetail)
def confirm_delivery(assignment_id: int, body: schemas.DeliveryRequest, request: Request, user: User = Depends(require_roles("VOLUNTEER")), db: Session = Depends(get_db)):
    dc = workflow.confirm_delivery(db, assignment_id, user, body.delivered_portions, body.delivery_location, body.notes)
    audit(db, user, "CONFIRM_DELIVERY", "food_listing", dc.listing_id, {"delivered": body.delivered_portions}, request)
    db.commit()
    a = db.get(PickupAssignment, assignment_id)
    return listing_detail(db, a.listing, user)
