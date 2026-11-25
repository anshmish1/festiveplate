"""Acceptance concurrency and expiry."""
from __future__ import annotations

import threading
from datetime import timedelta

from fastapi import HTTPException

from app.database import SessionLocal
from app.models import DonationAcceptance, FoodListing, NgoMatch, NgoProfile, User
from app.services import lifecycle, workflow
from app.services.timegeo import utcnow

from .helpers import create_and_publish, listing_payload

DONOR = "shubha.mantapa"


def test_two_ngos_cannot_accept_same_listing_sequential_race(client, as_user):
    """Both NGOs load the listing while it is open, then both try to accept."""
    out = create_and_publish(client, as_user(DONOR))
    lid = out["listing"]["id"]
    s1, s2 = SessionLocal(), SessionLocal()
    try:
        ngo1 = s1.query(NgoProfile).filter(NgoProfile.organization_name.like("Hasiru%")).one()
        ngo2 = s2.query(NgoProfile).filter(NgoProfile.organization_name.like("Annapoorna%")).one()
        assert s1.get(FoodListing, lid).status == "MATCHED"
        assert s2.get(FoodListing, lid).status == "MATCHED"  # stale view in session 2
        workflow.accept(s1, lid, ngo1, s1.get(User, ngo1.user_id))
        try:
            workflow.accept(s2, lid, ngo2, s2.get(User, ngo2.user_id))
            raise AssertionError("second acceptance must fail")
        except HTTPException as exc:
            assert exc.status_code == 409
    finally:
        s1.close()
        s2.close()
    with SessionLocal() as db:
        l = db.get(FoodListing, lid)
        assert l.status == "ACCEPTED"
        assert db.query(DonationAcceptance).filter_by(listing_id=lid, decision="ACCEPTED").count() == 1


def test_parallel_acceptance_exactly_one_winner(client, as_user):
    out = create_and_publish(client, as_user(DONOR))
    lid = out["listing"]["id"]
    with SessionLocal() as db:
        ngo_ids = [m.ngo_id for m in db.query(NgoMatch).filter_by(listing_id=lid).all()]
    assert len(ngo_ids) == 3
    results: list = []
    barrier = threading.Barrier(len(ngo_ids))

    def attempt(nid: int) -> None:
        with SessionLocal() as s:
            ngo = s.get(NgoProfile, nid)
            user = s.get(User, ngo.user_id)
            barrier.wait()
            try:
                workflow.accept(s, lid, ngo, user)
                results.append(("ok", nid))
            except HTTPException as exc:
                results.append((exc.status_code, nid))
            except Exception as exc:  # e.g. sqlite "database is locked" - still not a double accept
                results.append(("error:" + type(exc).__name__, nid))

    threads = [threading.Thread(target=attempt, args=(n,)) for n in ngo_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    winners = [r for r in results if r[0] == "ok"]
    assert len(winners) == 1, results
    with SessionLocal() as db:
        assert db.query(DonationAcceptance).filter_by(listing_id=lid, decision="ACCEPTED").count() == 1
        assert db.get(FoodListing, lid).accepted_ngo_id == winners[0][1]


def test_listing_expires_and_is_excluded(client, as_user):
    out = create_and_publish(client, as_user(DONOR))
    lid = out["listing"]["id"]
    with SessionLocal() as db:
        l = db.get(FoodListing, lid)
        l.pickup_deadline = utcnow() - timedelta(minutes=1)
        db.commit()
    # Any read triggers expiry processing
    detail = client.get(f"/api/listings/{lid}", headers=as_user(DONOR)).json()
    assert detail["status"] == "EXPIRED"
    assert detail["history"][-1]["to_status"] == "EXPIRED"
    assert lid not in [l["id"] for l in client.get("/api/ngo/listings/available", headers=as_user("hasiru")).json()]
    r = client.post(f"/api/ngo/listings/{lid}/accept", json={}, headers=as_user("hasiru"))
    assert r.status_code == 409


def test_accept_rejected_after_deadline_even_before_expiry_job(client, as_user):
    out = create_and_publish(client, as_user(DONOR))
    lid = out["listing"]["id"]
    with SessionLocal() as db:
        l = db.get(FoodListing, lid)
        l.pickup_deadline = utcnow() - timedelta(seconds=5)
        db.commit()
        ngo = db.query(NgoProfile).filter(NgoProfile.organization_name.like("Hasiru%")).one()
        try:
            workflow.accept(db, lid, ngo, db.get(User, ngo.user_id))
            raise AssertionError("expected conflict")
        except HTTPException as exc:
            assert exc.status_code == 409


def test_draft_past_deadline_expires_and_cannot_be_published(client, as_user):
    from .helpers import iso

    now = utcnow()
    h = as_user(DONOR)
    r = client.post("/api/listings", json=listing_payload(prepared_at=iso(now - timedelta(hours=3)), pickup_deadline=iso(now - timedelta(minutes=5))), headers=h)
    assert r.status_code == 201
    lid = r.json()["id"]
    r = client.post(f"/api/listings/{lid}/publish", headers=h)
    assert r.status_code == 409
    assert client.get(f"/api/listings/{lid}", headers=h).json()["status"] == "EXPIRED"


def test_assigned_pickup_expires_and_assignment_cancelled(client, as_user):
    from .helpers import assignment_for, volunteer_id

    out = create_and_publish(client, as_user(DONOR))
    lid = out["listing"]["id"]
    ngo_h, vol_h = as_user("hasiru"), as_user("ravi.volunteer")
    client.post(f"/api/ngo/listings/{lid}/accept", json={}, headers=ngo_h)
    client.post(f"/api/ngo/listings/{lid}/assign", json={"volunteer_user_id": volunteer_id(client, vol_h)}, headers=ngo_h)
    aid = assignment_for(client, vol_h, lid)
    with SessionLocal() as db:
        db.get(FoodListing, lid).pickup_deadline = utcnow() - timedelta(minutes=1)
        db.commit()
        assert lifecycle.expire_overdue(db) == 1
    r = client.post(f"/api/volunteer/assignments/{aid}/pickup", data={"collected_portions": "10"}, headers=vol_h)
    assert r.status_code == 409
