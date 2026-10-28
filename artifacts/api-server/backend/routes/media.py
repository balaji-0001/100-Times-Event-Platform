"""Event pictures organisers upload when publishing an event.

The browser sends the file itself as the request body (Content-Type
image/jpeg, image/png or image/webp) — no multipart parser needed. The bytes
must really be that kind of image (checked by its file signature), at most
5 MB. Files get a random name under api-server/uploads/event-images and are
served publicly from /api/media/event-images/<name>, the URL stored as the
event's `image`.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse

from backend.dependencies import require_roles
from backend.models import User

router = APIRouter(tags=["media"])

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "event-images"
MAX_BYTES = 5 * 1024 * 1024
_URL_PREFIX = "/api/media/event-images/"
_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")
_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _matches_signature(data: bytes, ext: str) -> bool:
    if ext == "jpg":
        return data[:3] == b"\xff\xd8\xff"
    if ext == "png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


@router.post("/organizer/event-images", status_code=status.HTTP_201_CREATED)
async def upload_event_image(request: Request, _user: User = Depends(require_roles("ORGANIZER", "ADMIN"))) -> dict[str, str]:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    ext = _TYPES.get(content_type)
    if ext is None:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG or WebP image.")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="The picture is larger than 5 MB.")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="The picture is larger than 5 MB.")
    if not data:
        raise HTTPException(status_code=400, detail="The picture is empty.")
    if not _matches_signature(bytes(data), ext):
        raise HTTPException(status_code=415, detail="That file is not a valid JPG, PNG or WebP image.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (UPLOAD_DIR / name).write_bytes(bytes(data))
    return {"url": _URL_PREFIX + name}


@router.get("/media/event-images/{name}")
def get_event_image(name: str) -> FileResponse:
    path = UPLOAD_DIR / name
    if not _NAME_RE.match(name) or not path.is_file():
        raise HTTPException(status_code=404, detail="Picture not found")
    media_type = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[name.rsplit(".", 1)[1]]
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=31536000, immutable"})
