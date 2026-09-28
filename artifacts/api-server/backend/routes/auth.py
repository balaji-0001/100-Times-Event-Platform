from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.security import create_access_token, hash_password, verify_password
from backend.db import get_db
from backend.models import User
from backend.schemas import LoginInput, Session as SessionOut, UserInput, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def session_for(user: User) -> SessionOut:
    return SessionOut(user=UserOut.model_validate(user), token=create_access_token(user.id, user.role))


@router.post("/register", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserInput, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    from backend.services.audit import record_audit_log
    from backend.services.notifications import send_templated_notification

    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    role = payload.role if payload.role in ("USER", "ORGANIZER") else "USER"
    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        country=payload.country,
        role=role,
        company=payload.company,
    )
    db.add(user)
    try:
        db.flush()
        if role == "ORGANIZER":
            from backend.routes.platform_ops import _ensure_organizer_and_profile

            _ensure_organizer_and_profile(db, user)
        send_templated_notification(
            db,
            template_key="welcome",
            user_id=user.id,
            recipient_email=user.email,
            context={"name": user.name, "email": user.email},
        )
        record_audit_log(
            db,
            actor=user.email,
            actor_id=user.id,
            action="USER_SIGNUP",
            entity="User",
            entity_id=user.id,
            metadata={"role": role, "company": payload.company},
        )
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists") from exc
    session = session_for(user)
    response.set_cookie("access_token", session.token, httponly=True, samesite="lax", secure=False, max_age=60 * 24 * 60 * 60)
    return session


@router.post("/login", response_model=SessionOut)
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    session = session_for(user)
    response.set_cookie("access_token", session.token, httponly=True, samesite="lax", secure=False, max_age=60 * 24 * 60 * 60)
    return session


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(__import__("backend.dependencies", fromlist=["get_current_user"]).get_current_user)) -> UserOut:
    return UserOut.model_validate(user)