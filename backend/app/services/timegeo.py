"""Time-zone and geography helpers.

Storage convention: naive datetimes in UTC. Bengaluru operates in IST (UTC+5:30).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: datetime) -> datetime:
    """Normalise any datetime to naive UTC. Naive inputs are assumed to be UTC already."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def to_ist(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(IST)


def fmt_ist(dt: datetime) -> str:
    return to_ist(dt).strftime("%d %b %Y, %I:%M %p IST")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def approx_coord(value: float) -> float:
    """Round coordinates to ~1 km so un-authorised viewers never see precise donor locations."""
    return round(value, 2)
