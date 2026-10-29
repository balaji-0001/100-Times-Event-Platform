"""Attendee profile — personal details of an attendee account.

Stored in `attendee_profiles`, never in organiser tables. A row is created the
first time it is needed; for accounts that existed before the table it starts
from the details those accounts already had on `users` (copied, not moved).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models import AttendeeProfile, User


def get_or_create_attendee_profile(db: Session, user: User) -> AttendeeProfile:
    profile = db.get(AttendeeProfile, user.id)
    if profile is None:
        profile = AttendeeProfile(
            user_id=user.id,
            country=user.country,
            job_title=user.job_title,
            company=user.company,
            bio=user.bio,
        )
        db.add(profile)
        db.flush()
    return profile


def profile_out(user: User, profile: AttendeeProfile) -> dict[str, Any]:
    return {
        "userId": user.id,
        "accountType": user.account_type,
        "name": user.name,
        "email": user.email,
        "emailVerified": bool(user.email_verified),
        "memberSince": user.created_at.isoformat() if user.created_at else None,
        "phone": profile.phone,
        "city": profile.city,
        "country": profile.country,
        "jobTitle": profile.job_title,
        "company": profile.company,
        "bio": profile.bio,
        "linkedinUrl": profile.linkedin_url,
        "updatedAt": profile.updated_at.isoformat() if profile.updated_at else None,
    }
