from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..deps import audit
from ..models import DonorProfile, NgoProfile, User, VolunteerProfile
from ..ratelimit import rate_limit
from ..security import create_access_token, hash_password, verify_password
from ..services.timegeo import utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenOut, status_code=201, dependencies=[Depends(rate_limit("auth"))])
def register(body: schemas.RegisterRequest, request: Request, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(
        email=email, password_hash=hash_password(body.password), full_name=body.full_name.strip(), phone=body.phone,
        role=body.role, preferred_language=body.preferred_language,
    )
    db.add(user)
    db.flush()
    if body.role == "DONOR":
        db.add(DonorProfile(user_id=user.id, **body.donor.model_dump()))
    elif body.role == "NGO":
        # Always PENDING: an administrator must verify the organisation before it can receive donations.
        db.add(NgoProfile(user_id=user.id, verification_status="PENDING", **body.ngo.model_dump()))
    elif body.role == "VOLUNTEER":
        ngo = db.get(NgoProfile, body.volunteer.ngo_id)
        if ngo is None or ngo.verification_status != "VERIFIED":
            db.rollback()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Volunteers must join a verified NGO.")
        db.add(VolunteerProfile(user_id=user.id, **body.volunteer.model_dump()))
    audit(db, user, "REGISTER", "user", user.id, {"role": body.role}, request)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    return schemas.TokenOut(access_token=create_access_token(user.id, user.role), user=schemas.UserOut.model_validate(user))


@router.post("/login", response_model=schemas.TokenOut, dependencies=[Depends(rate_limit("auth"))])
def login(body: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        audit(db, None, "LOGIN_FAILED", "user", user.id if user else None, {"email": body.email.lower()}, request)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated. Contact an administrator.")
    user.last_login_at = utcnow()
    audit(db, user, "LOGIN", "user", user.id, {}, request)
    db.commit()
    return schemas.TokenOut(access_token=create_access_token(user.id, user.role), user=schemas.UserOut.model_validate(user))


@router.get("/verified-ngos", response_model=List[schemas.NgoPublic])
def verified_ngos(db: Session = Depends(get_db)):
    """Public list (name + area only) so volunteers can pick their NGO when registering."""
    rows = db.query(NgoProfile).filter(NgoProfile.verification_status == "VERIFIED").order_by(NgoProfile.organization_name).all()
    return [schemas.NgoPublic(id=n.id, organization_name=n.organization_name, area=n.area) for n in rows]
