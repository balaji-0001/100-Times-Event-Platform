import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.rate_limiter import rate_limit_auth
from backend.core.security import create_access_token, hash_password, verify_password
from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import (
    AttendeeProfile,
    AuditLog,
    EmailVerificationToken,
    Event,
    Notification,
    Organizer,
    PasswordResetToken,
    Registration,
    Review,
    SavedEvent,
    ScheduleItem,
    User,
)
from backend.schemas import (
    DeleteAccountInput,
    ForgotPasswordInput,
    LoginInput,
    ResetPasswordInput,
    Session as SessionOut,
    UserInput,
    UserOut,
    VerifyEmailInput,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# One message for both "no such account" and "wrong password", so the login
# endpoint does not reveal which emails have accounts.
INVALID_LOGIN_MESSAGE = "Incorrect email or password"


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(24))


def _frontend_link(path: str, token: str) -> str:
    """Absolute link into the web app for emails (PUBLIC_APP_URL setting)."""
    base = (get_settings().public_app_url or "").strip().rstrip("/")
    return f"{base}{path}?{urlencode({'token': token})}"


def session_for(user: User) -> SessionOut:
    return SessionOut(user=UserOut.model_validate(user), token=create_access_token(user.id, user.role))


def _set_auth_cookie(response: Response, token: str) -> None:
    is_prod = get_settings().environment.lower() == "production"
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        secure=is_prod,
        max_age=60 * 24 * 60 * 60,
    )


@router.post("/register", response_model=SessionOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit_auth)])
def register(payload: UserInput, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    from backend.services.audit import record_audit_log
    from backend.services.notifications import send_templated_notification

    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    # Attendee and organiser accounts are separate and the type is fixed at sign-up
    # (`accountType`); a raw `role` in the payload is ignored and ADMIN is never
    # self-assigned. An organiser account can list events, which still go through
    # trust review and an admin before anything is published.
    is_organiser = payload.account_type == "organiser"
    role = "ORGANIZER" if is_organiser else "USER"
    company = (payload.company or "").strip() or None

    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        country=payload.country,
        role=role,
        roles_list=["organiser"] if is_organiser else ["attendee"],
        email_verified=False,
        company=company if is_organiser else None,
    )
    db.add(user)
    try:
        db.flush()
        if is_organiser:
            from backend.routes.platform_ops import _ensure_organizer_and_profile

            _ensure_organizer_and_profile(db, user)
        else:
            db.add(AttendeeProfile(user_id=user.id, country=payload.country, company=company))

        # Generate single-use expiring email verification token (24 hours)
        raw_verification_token = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw_verification_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        verif_record = EmailVerificationToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(verif_record)

        # Welcome notification
        send_templated_notification(
            db,
            template_key="welcome",
            user_id=user.id,
            recipient_email=user.email,
            context={"name": user.name, "email": user.email},
        )

        # Verification email notification
        verification_link = _frontend_link("/verify-email", raw_verification_token)
        send_templated_notification(
            db,
            template_key="email_verification",
            user_id=user.id,
            recipient_email=user.email,
            context={"name": user.name, "email": user.email, "verification_link": verification_link},
        )

        record_audit_log(
            db,
            actor=user.email,
            actor_id=user.id,
            action="USER_SIGNUP",
            entity="User",
            entity_id=user.id,
            metadata={"role": role, "account_type": payload.account_type, "company": company, "email_verified": False},
        )
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists") from exc

    session = session_for(user)
    _set_auth_cookie(response, session.token)
    return session


@router.post("/login", response_model=SessionOut, dependencies=[Depends(rate_limit_auth)])
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    email_clean = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email_clean))
    if user is None:
        # Spend the same hashing work as a real check so response timing does
        # not reveal whether the account exists either.
        verify_password(payload.password, _dummy_password_hash())
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN_MESSAGE)
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN_MESSAGE)
    session = session_for(user)
    _set_auth_cookie(response, session.token)
    return session


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(response: Response) -> dict[str, str]:
    is_prod = get_settings().environment.lower() == "production"
    response.delete_cookie(
        "access_token",
        httponly=True,
        samesite="lax",
        secure=is_prod,
    )
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/send-verification-email", dependencies=[Depends(rate_limit_auth)])
def send_verification_email(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    from backend.services.notifications import send_templated_notification

    if user.email_verified:
        return {"message": "Email is already verified."}

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    record = EmailVerificationToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()

    verification_link = _frontend_link("/verify-email", raw_token)
    send_templated_notification(
        db,
        template_key="email_verification",
        user_id=user.id,
        recipient_email=user.email,
        context={"name": user.name, "email": user.email, "verification_link": verification_link},
    )
    return {"message": "Verification email sent. Please check your inbox."}


@router.post("/verify-email", dependencies=[Depends(rate_limit_auth)])
def verify_email(payload: VerifyEmailInput, db: Session = Depends(get_db)) -> dict[str, str]:
    from backend.services.audit import record_audit_log

    token_hash = _hash_token(payload.token.strip())
    record = db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.used_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    if not record or (record.expires_at and record.expires_at.replace(tzinfo=timezone.utc) < now):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification link.")

    user = db.get(User, record.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User account not found.")

    user.email_verified = True
    record.used_at = now

    record_audit_log(
        db,
        actor=user.email,
        actor_id=user.id,
        action="USER_EMAIL_VERIFIED",
        entity="User",
        entity_id=user.id,
        metadata={"verified_at": now.isoformat()},
    )
    db.commit()
    return {"message": "Your email address has been successfully verified!"}


@router.post("/forgot-password", dependencies=[Depends(rate_limit_auth)])
def forgot_password(payload: ForgotPasswordInput, db: Session = Depends(get_db)) -> dict[str, str]:
    from backend.services.notifications import send_templated_notification

    # Generic response returned unconditionally to prevent user account enumeration
    generic_msg = "If an account with this email exists, a password reset link has been sent."

    email = payload.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        return {"message": generic_msg}

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    record = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()

    reset_link = _frontend_link("/reset-password", raw_token)
    send_templated_notification(
        db,
        template_key="password_reset",
        user_id=user.id,
        recipient_email=user.email,
        context={"name": user.name, "email": user.email, "reset_link": reset_link},
    )
    return {"message": generic_msg}


@router.post("/reset-password", dependencies=[Depends(rate_limit_auth)])
def reset_password(payload: ResetPasswordInput, db: Session = Depends(get_db)) -> dict[str, str]:
    from backend.services.audit import record_audit_log

    token_hash = _hash_token(payload.token.strip())
    record = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    if not record or (record.expires_at and record.expires_at.replace(tzinfo=timezone.utc) < now):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired password reset link.")

    user = db.get(User, record.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User account not found.")

    user.password_hash = hash_password(payload.new_password)
    record.used_at = now

    record_audit_log(
        db,
        actor=user.email,
        actor_id=user.id,
        action="USER_PASSWORD_RESET",
        entity="User",
        entity_id=user.id,
        metadata={"reset_at": now.isoformat()},
    )
    db.commit()
    return {"message": "Your password has been successfully reset. You may now sign in."}


@router.post("/delete-account")
def delete_account(
    payload: DeleteAccountInput,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    from backend.services.audit import record_audit_log

    if payload.confirmation.strip().upper() != "DELETE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please type 'DELETE' to confirm account removal.")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password. Account deletion aborted.")

    user_id = user.id
    user_email = user.email

    # Anonymize registrations to retain event audit and ticket count integrity
    registrations = db.scalars(select(Registration).where(Registration.user_id == user_id)).all()
    for reg in registrations:
        reg.user_id = None
        reg.attendee_name = "Former Member"
        reg.attendee_email = f"deleted-{user_id}@100times.anonymized"

    # Safely detach organizer ownership if user owns organizer entities
    organizers = db.scalars(select(Organizer).where(Organizer.user_id == user_id)).all()
    for org in organizers:
        org.user_id = None
        org.email = f"archived-organizer-{org.id}@100times.in"

    # Delete schedule items, saved events, notifications, reviews
    for item in db.scalars(select(ScheduleItem).where(ScheduleItem.user_id == user_id)).all():
        db.delete(item)
    for saved in db.scalars(select(SavedEvent).where(SavedEvent.user_id == user_id)).all():
        db.delete(saved)
    for note in db.scalars(select(Notification).where(Notification.user_id == user_id)).all():
        db.delete(note)
    for rev in db.scalars(select(Review).where(Review.user_id == user_id)).all():
        db.delete(rev)

    # Record security audit log before removing user record
    record_audit_log(
        db,
        actor=user_email,
        actor_id=user_id,
        action="USER_ACCOUNT_DELETED",
        entity="User",
        entity_id=user_id,
        metadata={"deleted_at": datetime.now(timezone.utc).isoformat(), "reason": "User requested self-deletion"},
    )

    # Delete user record
    db.delete(user)
    db.commit()

    # Clear auth cookie
    is_prod = get_settings().environment.lower() == "production"
    response.delete_cookie(
        "access_token",
        httponly=True,
        samesite="lax",
        secure=is_prod,
    )

    return {"message": "Your account and personal data have been permanently removed."}
