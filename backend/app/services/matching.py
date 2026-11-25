"""NGO matching engine.

Only NGOs that an administrator has VERIFIED are ever considered. Hard filters
remove NGOs that cannot legitimately take the donation; the remaining NGOs are
scored 0-100 and every score comes with a plain-language explanation built from
the same numbers used to rank it (no invented reasons).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import FoodListing, NgoMatch, NgoProfile, User
from .timegeo import fmt_ist, haversine_km, utcnow

WEIGHTS = {"distance": 35, "capacity": 20, "reachability": 20, "availability": 10, "preference": 10, "vehicle": 5}
MAX_MATCHES = 5
EMERGENCY_RADIUS_MULTIPLIER = 1.5


@dataclass
class Candidate:
    ngo: NgoProfile
    eligible: bool
    score: float = 0.0
    distance_km: float = 0.0
    components: Dict[str, float] = field(default_factory=dict)
    facts: Dict[str, object] = field(default_factory=dict)
    exclusion_reasons: List[str] = field(default_factory=list)
    explanation: str = ""


def _ist_hour_intervals(start_hour: int, end_hour: int, frm: datetime, to: datetime) -> List[Tuple[datetime, datetime]]:
    """Availability intervals (naive UTC) for an NGO's daily IST pickup hours between frm and to."""
    offset = timedelta(hours=5, minutes=30)
    out = []
    day = (frm + offset).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    last = (to + offset).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    while day <= last:
        s = day + timedelta(hours=start_hour)
        e = day + timedelta(hours=end_hour if end_hour > start_hour else end_hour + 24)
        out.append((s - offset, e - offset))
        day += timedelta(days=1)
    return out


def availability_overlap_hours(ngo: NgoProfile, frm: datetime, to: datetime) -> float:
    if to <= frm:
        return 0.0
    if ngo.pickup_start_hour == 0 and ngo.pickup_end_hour == 24:
        return (to - frm).total_seconds() / 3600
    total = 0.0
    for s, e in _ist_hour_intervals(ngo.pickup_start_hour, ngo.pickup_end_hour, frm, to):
        lo, hi = max(s, frm), min(e, to)
        if hi > lo:
            total += (hi - lo).total_seconds()
    return total / 3600


def capacity_used_today(db: Session, ngo_id: int, now: datetime) -> int:
    offset = timedelta(hours=5, minutes=30)
    ist_midnight = (now + offset).replace(hour=0, minute=0, second=0, microsecond=0) - offset
    used = (
        db.query(func.coalesce(func.sum(FoodListing.portions_reported), 0))
        .filter(
            FoodListing.accepted_ngo_id == ngo_id,
            FoodListing.accepted_at >= ist_midnight,
            FoodListing.status.notin_(["CANCELLED", "EXPIRED"]),
        )
        .scalar()
    )
    return int(used or 0)


def _fmt_hours(ngo: NgoProfile) -> str:
    if ngo.pickup_start_hour == 0 and ngo.pickup_end_hour == 24:
        return "round the clock"

    def h(x: int) -> str:
        x = x % 24
        suffix = "AM" if x < 12 else "PM"
        return f"{(x % 12) or 12} {suffix}"

    return f"between {h(ngo.pickup_start_hour)} and {h(ngo.pickup_end_hour)}"


def evaluate(db: Session, listing: FoodListing, ngo: NgoProfile, now: datetime, emergency: bool) -> Candidate:
    s = get_settings()
    c = Candidate(ngo=ngo, eligible=True)
    c.distance_km = round(haversine_km(listing.latitude, listing.longitude, ngo.latitude, ngo.longitude), 2)
    radius = ngo.service_radius_km * (EMERGENCY_RADIUS_MULTIPLIER if emergency else 1.0)

    if ngo.verification_status != "VERIFIED":
        c.exclusion_reasons.append("organisation is not verified by an administrator")
    if not ngo.user.is_active:
        c.exclusion_reasons.append("account is deactivated")
    if c.distance_km > radius:
        c.exclusion_reasons.append(f"{c.distance_km:.1f} km away, outside its {radius:.0f} km service area")
    veg_food = listing.food_category == "VEG"
    if veg_food and not ngo.accepts_veg:
        c.exclusion_reasons.append("does not accept vegetarian food")
    if not veg_food and not ngo.accepts_non_veg:
        c.exclusion_reasons.append("accepts vegetarian food only")

    remaining = ngo.daily_capacity_portions - capacity_used_today(db, ngo.id, now)
    if remaining <= 0:
        c.exclusion_reasons.append("has no remaining capacity today")

    travel_min = c.distance_km / s.volunteer_speed_kmph * 60
    minutes_left = (listing.pickup_deadline - now).total_seconds() / 60
    if travel_min >= minutes_left:
        c.exclusion_reasons.append("cannot reach the pickup before the deadline")

    overlap = availability_overlap_hours(ngo, now, listing.pickup_deadline - timedelta(minutes=travel_min))
    if overlap <= 0:
        c.exclusion_reasons.append(f"collects only {_fmt_hours(ngo)}, which does not overlap the pickup window")

    if c.exclusion_reasons:
        c.eligible = False
        return c

    window_h = max(minutes_left / 60, 1e-6)
    comp = {
        "distance": max(0.0, 1 - c.distance_km / radius),
        "capacity": min(1.0, remaining / listing.portions_reported),
        "reachability": max(0.0, min(1.0, (minutes_left - travel_min) / max(minutes_left, 1))),
        "availability": min(1.0, overlap / window_h),
        "preference": 1.0 if (veg_food and not ngo.accepts_non_veg) or (not veg_food and ngo.accepts_non_veg and not ngo.accepts_veg) else 0.8,
        "vehicle": 1.0 if ngo.has_vehicle else (0.6 if listing.portions_reported <= 50 else 0.2),
    }
    c.components = {k: round(v, 3) for k, v in comp.items()}
    c.score = round(sum(WEIGHTS[k] * v for k, v in comp.items()), 1)
    c.facts = {
        "remaining_capacity": remaining,
        "travel_minutes": round(travel_min),
        "minutes_to_deadline": round(minutes_left),
        "service_radius_km": radius,
        "pickup_hours": _fmt_hours(ngo),
        "emergency_radius": emergency,
    }
    c.explanation = explain(listing, c)
    return c


def explain(listing: FoodListing, c: Candidate) -> str:
    f = c.facts
    parts = [
        f"{c.ngo.organization_name} is {c.distance_km:.1f} km from the pickup point"
        f" (inside its {f['service_radius_km']:.0f} km service area"
        + (", widened for an urgent pickup" if f["emergency_radius"] else "")
        + ")",
    ]
    if f["remaining_capacity"] >= listing.portions_reported:
        parts.append(f"it has room for all {listing.portions_reported} portions today ({f['remaining_capacity']} remaining)")
    else:
        parts.append(
            f"it can take about {f['remaining_capacity']} of the {listing.portions_reported} portions today, so it ranks lower on capacity"
        )
    food = "vegetarian" if listing.food_category == "VEG" else "non-vegetarian / mixed"
    parts.append(f"it accepts {food} food")
    parts.append(f"it collects {f['pickup_hours']}")
    parts.append(
        f"a volunteer could reach the pickup in about {f['travel_minutes']} minutes, before the deadline of {fmt_ist(listing.pickup_deadline)}"
    )
    if c.ngo.has_vehicle:
        parts.append("it has its own vehicle")
    return "Matched because " + "; ".join(parts) + f". Overall score {c.score:.0f}/100."


def rank_ngos(db: Session, listing: FoodListing, emergency_enabled: bool, now: Optional[datetime] = None) -> Tuple[List[Candidate], List[Candidate], bool]:
    now = now or utcnow()
    s = get_settings()
    emergency = emergency_enabled and (listing.pickup_deadline - now) <= timedelta(minutes=s.emergency_window_minutes)
    ngos = db.query(NgoProfile).join(User, User.id == NgoProfile.user_id).filter(NgoProfile.verification_status == "VERIFIED").all()
    evaluated = [evaluate(db, listing, n, now, emergency) for n in ngos]
    eligible = sorted([c for c in evaluated if c.eligible], key=lambda c: (-c.score, c.distance_km))
    excluded = [c for c in evaluated if not c.eligible]
    return eligible, excluded, emergency


def run_matching(db: Session, listing: FoodListing, emergency_enabled: bool) -> List[NgoMatch]:
    """Persist the top matches for a listing (replacing previous ones). Caller commits."""
    eligible, _excluded, emergency = rank_ngos(db, listing, emergency_enabled)
    listing.emergency = emergency
    db.query(NgoMatch).filter(NgoMatch.listing_id == listing.id).delete(synchronize_session=False)
    matches = []
    for i, c in enumerate(eligible[:MAX_MATCHES], start=1):
        m = NgoMatch(
            listing_id=listing.id,
            ngo_id=c.ngo.id,
            rank=i,
            score=c.score,
            distance_km=c.distance_km,
            components={**c.components, **{"facts": c.facts}},
            explanation=c.explanation,
        )
        db.add(m)
        matches.append(m)
    db.flush()
    return matches
