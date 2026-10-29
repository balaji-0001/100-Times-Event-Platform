from collections.abc import Callable

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from backend.core.security import decode_access_token
from backend.db import get_db
from backend.models import User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials else access_token
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    return user


def optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    token = credentials.credentials if credentials else access_token
    if token is None:
        return None
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        return None
    return db.get(User, user_id)


def require_roles(*roles: str) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        # Check either has_role (supporting multi-roles and case-insensitivity) or direct role matching
        has_permission = False
        if hasattr(user, "has_role"):
            has_permission = user.has_role(*roles)
        if not has_permission and user.role in roles:
            has_permission = True
        # Also check uppercase/lowercase
        if not has_permission and any(r.upper() == (user.role or "").upper() for r in roles):
            has_permission = True

        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency

# Attendee and organiser accounts are separate (see `User.roles`): attendee-only
# endpoints refuse organiser accounts and organiser-only endpoints refuse
# attendee accounts. Admins pass both.
require_attendee = require_roles("attendee")
require_organiser = require_roles("ORGANIZER", "ADMIN")
