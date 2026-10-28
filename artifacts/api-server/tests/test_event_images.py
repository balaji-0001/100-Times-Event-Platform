"""Event pictures: organisers upload a real JPG/PNG/WebP (<= 5 MB) that is then
served publicly; anything else is refused. Files go to a temporary folder."""

import pytest
from fastapi.testclient import TestClient

from backend.dependencies import get_current_user
from backend.main import app
from backend.models import User
from backend.routes import media

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "UPLOAD_DIR", tmp_path)
    app.dependency_overrides[get_current_user] = lambda: User(id=5, name="Org", email="org@x.test", password_hash="x", role="ORGANIZER")
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_an_uploaded_picture_is_stored_and_served(client, tmp_path):
    res = client.post("/api/organizer/event-images", content=JPEG, headers={"Content-Type": "image/jpeg"})

    assert res.status_code == 201
    url = res.json()["url"]
    assert url.startswith("/api/media/event-images/") and url.endswith(".jpg")
    assert len(list(tmp_path.iterdir())) == 1
    served = client.get(url)
    assert served.status_code == 200 and served.content == JPEG and served.headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize("body, content_type, code", [
    (b"<html>not an image</html>", "image/jpeg", 415),  # bytes don't match the declared type
    (PNG, "image/jpeg", 415),
    (JPEG, "application/pdf", 415),
    (b"", "image/png", 400),
    (b"\xff\xd8\xff" + b"\x00" * (media.MAX_BYTES + 1), "image/jpeg", 413),
], ids=["html-as-jpeg", "png-as-jpeg", "pdf", "empty", "over-5mb"])
def test_anything_but_a_real_small_image_is_refused(client, tmp_path, body, content_type, code):
    res = client.post("/api/organizer/event-images", content=body, headers={"Content-Type": content_type})
    assert res.status_code == code
    assert list(tmp_path.iterdir()) == []


def test_only_organizers_can_upload_and_names_are_not_paths(client):
    app.dependency_overrides[get_current_user] = lambda: User(id=6, name="A", email="a@x.test", password_hash="x", role="USER")
    assert client.post("/api/organizer/event-images", content=PNG, headers={"Content-Type": "image/png"}).status_code == 403
    assert client.get("/api/media/event-images/..%2F..%2Fmain.py").status_code == 404
    assert client.get("/api/media/event-images/not-a-picture.txt").status_code == 404
