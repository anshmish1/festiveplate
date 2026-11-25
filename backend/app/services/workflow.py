"""Donation workflow operations (publish, accept, assign, pickup, deliver, cancel, review)."""
from __future__ import annotations

import secrets
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import insert, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    DeliveryConfirmation,
    DonationAcceptance,
    DonationStatusHistory,
    FoodListing,
    FoodSafetyCheck,
    NgoMatch,
    NgoProfile,
    PickupAssignment,
    User,
    VolunteerProfile,
)
from . import lifecycle
from .flags import flag_service
from .matching import run_matching
from .notify import notify
from .safety import screen
from .timegeo import fmt_ist, utcnow


def _conflict(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, msg)


def run_safety(db: Session, listing: FoodListing) -> FoodSafetyCheck:
    res = screen(
        prepared_at=listing.prepared_at,
        pickup_deadline=listing.pickup_deadline,
        storage_condition=listing.storage_condition,
        food_category=listing.food_category,
        allergens=listing.allergens,
    )
    check = FoodSafetyCheck(listing_id=listing.id, result=res.result, issues=[i.as_dict() for i in res.issues])
    db.add(check)
    return check


def match_and_notify(db: Session, listing: FoodListing, actor: Optional[User]) -> List[NgoMatch]:
    matches = run_matching(db, listing, flag_service.is_enabled(db, "emergency_matching"))
    if matches and listing.status == "PUBLISHED":
        lifecycle.transition(
            db, listing, "MATCHED", actor,
            f"Matched with {len(matches)} verified NGO(s)" + (" using widened emergency radius" if listing.emergency else ""),
        )
    db.commit()
    for m in matches:
        if not m.notified:
            notify(
                db, m.ngo.user, type="NEW_MATCH", listing_id=listing.id,
                title=("URGENT: " if listing.emergency else "") + f"{listing.portions_reported} portions available in {listing.area}",
                body=(
                    f"A donation of {listing.portions_reported} {listing.food_category.replace('_', '-').lower()} portions "
                    f"({listing.food_type}) is available {m.distance_km:.1f} km from you. Pickup before "
                    f"{fmt_ist(listing.pickup_deadline)}. Open FestivePlate to accept or decline."
                ),
            )
            m.notified = True
    db.commit()
    return matches


def publish(db: Session, listing: FoodListing, actor: User) -> Tuple[FoodSafetyCheck, List[NgoMatch]]:
    if listing.status != "DRAFT":
        raise _conflict(f"Only draft donations can be published (current status {listing.status}).")
    check = run_safety(db, listing)
    db.flush()
    if check.result == "FLAGGED":
        lifecycle.transition(
            db, listing, "FLAGGED", None,
            "Automated screening flagged: " + "; ".join(i["message"] for i in check.issues if i["severity"] == "BLOCKING"),
        )
        db.commit()
        for admin in db.query(User).filter(User.role == "ADMIN", User.is_active.is_(True)).all():
            notify(db, admin, type="SAFETY_FLAG", listing_id=listing.id, title=f"Safety review needed: {listing.title}",
                   body="A donation was flagged by automated screening and is excluded from matching until reviewed.")
        db.commit()
        return check, []
    listing.published_at = utcnow()
    lifecycle.transition(db, listing, "PUBLISHED", actor, "Passed automated screening (not a safety certification)")
    db.commit()
    return check, match_and_notify(db, listing, None)


def accept(db: Session, listing_id: int, ngo: NgoProfile, actor: User, reason: Optional[str] = None) -> FoodListing:
    """Atomically accept a listing for an NGO. Exactly one NGO can win.

    The conditional UPDATE (status still open AND no accepted NGO) is the primary
    guard; the partial unique index on donation_acceptances is the second.
    """
    if ngo.verification_status != "VERIFIED":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrator-verified NGOs can accept donations.")
    matched = db.query(NgoMatch).filter(NgoMatch.listing_id == listing_id, NgoMatch.ngo_id == ngo.id).count()
    if not matched:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This donation was not matched to your organisation.")
    now = utcnow()
    before = db.query(FoodListing.status).filter(FoodListing.id == listing_id).scalar()
    res = db.execute(
        update(FoodListing)
        .where(
            FoodListing.id == listing_id,
            FoodListing.status.in_(lifecycle.OPEN_FOR_ACCEPTANCE),
            FoodListing.accepted_ngo_id.is_(None),
            FoodListing.pickup_deadline > now,
        )
        .values(status="ACCEPTED", accepted_ngo_id=ngo.id, accepted_at=now, version=FoodListing.version + 1, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if res.rowcount != 1:
        db.rollback()
        current = db.get(FoodListing, listing_id)
        if current is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Donation not found")
        if current.pickup_deadline <= now:
            raise _conflict("The pickup deadline has passed; this donation can no longer be accepted.")
        raise _conflict("This donation has already been accepted by another organisation or is no longer available.")
    try:
        db.execute(
            insert(DonationAcceptance).values(
                listing_id=listing_id, ngo_id=ngo.id, decision="ACCEPTED", reason=reason, decided_by=actor.id, created_at=now
            )
        )
        db.add(DonationStatusHistory(listing_id=listing_id, from_status=before if before in lifecycle.OPEN_FOR_ACCEPTANCE else "MATCHED",
                                     to_status="ACCEPTED", changed_by=actor.id,
                                     note=f"Accepted by {ngo.organization_name}"))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflict("This donation has already been accepted by another organisation.")

    listing = db.get(FoodListing, listing_id)
    db.refresh(listing)
    notify(db, listing.donor, type="ACCEPTED", listing_id=listing.id, title="Your donation was accepted",
           body=f"{ngo.organization_name} accepted your donation '{listing.title}'. A volunteer will be assigned for pickup.")
    others = db.query(NgoMatch).filter(NgoMatch.listing_id == listing_id, NgoMatch.ngo_id != ngo.id).all()
    for m in others:
        notify(db, m.ngo.user, type="NO_LONGER_AVAILABLE", listing_id=listing.id, title="Donation no longer available",
               body=f"The donation '{listing.title}' in {listing.area} has been accepted by another organisation.")
    db.commit()
    return listing


def reject(db: Session, listing: FoodListing, ngo: NgoProfile, actor: User, reason: Optional[str]) -> None:
    if listing.status not in lifecycle.OPEN_FOR_ACCEPTANCE:
        raise _conflict("This donation is no longer open for decisions.")
    if not db.query(NgoMatch).filter(NgoMatch.listing_id == listing.id, NgoMatch.ngo_id == ngo.id).count():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This donation was not matched to your organisation.")
    db.add(DonationAcceptance(listing_id=listing.id, ngo_id=ngo.id, decision="REJECTED", reason=reason, decided_by=actor.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflict("Your organisation has already responded to this donation.")
    total = db.query(NgoMatch).filter(NgoMatch.listing_id == listing.id).count()
    rejected = db.query(DonationAcceptance).filter(DonationAcceptance.listing_id == listing.id, DonationAcceptance.decision == "REJECTED").count()
    if total and rejected >= total:
        notify(db, listing.donor, type="ALL_DECLINED", listing_id=listing.id, title="Matched NGOs declined",
               body=f"All matched organisations declined '{listing.title}'. FestivePlate will keep looking as more NGOs become available.")
        db.commit()


def assign_volunteer(db: Session, listing: FoodListing, ngo: NgoProfile, actor: User, volunteer_user_id: int) -> PickupAssignment:
    if listing.accepted_ngo_id != ngo.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the accepting NGO can assign a volunteer.")
    if listing.status != "ACCEPTED":
        raise _conflict(f"A volunteer can only be assigned to an ACCEPTED donation (current {listing.status}).")
    vp = db.query(VolunteerProfile).filter(VolunteerProfile.user_id == volunteer_user_id, VolunteerProfile.ngo_id == ngo.id).one_or_none()
    if vp is None or not vp.user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Volunteer not found in your organisation.")
    if not vp.is_available:
        raise _conflict("This volunteer has marked themselves unavailable.")
    a = PickupAssignment(listing_id=listing.id, ngo_id=ngo.id, volunteer_id=volunteer_user_id, assigned_by=actor.id)
    db.add(a)
    lifecycle.transition(db, listing, "PICKUP_ASSIGNED", actor, f"Pickup assigned to volunteer {vp.user.full_name}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflict("A volunteer is already assigned to this donation.")
    notify(db, vp.user, type="PICKUP_ASSIGNED", listing_id=listing.id, title="New pickup assigned",
           body=f"Collect {listing.portions_reported} portions ({listing.food_type}) in {listing.area} before {fmt_ist(listing.pickup_deadline)}.")
    notify(db, listing.donor, type="PICKUP_ASSIGNED", listing_id=listing.id, title="Volunteer on the way",
           body=f"{vp.user.full_name} from {ngo.organization_name} will collect '{listing.title}'.")
    db.commit()
    return a


def unassign_volunteer(db: Session, listing: FoodListing, ngo: NgoProfile, actor: User) -> None:
    if listing.accepted_ngo_id != ngo.id or listing.status != "PICKUP_ASSIGNED":
        raise _conflict("No reassignable pickup for this donation.")
    a = db.query(PickupAssignment).filter(PickupAssignment.listing_id == listing.id, PickupAssignment.status == "ASSIGNED").one()
    a.status = "CANCELLED"
    lifecycle.transition(db, listing, "ACCEPTED", actor, "Volunteer unassigned; awaiting reassignment")
    db.commit()


def _get_assignment(db: Session, assignment_id: int, volunteer: User) -> PickupAssignment:
    a = db.get(PickupAssignment, assignment_id)
    if a is None or a.volunteer_id != volunteer.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")
    return a


def confirm_pickup(db: Session, assignment_id: int, volunteer: User, collected: int, notes: Optional[str], proof_path: Optional[str]) -> PickupAssignment:
    a = _get_assignment(db, assignment_id, volunteer)
    listing = a.listing
    if a.status != "ASSIGNED" or listing.status != "PICKUP_ASSIGNED":
        raise _conflict("This pickup is not awaiting collection.")
    if listing.pickup_deadline <= utcnow():
        raise _conflict("The pickup deadline has passed. Do not collect; contact your NGO coordinator.")
    if collected <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Collected portions must be greater than zero.")
    a.status = "PICKED_UP"
    a.collected_portions = collected
    a.collection_notes = notes
    a.collection_proof_path = proof_path
    a.picked_up_at = utcnow()
    note = f"Collected {collected} portions (donor reported {listing.portions_reported})"
    lifecycle.transition(db, listing, "PICKED_UP", volunteer, note)
    db.commit()
    notify(db, listing.donor, type="PICKED_UP", listing_id=listing.id, title="Food collected",
           body=f"{volunteer.full_name} collected {collected} portions of '{listing.title}'. Thank you!")
    notify(db, a.ngo.user, type="PICKED_UP", listing_id=listing.id, title="Pickup confirmed",
           body=f"{volunteer.full_name} collected {collected} portions from {listing.area} and is heading to you.")
    db.commit()
    return a


def confirm_delivery(db: Session, assignment_id: int, volunteer: User, delivered: int, location: Optional[str], notes: Optional[str]) -> DeliveryConfirmation:
    a = _get_assignment(db, assignment_id, volunteer)
    listing = a.listing
    if a.status != "PICKED_UP" or listing.status != "PICKED_UP":
        raise _conflict("Delivery can only be confirmed after pickup.")
    if delivered > (a.collected_portions or 0):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Delivered portions cannot exceed collected portions ({a.collected_portions}).")
    now = utcnow()
    a.status = "DELIVERED"
    a.delivered_at = now
    dc = DeliveryConfirmation(
        listing_id=listing.id, assignment_id=a.id, collected_portions=a.collected_portions or 0,
        delivered_portions=delivered, delivery_location=location, notes=notes, confirmed_by_volunteer=volunteer.id,
        receipt_number=f"FP-{now:%Y%m%d}-{listing.id:05d}-{secrets.token_hex(2).upper()}",
    )
    db.add(dc)
    lifecycle.transition(db, listing, "DELIVERED", volunteer, f"Delivered {delivered} portions (collected {a.collected_portions})")
    db.commit()
    notify(db, listing.donor, type="DELIVERED", listing_id=listing.id, title="Delivered! Your receipt is ready",
           body=f"{delivered} portions from '{listing.title}' reached people in need. Receipt {dc.receipt_number}.")
    notify(db, a.ngo.user, type="DELIVERED", listing_id=listing.id, title="Delivery confirmed by volunteer",
           body=f"{volunteer.full_name} confirmed delivery of {delivered} portions. Please acknowledge receipt.")
    db.commit()
    return dc


def acknowledge_delivery(db: Session, listing: FoodListing, ngo: NgoProfile, actor: User) -> DeliveryConfirmation:
    if listing.accepted_ngo_id != ngo.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the receiving NGO can acknowledge delivery.")
    dc = db.query(DeliveryConfirmation).filter(DeliveryConfirmation.listing_id == listing.id).one_or_none()
    if dc is None:
        raise _conflict("Delivery has not been confirmed yet.")
    if dc.ngo_acknowledged_at:
        raise _conflict("Delivery already acknowledged.")
    dc.ngo_acknowledged_by = actor.id
    dc.ngo_acknowledged_at = utcnow()
    db.add(DonationStatusHistory(listing_id=listing.id, from_status="DELIVERED", to_status="DELIVERED", changed_by=actor.id,
                                 note=f"{ngo.organization_name} acknowledged receipt"))
    db.commit()
    return dc


def cancel(db: Session, listing: FoodListing, actor: User, reason: Optional[str]) -> None:
    lifecycle.transition(db, listing, "CANCELLED", actor, reason or "Cancelled")
    db.query(PickupAssignment).filter(PickupAssignment.listing_id == listing.id, PickupAssignment.status == "ASSIGNED").update(
        {"status": "CANCELLED"}, synchronize_session=False
    )
    db.commit()
    recipients = []
    if listing.accepted_ngo:
        recipients.append(listing.accepted_ngo.user)
    a = db.query(PickupAssignment).filter(PickupAssignment.listing_id == listing.id).order_by(PickupAssignment.id.desc()).first()
    if a:
        recipients.append(a.volunteer)
    if actor.id != listing.donor_id:
        recipients.append(listing.donor)
    for u in recipients:
        notify(db, u, type="CANCELLED", listing_id=listing.id, title="Donation cancelled",
               body=f"'{listing.title}' was cancelled. Reason: {reason or 'not given'}.")
    db.commit()


def review_safety(db: Session, listing: FoodListing, admin: User, decision: str, notes: str) -> List[NgoMatch]:
    if listing.status != "FLAGGED":
        raise _conflict("Only flagged donations can be reviewed.")
    check = listing.safety_checks[-1] if listing.safety_checks else None
    if check:
        check.reviewer_id = admin.id
        check.review_decision = decision
        check.review_notes = notes
        check.reviewed_at = utcnow()
    if decision == "REJECTED":
        lifecycle.transition(db, listing, "CANCELLED", admin, f"Rejected in safety review: {notes}")
        db.commit()
        notify(db, listing.donor, type="SAFETY_REJECTED", listing_id=listing.id, title="Donation not approved",
               body=f"'{listing.title}' could not be approved after safety review: {notes}")
        db.commit()
        return []
    # Re-screen: clearing a flag never overrides a passed deadline.
    if listing.pickup_deadline <= utcnow():
        raise _conflict("The pickup deadline has passed; the listing cannot be cleared.")
    listing.published_at = listing.published_at or utcnow()
    lifecycle.transition(db, listing, "PUBLISHED", admin, f"Cleared by admin after review: {notes}")
    db.commit()
    notify(db, listing.donor, type="SAFETY_CLEARED", listing_id=listing.id, title="Donation cleared for matching",
           body=f"An administrator reviewed '{listing.title}' and released it for NGO matching.")
    db.commit()
    return match_and_notify(db, listing, admin)
