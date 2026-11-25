"""Seed Bengaluru DEMO data.

Every organisation and person created here is FICTIONAL and labelled "(DEMO)".
No real NGO partnership is implied. Run:  python -m app.seed [--reset]
"""
from __future__ import annotations

import argparse
import os
from datetime import timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import (
    DeliveryConfirmation,
    DonationAcceptance,
    DonationStatusHistory,
    DonorProfile,
    FoodListing,
    FoodSafetyCheck,
    NgoMatch,
    NgoProfile,
    PickupAssignment,
    User,
    VolunteerProfile,
)
from .security import hash_password
from .services.timegeo import utcnow

DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo@12345")
DOMAIN = "festiveplate.demo"

DONORS = [
    dict(email=f"shubha.mantapa@{DOMAIN}", full_name="Manjunath Rao (DEMO)", phone="+91 90000 00001", lang="kn",
         org="Shubha Kalyana Mantapa (DEMO)", type="WEDDING_HALL",
         address="(DEMO) 2nd Cross, Electronic City Phase 1, Bengaluru 560100", area="Electronic City", lat=12.8458, lng=77.6612),
    dict(email=f"udupi.grand@{DOMAIN}", full_name="Kavya Shetty (DEMO)", phone="+91 90000 00002", lang="en",
         org="Udupi Grand Restaurant (DEMO)", type="RESTAURANT",
         address="(DEMO) 80 Feet Road, Koramangala 4th Block, Bengaluru 560034", area="Koramangala", lat=12.9340, lng=77.6260),
    dict(email=f"hsr.caterers@{DOMAIN}", full_name="Imran Pasha (DEMO)", phone="+91 90000 00003", lang="hi",
         org="HSR Feast Caterers (DEMO)", type="CATERER",
         address="(DEMO) 27th Main, HSR Layout Sector 2, Bengaluru 560102", area="HSR Layout", lat=12.9105, lng=77.6460),
]

NGOS = [
    dict(key="annapoorna", email=f"annapoorna@{DOMAIN}", full_name="Shanthi Devi (DEMO)", lang="kn",
         org="Annapoorna Community Kitchen (DEMO)", reg="DEMO-KA-TRUST-0001", area="Begur",
         address="(DEMO) Begur Main Road, Bengaluru 560068", lat=12.8770, lng=77.6350, radius=10, cap=300,
         veg=True, nonveg=False, start=0, end=24, vehicle=False, status="VERIFIED"),
    dict(key="hasiru", email=f"hasiru@{DOMAIN}", full_name="Prakash Gowda (DEMO)", lang="en",
         org="Hasiru Food Bank (DEMO)", reg="DEMO-KA-SOC-0002", area="Bommanahalli",
         address="(DEMO) Hosur Road, Bommanahalli, Bengaluru 560068", lat=12.9030, lng=77.6240, radius=12, cap=500,
         veg=True, nonveg=True, start=0, end=24, vehicle=True, status="VERIFIED"),
    dict(key="nammaoota", email=f"nammaoota@{DOMAIN}", full_name="Farah Khan (DEMO)", lang="hi",
         org="Namma Oota Seva Trust (DEMO)", reg="DEMO-KA-TRUST-0003", area="HSR Layout",
         address="(DEMO) 14th Main, HSR Layout Sector 6, Bengaluru 560102", lat=12.9120, lng=77.6390, radius=10, cap=200,
         veg=True, nonveg=True, start=0, end=24, vehicle=False, status="VERIFIED"),
    dict(key="yelahanka", email=f"yelahanka@{DOMAIN}", full_name="Ramesh B (DEMO)", lang="kn",
         org="Yelahanka Seva Kendra (DEMO)", reg="DEMO-KA-SOC-0004", area="Yelahanka",
         address="(DEMO) Yelahanka New Town, Bengaluru 560064", lat=13.1007, lng=77.5963, radius=8, cap=250,
         veg=True, nonveg=True, start=0, end=24, vehicle=True, status="VERIFIED"),
    dict(key="jayanagar", email=f"jayanagar@{DOMAIN}", full_name="Geetha M (DEMO)", lang="kn",
         org="Jayanagar Morning Meals (DEMO)", reg="DEMO-KA-TRUST-0005", area="Jayanagar",
         address="(DEMO) 9th Block, Jayanagar, Bengaluru 560069", lat=12.9250, lng=77.5938, radius=15, cap=150,
         veg=True, nonveg=False, start=6, end=9, vehicle=False, status="VERIFIED"),
    dict(key="koramangala", email=f"kmc@{DOMAIN}", full_name="Neha Iyer (DEMO)", lang="en",
         org="Koramangala Meals Collective (DEMO)", reg="DEMO-KA-SOC-0006", area="Koramangala",
         address="(DEMO) 5th Block, Koramangala, Bengaluru 560095", lat=12.9352, lng=77.6245, radius=10, cap=200,
         veg=True, nonveg=True, start=0, end=24, vehicle=False, status="PENDING"),
]

VOLUNTEERS = [
    dict(email=f"ravi.volunteer@{DOMAIN}", full_name="Ravi Kumar (DEMO)", phone="+91 90000 00101", ngo="hasiru", vehicle="Two-wheeler", area="Bommanahalli", lang="kn"),
    dict(email=f"priya.volunteer@{DOMAIN}", full_name="Priya Nair (DEMO)", phone="+91 90000 00102", ngo="hasiru", vehicle="Van", area="Electronic City", lang="en"),
    dict(email=f"lakshmi.volunteer@{DOMAIN}", full_name="Lakshmi N (DEMO)", phone="+91 90000 00103", ngo="annapoorna", vehicle="Auto-rickshaw", area="Begur", lang="kn"),
    dict(email=f"arjun.volunteer@{DOMAIN}", full_name="Arjun S (DEMO)", phone="+91 90000 00104", ngo="nammaoota", vehicle="Two-wheeler", area="HSR Layout", lang="hi"),
]


def _user(db: Session, email: str, name: str, role: str, phone: Optional[str] = None, lang: str = "en") -> User:
    u = User(email=email, password_hash=hash_password(DEMO_PASSWORD), full_name=name, phone=phone, role=role,
             preferred_language=lang, is_demo=True)
    db.add(u)
    db.flush()
    return u


def _history(db: Session, listing: FoodListing, steps: List[tuple]) -> None:
    prev = None
    for status, when, actor, note in steps:
        db.add(DonationStatusHistory(listing_id=listing.id, from_status=prev, to_status=status,
                                     changed_by=actor.id if actor else None, note=note, created_at=when))
        prev = status


def seed(db: Session) -> Dict[str, int]:
    if db.query(User).filter(User.email == f"admin@{DOMAIN}").first():
        print("Demo data already present - skipping (use --reset to rebuild).")
        return {}
    now = utcnow()
    admin = _user(db, f"admin@{DOMAIN}", "Platform Admin (DEMO)", "ADMIN", "+91 90000 00000")

    donors: Dict[str, User] = {}
    for d in DONORS:
        u = _user(db, d["email"], d["full_name"], "DONOR", d["phone"], d["lang"])
        db.add(DonorProfile(user_id=u.id, organization_name=d["org"], donor_type=d["type"], address=d["address"],
                            area=d["area"], latitude=d["lat"], longitude=d["lng"]))
        donors[d["area"]] = u

    ngos: Dict[str, NgoProfile] = {}
    for n in NGOS:
        u = _user(db, n["email"], n["full_name"], "NGO", None, n["lang"])
        p = NgoProfile(user_id=u.id, organization_name=n["org"], registration_number=n["reg"], contact_person=n["full_name"],
                       address=n["address"], area=n["area"], latitude=n["lat"], longitude=n["lng"],
                       service_radius_km=n["radius"], daily_capacity_portions=n["cap"], accepts_veg=n["veg"],
                       accepts_non_veg=n["nonveg"], pickup_start_hour=n["start"], pickup_end_hour=n["end"],
                       has_vehicle=n["vehicle"], verification_status=n["status"])
        if n["status"] == "VERIFIED":
            p.verified_by, p.verified_at = admin.id, now - timedelta(days=30)
            p.verification_notes = "DEMO record - fictional organisation verified for hackathon demonstration only."
        db.add(p)
        db.flush()
        ngos[n["key"]] = p

    vols: Dict[str, User] = {}
    for v in VOLUNTEERS:
        u = _user(db, v["email"], v["full_name"], "VOLUNTEER", v["phone"], v["lang"])
        db.add(VolunteerProfile(user_id=u.id, ngo_id=ngos[v["ngo"]].id, vehicle_type=v["vehicle"], area=v["area"]))
        vols[v["email"]] = u
    db.flush()

    # ---- Historical, completed DEMO donations (so the impact dashboard has context) ----
    history_specs = [
        ("Koramangala", "Lunch buffet surplus - bisi bele bath, curd rice", "VEG", 60, "REFRIGERATED", 6, "nammaoota", f"arjun.volunteer@{DOMAIN}", 58, 55),
        ("HSR Layout", "Corporate event surplus - veg pulao, paneer curry", "VEG", 90, "HOT_HELD", 4, "hasiru", f"ravi.volunteer@{DOMAIN}", 90, 86),
        ("Electronic City", "Reception dinner surplus - rice, sambar, palya", "VEG", 120, "HOT_HELD", 2, "annapoorna", f"lakshmi.volunteer@{DOMAIN}", 115, 112),
        ("Koramangala", "Chicken biryani and raita", "NON_VEG", 40, "HOT_HELD", 1, "hasiru", f"priya.volunteer@{DOMAIN}", 40, 40),
    ]
    for area, title, cat, portions, storage, days_ago, ngo_key, vol_email, collected, delivered in history_specs:
        donor = donors[area]
        dp = donor.donor_profile or db.query(DonorProfile).filter(DonorProfile.user_id == donor.id).one()
        t0 = now - timedelta(days=days_ago, hours=3)
        ngo, vol = ngos[ngo_key], vols[vol_email]
        l = FoodListing(donor_id=donor.id, title=title, food_type=title.split(" - ")[-1], food_category=cat,
                        portions_reported=portions, prepared_at=t0 - timedelta(minutes=45), pickup_deadline=t0 + timedelta(hours=3),
                        storage_condition=storage, allergens="Dairy" if "curd" in title or "paneer" in title else "None declared",
                        pickup_address=dp.address, area=dp.area, latitude=dp.latitude, longitude=dp.longitude, status="DELIVERED",
                        accepted_ngo_id=ngo.id, is_demo=True, published_at=t0 + timedelta(minutes=2),
                        accepted_at=t0 + timedelta(minutes=14), created_at=t0, updated_at=t0 + timedelta(hours=2), version=6)
        db.add(l)
        db.flush()
        db.add(FoodSafetyCheck(listing_id=l.id, result="ELIGIBLE", issues=[], created_at=t0 + timedelta(minutes=2)))
        db.add(NgoMatch(listing_id=l.id, ngo_id=ngo.id, rank=1, score=82.0, distance_km=4.0, components={},
                        explanation="Historical DEMO match.", notified=True, created_at=t0 + timedelta(minutes=2)))
        db.add(DonationAcceptance(listing_id=l.id, ngo_id=ngo.id, decision="ACCEPTED", decided_by=ngo.user_id, created_at=t0 + timedelta(minutes=14)))
        a = PickupAssignment(listing_id=l.id, ngo_id=ngo.id, volunteer_id=vol.id, assigned_by=ngo.user_id, status="DELIVERED",
                             collected_portions=collected, picked_up_at=t0 + timedelta(minutes=50), delivered_at=t0 + timedelta(minutes=95),
                             created_at=t0 + timedelta(minutes=20))
        db.add(a)
        db.flush()
        db.add(DeliveryConfirmation(listing_id=l.id, assignment_id=a.id, collected_portions=collected, delivered_portions=delivered,
                                    delivery_location=ngo.address, confirmed_by_volunteer=vol.id, ngo_acknowledged_by=ngo.user_id,
                                    ngo_acknowledged_at=t0 + timedelta(minutes=100), receipt_number=f"FP-DEMO-{l.id:05d}",
                                    created_at=t0 + timedelta(minutes=95)))
        _history(db, l, [
            ("DRAFT", t0, donor, "Created manually (DEMO)"),
            ("PUBLISHED", t0 + timedelta(minutes=2), donor, "Passed automated screening (not a safety certification)"),
            ("MATCHED", t0 + timedelta(minutes=2), None, "Matched with verified NGO(s)"),
            ("ACCEPTED", t0 + timedelta(minutes=14), ngo.user, f"Accepted by {ngo.organization_name}"),
            ("PICKUP_ASSIGNED", t0 + timedelta(minutes=20), ngo.user, f"Pickup assigned to volunteer {vol.full_name}"),
            ("PICKED_UP", t0 + timedelta(minutes=50), vol, f"Collected {collected} portions (donor reported {portions})"),
            ("DELIVERED", t0 + timedelta(minutes=95), vol, f"Delivered {delivered} portions (collected {collected})"),
        ])

    # ---- One flagged listing awaiting admin review (missing storage information) ----
    hsr = donors["HSR Layout"]
    hp = db.query(DonorProfile).filter(DonorProfile.user_id == hsr.id).one()
    t = now - timedelta(minutes=20)
    flagged = FoodListing(donor_id=hsr.id, title="Sweets and snacks from a naming ceremony (DEMO)", food_type="mysore pak, kodubale, chips",
                          food_category="VEG", portions_reported=35, prepared_at=now - timedelta(hours=1), pickup_deadline=now + timedelta(hours=5),
                          storage_condition=None, allergens="Ghee, gram flour", pickup_address=hp.address, area=hp.area,
                          latitude=hp.latitude, longitude=hp.longitude, status="FLAGGED", is_demo=True, created_at=t, updated_at=t, version=2)
    db.add(flagged)
    db.flush()
    db.add(FoodSafetyCheck(listing_id=flagged.id, result="FLAGGED", created_at=t, issues=[
        {"code": "MISSING_STORAGE_INFO", "severity": "BLOCKING", "message": "Storage condition was not provided; an admin must review."}]))
    _history(db, flagged, [("DRAFT", t, hsr, "Created manually (DEMO)"),
                           ("FLAGGED", t, None, "Automated screening flagged: Storage condition was not provided; an admin must review.")])

    # ---- One expired listing (shows expiry handling) ----
    k = donors["Koramangala"]
    kp = db.query(DonorProfile).filter(DonorProfile.user_id == k.id).one()
    te = now - timedelta(days=1, hours=2)
    expired = FoodListing(donor_id=k.id, title="Dinner surplus - dosa batter and chutney (DEMO)", food_type="dosa batter, chutney",
                          food_category="VEG", portions_reported=25, prepared_at=te - timedelta(hours=1), pickup_deadline=te + timedelta(hours=1),
                          storage_condition="REFRIGERATED", allergens="None declared", pickup_address=kp.address, area=kp.area,
                          latitude=kp.latitude, longitude=kp.longitude, status="EXPIRED", is_demo=True,
                          published_at=te, created_at=te, updated_at=te + timedelta(hours=1), version=3)
    db.add(expired)
    db.flush()
    db.add(FoodSafetyCheck(listing_id=expired.id, result="ELIGIBLE", issues=[], created_at=te))
    _history(db, expired, [("DRAFT", te, k, "Created manually (DEMO)"),
                           ("PUBLISHED", te, k, "Passed automated screening (not a safety certification)"),
                           ("EXPIRED", te + timedelta(hours=1), None, "Pickup deadline passed before collection; excluded from matching.")])

    db.commit()
    return {"users": db.query(User).count(), "ngos": len(ngos), "listings": db.query(FoodListing).count()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="Drop and recreate ALL tables before seeding (destroys data)")
    ap.add_argument("--create-tables", action="store_true", help="Create tables without Alembic (local quick start)")
    args = ap.parse_args()
    if args.reset:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    elif args.create_tables:
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        out = seed(db)
    if out:
        print(f"Seeded DEMO data: {out}. All demo accounts use password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
