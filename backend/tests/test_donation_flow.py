"""Integration tests: donation creation, matching, acceptance, pickup, delivery, privacy."""
from __future__ import annotations

from app.models import FoodListing

from .helpers import assignment_for, create_and_publish, listing_payload, ngo_id, volunteer_id

DONOR = "shubha.mantapa"


def test_create_listing_is_draft_with_history(client, as_user):
    r = client.post("/api/listings", json=listing_payload(), headers=as_user(DONOR))
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "DRAFT"
    assert [h["to_status"] for h in body["history"]] == ["DRAFT"]
    assert body["matches"] == []


def test_create_listing_validation(client, as_user):
    h = as_user(DONOR)
    bad = listing_payload(portions_reported=0)
    assert client.post("/api/listings", json=bad, headers=h).status_code == 422
    p = listing_payload()
    p["pickup_deadline"], p["prepared_at"] = p["prepared_at"], p["pickup_deadline"]
    assert client.post("/api/listings", json=p, headers=h).status_code == 422
    # voice listings require explicit donor confirmation
    assert client.post("/api/listings", json=listing_payload(source="VOICE"), headers=h).status_code == 422
    assert client.post("/api/listings", json=listing_payload(source="VOICE", voice_confirmed=True), headers=h).status_code == 201


def test_only_donors_can_create(client, as_user):
    assert client.post("/api/listings", json=listing_payload(), headers=as_user("hasiru")).status_code == 403
    assert client.post("/api/listings", json=listing_payload()).status_code == 401


def test_publish_matches_three_verified_ngos_with_explanations(client, as_user):
    out = create_and_publish(client, as_user(DONOR))
    assert out["safety_result"] == "ELIGIBLE"
    assert out["listing"]["status"] == "MATCHED"
    names = [m["ngo_name"] for m in out["listing"]["matches"]]
    assert len(names) == 3, names
    assert set(names) == {"Annapoorna Community Kitchen (DEMO)", "Hasiru Food Bank (DEMO)", "Namma Oota Seva Trust (DEMO)"}
    # Pending NGO, far NGO, and NGO with non-overlapping hours are never matched
    assert "Koramangala Meals Collective (DEMO)" not in names
    assert "Yelahanka Seva Kendra (DEMO)" not in names
    for m in out["listing"]["matches"]:
        assert m["explanation"].startswith("Matched because")
        assert 0 <= m["score"] <= 100
    scores = [m["score"] for m in out["listing"]["matches"]]
    assert scores == sorted(scores, reverse=True)


def test_explain_match_lists_exclusions(client, as_user):
    out = create_and_publish(client, as_user(DONOR))
    r = client.get(f"/api/ai/explain-match/{out['listing']['id']}", headers=as_user(DONOR))
    assert r.status_code == 200
    excluded = {e["ngo"]: e["reasons"] for e in r.json()["excluded"]}
    assert any("service area" in x for x in excluded["Yelahanka Seva Kendra (DEMO)"])
    # unverified NGOs are never even evaluated
    assert "Koramangala Meals Collective (DEMO)" not in excluded


def test_flagged_listing_excluded_from_matching(client, as_user):
    out = create_and_publish(client, as_user(DONOR), storage_condition=None)
    assert out["safety_result"] == "FLAGGED"
    assert out["listing"]["status"] == "FLAGGED"
    assert out["matches_found"] == 0
    avail = client.get("/api/ngo/listings/available", headers=as_user("hasiru")).json()
    assert out["listing"]["id"] not in [l["id"] for l in avail]


def test_admin_clears_flag_then_matches(client, as_user):
    out = create_and_publish(client, as_user(DONOR), storage_condition=None)
    lid = out["listing"]["id"]
    r = client.post(f"/api/admin/listings/{lid}/safety-review", json={"decision": "CLEARED", "notes": "Called donor: food is in hot cases"}, headers=as_user("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "MATCHED"


def test_unverified_ngo_cannot_browse_or_accept(client, as_user):
    out = create_and_publish(client, as_user(DONOR))
    lid = out["listing"]["id"]
    h = as_user("kmc")  # PENDING verification
    assert client.get("/api/ngo/listings/available", headers=h).status_code == 403
    assert client.post(f"/api/ngo/listings/{lid}/accept", json={}, headers=h).status_code == 403


def test_unmatched_verified_ngo_cannot_accept(client, as_user):
    out = create_and_publish(client, as_user(DONOR))
    r = client.post(f"/api/ngo/listings/{out['listing']['id']}/accept", json={}, headers=as_user("yelahanka"))
    assert r.status_code == 403


def test_privacy_before_and_after_acceptance(client, as_user):
    out = create_and_publish(client, as_user(DONOR))
    lid = out["listing"]["id"]
    # matched NGO sees only approximate location and no donor contact
    v = client.get(f"/api/listings/{lid}", headers=as_user("hasiru")).json()
    assert v["location_precision"] == "approximate"
    assert v["pickup_address"] is None and v["donor_phone"] is None and v["donor_name"] is None
    assert v["latitude"] == round(12.8458, 2)
    # unrelated users cannot see it at all
    assert client.get(f"/api/listings/{lid}", headers=as_user("yelahanka")).status_code == 404
    assert client.get(f"/api/listings/{lid}", headers=as_user("udupi.grand")).status_code == 404
    # after acceptance the accepting NGO sees full details; other NGO does not
    assert client.post(f"/api/ngo/listings/{lid}/accept", json={}, headers=as_user("hasiru")).status_code == 200
    full = client.get(f"/api/listings/{lid}", headers=as_user("hasiru")).json()
    assert full["location_precision"] == "exact" and full["donor_phone"]
    other = client.get(f"/api/listings/{lid}", headers=as_user("annapoorna")).json()
    assert other["donor_phone"] is None


def test_full_journey_and_impact_only_after_delivery(client, as_user):
    donor, ngo_h, vol_h = as_user(DONOR), as_user("hasiru"), as_user("ravi.volunteer")
    before = client.get("/api/impact", headers=donor).json()

    out = create_and_publish(client, donor)
    lid = out["listing"]["id"]
    assert client.post(f"/api/ngo/listings/{lid}/accept", json={}, headers=ngo_h).json()["status"] == "ACCEPTED"

    r = client.post(f"/api/ngo/listings/{lid}/assign", json={"volunteer_user_id": volunteer_id(client, vol_h)}, headers=ngo_h)
    assert r.status_code == 200 and r.json()["status"] == "PICKUP_ASSIGNED"
    aid = assignment_for(client, vol_h, lid)

    # receipt not available yet
    assert client.get(f"/api/listings/{lid}/receipt", headers=donor).status_code == 409

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    r = client.post(f"/api/volunteer/assignments/{aid}/pickup", data={"collected_portions": "148", "notes": "2 portions spilled"},
                    files={"proof": ("proof.png", png, "image/png")}, headers=vol_h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PICKED_UP"
    mid = client.get("/api/impact", headers=donor).json()
    assert mid["collected_portions"] == before["collected_portions"] + 148
    assert mid["delivered_portions"] == before["delivered_portions"]  # not counted until delivery confirmed

    # cannot deliver more than collected
    assert client.post(f"/api/volunteer/assignments/{aid}/deliver", json={"delivered_portions": 149}, headers=vol_h).status_code == 400
    r = client.post(f"/api/volunteer/assignments/{aid}/deliver", json={"delivered_portions": 146, "delivery_location": "Hasiru shelter"}, headers=vol_h)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "DELIVERED"
    assert detail["delivery"]["collected_portions"] == 148 and detail["delivery"]["delivered_portions"] == 146
    assert [h["to_status"] for h in detail["history"]] == ["DRAFT", "PUBLISHED", "MATCHED", "ACCEPTED", "PICKUP_ASSIGNED", "PICKED_UP", "DELIVERED"]

    after = client.get("/api/impact", headers=donor).json()
    assert after["delivered_portions"] == before["delivered_portions"] + 146
    assert after["completed_donations"] == before["completed_donations"] + 1
    assert after["reported_portions"] == before["reported_portions"] + 150

    receipt = client.get(f"/api/listings/{lid}/receipt", headers=donor)
    assert receipt.status_code == 200
    rj = receipt.json()
    assert rj["portions_reported"] == 150 and rj["portions_collected"] == 148 and rj["portions_delivered"] == 146
    assert "not a food-safety certificate" in rj["statement"]

    assert client.post(f"/api/ngo/listings/{lid}/acknowledge", headers=ngo_h).status_code == 200
    assert client.get(f"/api/listings/{lid}/proof", headers=donor).status_code == 200

    notes = client.get("/api/me/notifications", headers=donor).json()
    assert {"ACCEPTED", "PICKED_UP", "DELIVERED"} <= {n["type"] for n in notes}


def test_volunteer_from_other_ngo_cannot_be_assigned(client, as_user):
    out = create_and_publish(client, as_user(DONOR))
    lid = out["listing"]["id"]
    client.post(f"/api/ngo/listings/{lid}/accept", json={}, headers=as_user("hasiru"))
    other_vol = volunteer_id(client, as_user("lakshmi.volunteer"))  # Annapoorna volunteer
    r = client.post(f"/api/ngo/listings/{lid}/assign", json={"volunteer_user_id": other_vol}, headers=as_user("hasiru"))
    assert r.status_code == 400


def test_volunteer_cannot_act_on_others_assignment(client, as_user):
    out = create_and_publish(client, as_user(DONOR))
    lid = out["listing"]["id"]
    ngo_h = as_user("hasiru")
    client.post(f"/api/ngo/listings/{lid}/accept", json={}, headers=ngo_h)
    client.post(f"/api/ngo/listings/{lid}/assign", json={"volunteer_user_id": volunteer_id(client, as_user("ravi.volunteer"))}, headers=ngo_h)
    aid = assignment_for(client, as_user("ravi.volunteer"), lid)
    r = client.post(f"/api/volunteer/assignments/{aid}/pickup", data={"collected_portions": "10"}, headers=as_user("priya.volunteer"))
    assert r.status_code == 404


def test_reject_records_decision(client, as_user, db):
    out = create_and_publish(client, as_user(DONOR))
    lid = out["listing"]["id"]
    assert client.post(f"/api/ngo/listings/{lid}/reject", json={"reason": "No volunteers tonight"}, headers=as_user("annapoorna")).status_code == 200
    assert client.post(f"/api/ngo/listings/{lid}/reject", json={}, headers=as_user("annapoorna")).status_code == 409
    avail = client.get("/api/ngo/listings/available", headers=as_user("annapoorna")).json()
    assert lid not in [l["id"] for l in avail]
    assert db.get(FoodListing, lid).status == "MATCHED"


def test_bad_image_rejected(client, as_user):
    r = client.post("/api/listings", json=listing_payload(), headers=as_user(DONOR))
    lid = r.json()["id"]
    r = client.post(f"/api/listings/{lid}/image", files={"file": ("x.png", b"<?php echo 1; ?>", "image/png")}, headers=as_user(DONOR))
    assert r.status_code == 415
