from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


def iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat()


def listing_payload(**overrides: Any) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    body = {
        "title": "Surplus wedding meals (TEST)",
        "food_type": "rice, sambar, palya, payasa",
        "food_category": "VEG",
        "portions_reported": 150,
        "prepared_at": iso(now - timedelta(hours=1)),
        "pickup_deadline": iso(now + timedelta(hours=3)),
        "storage_condition": "HOT_HELD",
        "allergens": "Dairy (payasa)",
        "pickup_address": "(DEMO) 2nd Cross, Electronic City Phase 1, Bengaluru 560100",
        "area": "Electronic City",
        "latitude": 12.8458,
        "longitude": 77.6612,
    }
    body.update(overrides)
    return body


def create_and_publish(client, donor_headers, **overrides) -> Dict[str, Any]:
    r = client.post("/api/listings", json=listing_payload(**overrides), headers=donor_headers)
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    r = client.post(f"/api/listings/{lid}/publish", headers=donor_headers)
    assert r.status_code == 200, r.text
    return r.json()


def ngo_id(client, ngo_headers) -> int:
    return client.get("/api/ngo/profile", headers=ngo_headers).json()["id"]


def volunteer_id(client, vol_headers) -> int:
    return client.get("/api/me", headers=vol_headers).json()["user"]["id"]


def assignment_for(client, vol_headers, listing_id: int) -> Optional[int]:
    for a in client.get("/api/volunteer/assignments", headers=vol_headers).json():
        if a["listing"]["id"] == listing_id:
            return a["assignment_id"]
    return None
