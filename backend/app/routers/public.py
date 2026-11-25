from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import DeliveryConfirmation, FoodListing, NgoProfile, PickupAssignment, User
from ..services.flags import flag_service
from ..services.monitoring import metrics

router = APIRouter(tags=["public"])

TERMINAL_AFTER_PUBLISH = ["DELIVERED", "EXPIRED", "CANCELLED"]


@router.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "uptime_seconds": metrics.snapshot()["uptime_seconds"]}


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def prometheus(authorization: Optional[str] = Header(default=None)):
    token = get_settings().metrics_token
    if token and authorization != f"Bearer {token}":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "metrics token required")
    return metrics.prometheus()


def impact_numbers(db: Session) -> Dict[str, Any]:
    published = db.query(FoodListing).filter(FoodListing.published_at.isnot(None))
    reported = published.with_entities(func.coalesce(func.sum(FoodListing.portions_reported), 0)).scalar()
    collected = (
        db.query(func.coalesce(func.sum(PickupAssignment.collected_portions), 0))
        .filter(PickupAssignment.status.in_(["PICKED_UP", "DELIVERED"]))
        .scalar()
    )
    delivered, completed = db.query(
        func.coalesce(func.sum(DeliveryConfirmation.delivered_portions), 0), func.count(DeliveryConfirmation.id)
    ).one()
    accepted = published.filter(FoodListing.accepted_at.isnot(None)).with_entities(FoodListing.published_at, FoodListing.accepted_at).all()
    mins = [(a - p).total_seconds() / 60 for p, a in accepted if a and p and a >= p]
    terminal = published.filter(FoodListing.status.in_(TERMINAL_AFTER_PUBLISH)).count()
    delivered_listings = published.filter(FoodListing.status == "DELIVERED").count()
    predicted = (
        db.query(func.coalesce(func.sum(FoodListing.predicted_surplus_portions), 0))
        .filter(FoodListing.predicted_surplus_portions.isnot(None))
        .scalar()
    )
    return {
        "reported_portions": int(reported or 0),
        "collected_portions": int(collected or 0),
        "delivered_portions": int(delivered or 0),
        "completed_donations": int(completed or 0),
        "average_matching_minutes": round(sum(mins) / len(mins), 1) if mins else None,
        "collection_success_rate": round(delivered_listings / terminal, 3) if terminal else None,
        "predicted_surplus_portions": int(predicted or 0),
        "verified_ngos": db.query(NgoProfile).filter(NgoProfile.verification_status == "VERIFIED").count(),
        "definitions": {
            "reported_portions": "Portions donors reported on published listings (self-reported, not measured).",
            "collected_portions": "Portions volunteers confirmed collecting at pickup.",
            "delivered_portions": "Portions confirmed delivered - counted only after delivery confirmation.",
            "average_matching_minutes": "Mean time from publishing to NGO acceptance.",
            "collection_success_rate": "Delivered listings / listings that reached delivered, expired or cancelled after publishing.",
            "predicted_surplus_portions": "Sum of donor-saved PREDICTIONS - estimates only, never counted as rescued food.",
        },
    }


@router.get("/api/impact/public")
def public_impact(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Aggregate statistics only - no personal data. Used on the landing page."""
    if not flag_service.is_enabled(db, "impact_dashboard"):
        return {"enabled": False}
    n = impact_numbers(db)
    demo = db.query(FoodListing).filter(FoodListing.is_demo.is_(True)).count() > 0
    return {"enabled": True, "includes_demo_data": demo, **{k: n[k] for k in ("delivered_portions", "completed_donations", "verified_ngos", "collected_portions")}}


@router.get("/api/impact")
def impact(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Dict[str, Any]:
    if not flag_service.is_enabled(db, "impact_dashboard"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Impact dashboard is currently disabled.")
    n = impact_numbers(db)
    by_day = (
        db.query(func.date(DeliveryConfirmation.created_at), func.sum(DeliveryConfirmation.delivered_portions))
        .group_by(func.date(DeliveryConfirmation.created_at))
        .order_by(func.date(DeliveryConfirmation.created_at))
        .all()
    )
    by_cat = (
        db.query(FoodListing.food_category, func.sum(DeliveryConfirmation.delivered_portions))
        .join(DeliveryConfirmation, DeliveryConfirmation.listing_id == FoodListing.id)
        .group_by(FoodListing.food_category)
        .all()
    )
    demo = db.query(FoodListing).filter(FoodListing.is_demo.is_(True)).count() > 0
    return {
        **n,
        "includes_demo_data": demo,
        "delivered_by_day": [{"date": str(d), "portions": int(p or 0)} for d, p in by_day],
        "delivered_by_category": [{"category": c, "portions": int(p or 0)} for c, p in by_cat],
    }


@router.get("/api/features")
def features(db: Session = Depends(get_db)) -> Dict[str, bool]:
    """Which features are enabled (names + booleans only)."""
    return flag_service.enabled_map(db)
