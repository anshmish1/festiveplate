from __future__ import annotations

from typing import Callable, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import AuditLog, NgoProfile, User
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_access_token(creds.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found or deactivated")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This action requires role: {', '.join(roles)}")
        return user

    return _dep


def get_ngo_profile(user: User = Depends(require_roles("NGO")), db: Session = Depends(get_db)) -> NgoProfile:
    ngo = db.query(NgoProfile).filter(NgoProfile.user_id == user.id).one_or_none()
    if ngo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NGO profile not found")
    return ngo


def require_verified_ngo(ngo: NgoProfile = Depends(get_ngo_profile)) -> NgoProfile:
    if ngo.verification_status != "VERIFIED":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Your organisation must be verified by a FestivePlate administrator before it can receive donations.",
        )
    return ngo


def audit(
    db: Session,
    actor: Optional[User],
    action: str,
    entity_type: str,
    entity_id: Optional[int],
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            ip_address=(request.client.host if request and request.client else None),
        )
    )
