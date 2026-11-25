"""Serialise listings for a specific viewer, enforcing contact-information privacy."""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models import (
    DeliveryConfirmation,
    DonationAcceptance,
    FoodListing,
    NgoMatch,
    NgoProfile,
    PickupAssignment,
    User,
)
from .. import schemas
from .safety import SAFETY_DISCLAIMER
from .timegeo import approx_coord


def active_assignment(db: Session, listing_id: int) -> Optional[PickupAssignment]:
    return (
        db.query(PickupAssignment)
        .filter(PickupAssignment.listing_id == listing_id, PickupAssignment.status != "CANCELLED")
        .one_or_none()
    )


def viewer_ngo(db: Session, user: User) -> Optional[NgoProfile]:
    if user.role != "NGO":
        return None
    return db.query(NgoProfile).filter(NgoProfile.user_id == user.id).one_or_none()


def access_level(db: Session, listing: FoodListing, user: User) -> str:
    """Return 'full', 'limited' or raise 404 (we do not reveal existence to unrelated users)."""
    if user.role == "ADMIN" or listing.donor_id == user.id:
        return "full"
    if user.role == "NGO":
        ngo = viewer_ngo(db, user)
        if ngo and listing.accepted_ngo_id == ngo.id:
            return "full"
        if ngo and ngo.verification_status == "VERIFIED":
            matched = db.query(NgoMatch).filter(NgoMatch.listing_id == listing.id, NgoMatch.ngo_id == ngo.id).count()
            if matched:
                return "limited"
    if user.role == "VOLUNTEER":
        a = active_assignment(db, listing.id)
        if a and a.volunteer_id == user.id:
            return "full"
        past = (
            db.query(PickupAssignment)
            .filter(PickupAssignment.listing_id == listing.id, PickupAssignment.volunteer_id == user.id)
            .count()
        )
        if past:
            return "limited"
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Donation not found")


def _match_out(m: NgoMatch, decision: Optional[str] = None) -> schemas.MatchOut:
    return schemas.MatchOut(
        ngo_id=m.ngo_id, ngo_name=m.ngo.organization_name, ngo_area=m.ngo.area, rank=m.rank, score=m.score,
        distance_km=m.distance_km, components=m.components or {}, explanation=m.explanation, decision=decision,
    )


def listing_out(db: Session, listing: FoodListing, user: User, level: Optional[str] = None) -> schemas.ListingOut:
    level = level or access_level(db, listing, user)
    full = level == "full"
    donor = listing.donor
    org = donor.donor_profile.organization_name if donor.donor_profile else None
    my_match = None
    ngo = viewer_ngo(db, user)
    if ngo:
        m = db.query(NgoMatch).filter(NgoMatch.listing_id == listing.id, NgoMatch.ngo_id == ngo.id).one_or_none()
        if m:
            d = (
                db.query(DonationAcceptance.decision)
                .filter(DonationAcceptance.listing_id == listing.id, DonationAcceptance.ngo_id == ngo.id)
                .scalar()
            )
            my_match = _match_out(m, d)
    return schemas.ListingOut(
        id=listing.id,
        title=listing.title,
        description=listing.description,
        food_type=listing.food_type,
        food_category=listing.food_category,
        portions_reported=listing.portions_reported,
        prepared_at=listing.prepared_at,
        pickup_deadline=listing.pickup_deadline,
        storage_condition=listing.storage_condition,
        packaging=listing.packaging,
        allergens=listing.allergens,
        area=listing.area,
        latitude=listing.latitude if full else approx_coord(listing.latitude),
        longitude=listing.longitude if full else approx_coord(listing.longitude),
        location_precision="exact" if full else "approximate",
        pickup_address=listing.pickup_address if full else None,
        donor_name=donor.full_name if full else None,
        donor_phone=donor.phone if full else None,
        donor_organization=org if full else ("Verified donor" if org else None),
        has_image=bool(listing.image_path),
        source=listing.source,
        voice_transcript=listing.voice_transcript if full else None,
        voice_language=listing.voice_language,
        predicted_surplus_portions=listing.predicted_surplus_portions,
        status=listing.status,
        emergency=listing.emergency,
        is_demo=listing.is_demo,
        accepted_ngo_id=listing.accepted_ngo_id,
        accepted_ngo_name=listing.accepted_ngo.organization_name if listing.accepted_ngo else None,
        published_at=listing.published_at,
        accepted_at=listing.accepted_at,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
        my_match=my_match,
    )


def listing_detail(db: Session, listing: FoodListing, user: User) -> schemas.ListingDetail:
    level = access_level(db, listing, user)
    base = listing_out(db, listing, user, level).model_dump()
    full = level == "full"

    history = [
        schemas.HistoryOut(
            id=h.id, from_status=h.from_status, to_status=h.to_status,
            actor_name=(h.actor.full_name if (h.actor and (full or h.actor.role != "DONOR")) else ("Donor" if h.actor else "System")),
            actor_role=h.actor.role if h.actor else "SYSTEM", note=h.note, created_at=h.created_at,
        )
        for h in listing.history
    ]
    decisions: Dict[int, str] = {
        a.ngo_id: a.decision
        for a in db.query(DonationAcceptance).filter(DonationAcceptance.listing_id == listing.id).all()
    }
    show_all_matches = user.role == "ADMIN" or listing.donor_id == user.id
    ngo = viewer_ngo(db, user)
    matches = [
        _match_out(m, decisions.get(m.ngo_id))
        for m in listing.matches
        if show_all_matches or (ngo and m.ngo_id == ngo.id)
    ]

    a = active_assignment(db, listing.id)
    assignment = None
    if a and (full or a.volunteer_id == user.id):
        assignment = schemas.AssignmentOut(
            id=a.id, listing_id=a.listing_id, volunteer_id=a.volunteer_id, volunteer_name=a.volunteer.full_name,
            status=a.status, collected_portions=a.collected_portions, has_proof=bool(a.collection_proof_path),
            collection_notes=a.collection_notes, picked_up_at=a.picked_up_at, delivered_at=a.delivered_at,
            created_at=a.created_at,
        )
    dc = db.query(DeliveryConfirmation).filter(DeliveryConfirmation.listing_id == listing.id).one_or_none()
    delivery = (
        schemas.DeliveryOut(
            collected_portions=dc.collected_portions, delivered_portions=dc.delivered_portions,
            delivery_location=dc.delivery_location, notes=dc.notes, receipt_number=dc.receipt_number,
            ngo_acknowledged_at=dc.ngo_acknowledged_at, created_at=dc.created_at,
        )
        if dc
        else None
    )

    is_owner = listing.donor_id == user.id
    is_accepted_ngo = bool(ngo and listing.accepted_ngo_id == ngo.id)
    is_assigned_vol = bool(a and a.volunteer_id == user.id)
    my_decision = decisions.get(ngo.id) if ngo else None
    viewer_can = {
        "publish": is_owner and listing.status == "DRAFT",
        "edit": is_owner and listing.status in ("DRAFT", "FLAGGED"),
        "cancel": (is_owner or user.role == "ADMIN") and listing.status in ("DRAFT", "PUBLISHED", "MATCHED", "FLAGGED", "ACCEPTED", "PICKUP_ASSIGNED"),
        "accept": bool(ngo and ngo.verification_status == "VERIFIED" and listing.status in ("PUBLISHED", "MATCHED") and level == "limited" and my_decision is None),
        "reject": bool(ngo and listing.status in ("PUBLISHED", "MATCHED") and level == "limited" and my_decision is None),
        "assign": is_accepted_ngo and listing.status == "ACCEPTED",
        "unassign": is_accepted_ngo and listing.status == "PICKUP_ASSIGNED",
        "confirm_pickup": is_assigned_vol and listing.status == "PICKUP_ASSIGNED",
        "confirm_delivery": is_assigned_vol and listing.status == "PICKED_UP",
        "acknowledge": is_accepted_ngo and listing.status == "DELIVERED" and bool(dc and not dc.ngo_acknowledged_at),
        "receipt": listing.status == "DELIVERED" and (is_owner or is_accepted_ngo or user.role == "ADMIN"),
        "review_safety": user.role == "ADMIN" and listing.status == "FLAGGED",
        "rematch": (is_owner or user.role == "ADMIN") and listing.status in ("PUBLISHED", "MATCHED"),
    }
    return schemas.ListingDetail(
        **base,
        history=history,
        safety_checks=[schemas.SafetyCheckOut.model_validate(c) for c in listing.safety_checks],
        matches=matches,
        assignment=assignment,
        delivery=delivery,
        safety_disclaimer=SAFETY_DISCLAIMER,
        viewer_can=viewer_can,
    )
