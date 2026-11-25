"""Donation lifecycle state machine and status history."""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import DonationStatusHistory, FoodListing, PickupAssignment, User
from .timegeo import utcnow

TRANSITIONS: Dict[str, Set[str]] = {
    "DRAFT": {"PUBLISHED", "FLAGGED", "CANCELLED"},
    "PUBLISHED": {"MATCHED", "ACCEPTED", "FLAGGED", "CANCELLED", "EXPIRED"},
    "MATCHED": {"ACCEPTED", "FLAGGED", "CANCELLED", "EXPIRED"},
    "FLAGGED": {"PUBLISHED", "DRAFT", "CANCELLED", "EXPIRED"},
    "ACCEPTED": {"PICKUP_ASSIGNED", "CANCELLED", "EXPIRED"},
    "PICKUP_ASSIGNED": {"PICKED_UP", "ACCEPTED", "CANCELLED", "EXPIRED"},
    "PICKED_UP": {"DELIVERED"},
    "DELIVERED": set(),
    "CANCELLED": set(),
    "EXPIRED": set(),
}

# Statuses that are still waiting for collection and therefore expire at the deadline.
EXPIRABLE: List[str] = ["DRAFT", "PUBLISHED", "MATCHED", "FLAGGED", "ACCEPTED", "PICKUP_ASSIGNED"]
OPEN_FOR_ACCEPTANCE: List[str] = ["PUBLISHED", "MATCHED"]


def record(db: Session, listing: FoodListing, old: Optional[str], new: str, actor: Optional[User], note: str = "") -> None:
    db.add(
        DonationStatusHistory(
            listing_id=listing.id, from_status=old, to_status=new, changed_by=actor.id if actor else None, note=note or None
        )
    )


def transition(db: Session, listing: FoodListing, new: str, actor: Optional[User], note: str = "") -> None:
    old = listing.status
    if new not in TRANSITIONS.get(old, set()):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot move donation from {old} to {new}.")
    listing.status = new
    listing.version += 1
    record(db, listing, old, new, actor, note)


def expire_overdue(db: Session) -> int:
    """Mark every not-yet-collected listing whose deadline has passed as EXPIRED.

    Uses a conditional UPDATE per row so it cannot race with acceptance.
    """
    now = utcnow()
    overdue = (
        db.query(FoodListing.id, FoodListing.status)
        .filter(FoodListing.status.in_(EXPIRABLE), FoodListing.pickup_deadline <= now)
        .all()
    )
    count = 0
    for listing_id, old in overdue:
        res = db.execute(
            update(FoodListing)
            .where(FoodListing.id == listing_id, FoodListing.status == old)
            .values(status="EXPIRED", version=FoodListing.version + 1, updated_at=now)
        )
        if res.rowcount == 1:
            db.add(
                DonationStatusHistory(
                    listing_id=listing_id,
                    from_status=old,
                    to_status="EXPIRED",
                    note="Pickup deadline passed before collection; excluded from matching.",
                )
            )
            db.execute(
                update(PickupAssignment)
                .where(PickupAssignment.listing_id == listing_id, PickupAssignment.status == "ASSIGNED")
                .values(status="CANCELLED", updated_at=now)
            )
            count += 1
    if count:
        db.commit()
    return count
