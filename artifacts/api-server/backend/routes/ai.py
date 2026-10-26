import re
from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import Connection, Registration, User
from backend.schemas import AIPeerMatch, AttendeeProfileOut

router = APIRouter(prefix="/ai", tags=["ai"])


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z]{3,}", text.lower()))


@router.get("/peer-matches", response_model=list[AIPeerMatch])
def get_peer_matches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AIPeerMatch]:
    other_users = db.scalars(
        select(User)
        .where(User.id != user.id)
    ).all()

    my_regs = set(db.scalars(select(Registration.event_id).where(Registration.user_id == user.id)).all())
    my_tokens = set()
    if user.job_title:
        my_tokens.update(tokenize(user.job_title))
    if user.company:
        my_tokens.update(tokenize(user.company))
    if user.bio:
        my_tokens.update(tokenize(user.bio))

    existing_conns = db.scalars(
        select(Connection).where(or_(Connection.requester_id == user.id, Connection.addressee_id == user.id))
    ).all()
    conn_map = {}
    for c in existing_conns:
        peer_id = c.addressee_id if c.requester_id == user.id else c.requester_id
        if c.status == "accepted":
            conn_map[peer_id] = ("connected", c.id)
        elif c.status == "pending":
            conn_map[peer_id] = ("pending_sent" if c.requester_id == user.id else "pending_received", c.id)

    matches: list[AIPeerMatch] = []
    for peer in other_users:
        peer_regs = set(db.scalars(select(Registration.event_id).where(Registration.user_id == peer.id)).all())
        shared_events = my_regs.intersection(peer_regs)

        peer_tokens = set()
        if peer.job_title:
            peer_tokens.update(tokenize(peer.job_title))
        if peer.company:
            peer_tokens.update(tokenize(peer.company))
        if peer.bio:
            peer_tokens.update(tokenize(peer.bio))

        skill_overlap = my_tokens.intersection(peer_tokens)

        score = 70
        mutual: list[str] = []
        if shared_events:
            score += 15
            plural = "s" if len(shared_events) != 1 else ""
            mutual.append(f"{len(shared_events)} Shared Event{plural}")
        if skill_overlap:
            score += min(len(skill_overlap) * 6, 15)
            mutual_terms = ", ".join(list(skill_overlap)[:2])
            mutual.append(f"Expertise in {mutual_terms}")
        if peer.country and user.country and peer.country.lower() == user.country.lower():
            score += 4
            mutual.append(peer.country)

        conn_status, conn_id = conn_map.get(peer.id, ("none", None))
        final_score = min(score, 96)
        reason = f"{final_score}% Match · Complementary focus in {peer.job_title or 'Tech'}" if peer.job_title else f"{final_score}% Match"

        matches.append(
            AIPeerMatch(
                attendee=AttendeeProfileOut(
                    id=peer.id,
                    name=peer.name,
                    email=peer.email,
                    role=peer.role,
                    job_title=peer.job_title,
                    company=peer.company,
                    bio=peer.bio,
                    country=peer.country,
                    registered_event_count=len(peer_regs),
                    connection_status=conn_status,
                    connection_id=conn_id,
                ),
                match_score=final_score,
                match_reason=reason,
                mutual_interests=mutual[:3] or ["Event Networking"],
            )
        )

    matches.sort(key=lambda x: x.match_score, reverse=True)
    return matches[:8]
