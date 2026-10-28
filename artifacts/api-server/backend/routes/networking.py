from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import Connection, Event, Message, Notification, Organizer, Registration, User
from backend.schemas import (
    APIModel,
    ConnectionCreate,
    ConnectionOut,
    ConnectionUpdate,
    MessageCreate,
    MessageOut,
)

router = APIRouter(prefix="/connections", tags=["networking"])


def connection_to_out(conn: Connection, user_id: int) -> ConnectionOut:
    is_req = conn.requester_id == user_id
    peer = conn.addressee if is_req else conn.requester
    return ConnectionOut(
        id=conn.id,
        requesterId=conn.requester_id,
        addresseeId=conn.addressee_id,
        status=conn.status,
        createdAt=conn.created_at,
        peerId=peer.id if peer else (conn.addressee_id if is_req else conn.requester_id),
        peerName=peer.name if peer else "Attendee",
        peerCompany=peer.company if peer else None,
        peerJobTitle=peer.job_title if peer else None,
        peerBio=peer.bio if peer else None,
        isRequester=is_req,
    )


@router.get("", response_model=list[ConnectionOut])
def list_connections(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[ConnectionOut]:
    rows = db.scalars(
        select(Connection)
        .options(selectinload(Connection.requester), selectinload(Connection.addressee))
        .where(or_(Connection.requester_id == user.id, Connection.addressee_id == user.id))
        .order_by(Connection.created_at.desc())
    ).all()
    return [connection_to_out(row, user.id) for row in rows]


class AttendeeDirectoryOut(APIModel):
    """Public directory card for another attendee. Same camelCase fields as
    schemas.AttendeeProfileOut minus `role` (account roles are not shown to
    other users); no email either."""

    id: int
    name: str
    job_title: str | None = Field(default=None, alias="jobTitle")
    company: str | None = None
    bio: str | None = None
    country: str | None = None
    registered_event_count: int = Field(default=0, alias="registeredEventCount")
    connection_status: Literal["none", "pending_sent", "pending_received", "connected"] = Field(default="none", alias="connectionStatus")
    connection_id: int | None = Field(default=None, alias="connectionId")


def _active_registration():
    return func.lower(Registration.status) != "cancelled"


def _is_admin(user: User) -> bool:
    return (user.role or "").upper() == "ADMIN"


def _events_caller_may_see_attendees_of(user: User):
    """Events the caller is (actively) registered for, plus events whose
    organizer row the caller owns."""
    registered = select(Registration.event_id).where(Registration.user_id == user.id, _active_registration())
    organized = select(Event.id).where(Event.organizer_id.in_(select(Organizer.id).where(Organizer.user_id == user.id)))
    return registered.union(organized)


@router.get("/attendees", response_model=list[AttendeeDirectoryOut])
def list_attendees(
    q: str | None = None,
    eventId: int | None = Query(None, alias="eventId"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AttendeeDirectoryOut]:
    # Query users excluding self
    query = select(User).options(selectinload(User.registrations)).where(User.id != user.id)

    # Who may appear: attendees of events the caller attends or organizes
    # (admins see everyone). Another event's attendee list is not exposed.
    if eventId is not None:
        if not _is_admin(user):
            allowed_event_ids = set(db.scalars(_events_caller_may_see_attendees_of(user)).all())
            if eventId not in allowed_event_ids:
                raise HTTPException(status_code=403, detail="You can only see attendees of events you are registered for or organize")
        event_attendees = select(Registration.user_id).where(Registration.event_id == eventId, _active_registration())
        query = query.where(User.id.in_(event_attendees))
    elif not _is_admin(user):
        co_attendees = select(Registration.user_id).where(
            Registration.event_id.in_(_events_caller_may_see_attendees_of(user)), _active_registration()
        )
        query = query.where(User.id.in_(co_attendees))
    if q:
        search_pattern = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                User.name.ilike(search_pattern),
                User.company.ilike(search_pattern),
                User.job_title.ilike(search_pattern),
                User.bio.ilike(search_pattern),
            )
        )
    users = db.scalars(query.order_by(User.name).limit(50)).all()

    # Load existing connection mappings for the current user
    user_connections = db.scalars(
        select(Connection).where(or_(Connection.requester_id == user.id, Connection.addressee_id == user.id))
    ).all()
    conn_map: dict[int, Connection] = {}
    for c in user_connections:
        other_id = c.addressee_id if c.requester_id == user.id else c.requester_id
        conn_map[other_id] = c

    results: list[AttendeeDirectoryOut] = []
    for u in users:
        conn = conn_map.get(u.id)
        status_val = "none"
        conn_id = None
        if conn:
            conn_id = conn.id
            if conn.status == "accepted":
                status_val = "connected"
            elif conn.requester_id == user.id:
                status_val = "pending_sent"
            else:
                status_val = "pending_received"

        results.append(
            AttendeeDirectoryOut(
                id=u.id,
                name=u.name,
                jobTitle=u.job_title,
                company=u.company,
                bio=u.bio,
                country=u.country,
                registeredEventCount=len(u.registrations) if u.registrations else 0,
                connectionStatus=status_val,
                connectionId=conn_id,
            )
        )
    return results


@router.post("", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
def request_connection(payload: ConnectionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ConnectionOut:
    if payload.addressee_id == user.id:
        raise HTTPException(status_code=400, detail="You cannot connect with yourself")
    target = db.get(User, payload.addressee_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    existing = db.scalar(
        select(Connection).where(
            or_(
                (Connection.requester_id == user.id) & (Connection.addressee_id == payload.addressee_id),
                (Connection.requester_id == payload.addressee_id) & (Connection.addressee_id == user.id),
            )
        )
    )
    if existing:
        if existing.status == "declined":
            existing.status = "pending"
            existing.requester_id = user.id
            existing.addressee_id = payload.addressee_id
            db.commit()
            db.refresh(existing)
            return connection_to_out(existing, user.id)
        raise HTTPException(status_code=409, detail="A connection request already exists")
    connection = Connection(requester_id=user.id, addressee_id=payload.addressee_id, status="pending")
    db.add(connection)
    db.add(Notification(user_id=payload.addressee_id, title="New connection request", message=f"{user.name} wants to connect with you on 100 TIMES.", is_read=False))
    db.commit()
    db.refresh(connection)
    connection.requester = user
    connection.addressee = target
    return connection_to_out(connection, user.id)


@router.patch("/{connection_id}", response_model=ConnectionOut)
def update_connection(connection_id: int, payload: ConnectionUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ConnectionOut:
    connection = db.scalar(
        select(Connection)
        .options(selectinload(Connection.requester), selectinload(Connection.addressee))
        .where(Connection.id == connection_id)
    )
    if not connection or connection.addressee_id != user.id:
        raise HTTPException(status_code=404, detail="Connection request not found")
    connection.status = payload.status
    if payload.status == "accepted":
        db.add(Notification(user_id=connection.requester_id, title="Connection accepted", message=f"{user.name} accepted your connection request.", is_read=False))
    db.commit()
    db.refresh(connection)
    return connection_to_out(connection, user.id)


@router.get("/messages/{peer_id}", response_model=list[MessageOut])
def get_messages(peer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[MessageOut]:
    peer = db.get(User, peer_id)
    if not peer:
        raise HTTPException(status_code=404, detail="User not found")
    messages = db.scalars(
        select(Message)
        .options(selectinload(Message.sender))
        .where(
            or_(
                (Message.sender_id == user.id) & (Message.recipient_id == peer_id),
                (Message.sender_id == peer_id) & (Message.recipient_id == user.id),
            )
        )
        .order_by(Message.created_at.asc())
    ).all()
    # Mark unread messages received by current user as read
    unread = [m for m in messages if m.recipient_id == user.id and not m.is_read]
    if unread:
        for m in unread:
            m.is_read = True
        db.commit()
    return [
        MessageOut(
            id=m.id,
            senderId=m.sender_id,
            senderName=m.sender.name if m.sender else ("You" if m.sender_id == user.id else peer.name),
            recipientId=m.recipient_id,
            content=m.content,
            isRead=m.is_read,
            createdAt=m.created_at,
        )
        for m in messages
    ]


@router.post("/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(payload: MessageCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> MessageOut:
    if payload.recipient_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot send message to yourself")
    recipient = db.get(User, payload.recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    # Verify connection exists and is accepted
    conn = db.scalar(
        select(Connection).where(
            or_(
                (Connection.requester_id == user.id) & (Connection.addressee_id == payload.recipient_id),
                (Connection.requester_id == payload.recipient_id) & (Connection.addressee_id == user.id),
            ),
            Connection.status == "accepted",
        )
    )
    if not conn:
        raise HTTPException(status_code=403, detail="You can only message accepted connections")
    message = Message(
        sender_id=user.id,
        recipient_id=payload.recipient_id,
        content=payload.content.strip(),
        is_read=False,
    )
    db.add(message)
    db.add(
        Notification(
            user_id=payload.recipient_id,
            title="New message",
            message=f"{user.name}: {payload.content[:50]}{'...' if len(payload.content) > 50 else ''}",
            is_read=False,
        )
    )
    db.commit()
    db.refresh(message)
    return MessageOut(
        id=message.id,
        senderId=user.id,
        senderName=user.name,
        recipientId=payload.recipient_id,
        content=message.content,
        isRead=False,
        createdAt=message.created_at,
    )