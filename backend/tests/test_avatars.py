"""Agent avatars (phase 20, block 5; CA3, CA4, CA5): owls of the gallery and cropped photos
stored again without metadata, exported inside the agent file and imported elsewhere."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.errors import ApiError
from agentic_os.services import avatars
from agentic_os.services.architect.sheet import Refused, check_field

OWLS_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "assets" / "owls"


def picture(
    side: int = 256,
    fmt: str = "PNG",
    height: int | None = None,
    exif: bool = False,
    color: tuple[int, int, int] = (200, 80, 40),
):
    image = Image.new("RGB", (side, height or side), color)
    out = io.BytesIO()
    if exif:
        data = Image.Exif()
        data[0x010F] = "SecretCamera"  # Make
        data[0x9003] = "2026:10:28 09:00:00"  # DateTimeOriginal
        image.save(out, format=fmt, exif=data)
    else:
        image.save(out, format=fmt)
    return out.getvalue()


def new_agent(client: TestClient, **fields) -> dict:
    body = {"name": "Dev", "role": "Desarrollador", "instructions": "Programa.", **fields}
    response = client.post("/api/agents", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def upload(client: TestClient, agent_id: str, data: bytes, kind: str = "image/png"):
    return client.put(
        f"/api/agents/{agent_id}/avatar", content=data, headers={"Content-Type": kind}
    )


# ------------------------------------------------------------------------------- the crop
def test_a_crop_is_stored_again_as_small_webp_without_metadata(tmp_path: Path):
    value = avatars.save_crop(tmp_path, picture(400, "JPEG", exif=True))
    digest = value.removeprefix("photo:")
    stored = avatars.photo_path(tmp_path, digest)
    with Image.open(stored) as image:
        assert image.format == "WEBP"
        assert image.size == (avatars.SIDE, avatars.SIDE)
        assert "exif" not in image.info
    assert b"SecretCamera" not in stored.read_bytes()
    # Only the stored crop: no temporary file, nothing else.
    assert [p.name for p in avatars.folder(tmp_path).iterdir()] == [f"{digest}.webp"]
    # The same picture twice is the same file.
    assert avatars.save_crop(tmp_path, picture(400, "JPEG", exif=True)) == value


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [
        (picture(256, height=200), 422, "avatar_not_square"),
        (picture(600), 422, "avatar_not_square"),
        (b"not an image at all", 415, "avatar_format"),
        (picture(64, "GIF"), 415, "avatar_format"),
        (b"\x89PNG" + b"0" * (avatars.MAX_CROP_BYTES + 1), 413, "avatar_too_big"),
    ],
    # Short ids: the bytes would make a test name too long for an environment variable.
    ids=["not-square", "too-large", "not-an-image", "gif", "too-heavy"],
)
def test_refuses_what_is_not_a_small_square_crop(tmp_path: Path, data, status, code):
    with pytest.raises(ApiError) as caught:
        avatars.save_crop(tmp_path, data)
    assert (caught.value.status, caught.value.code) == (status, code)
    assert not avatars.folder(tmp_path).exists() or not any(avatars.folder(tmp_path).iterdir())


def test_the_owl_ids_match_the_drawn_gallery():
    assert sorted(p.stem for p in OWLS_DIR.glob("*.svg")) == sorted(avatars.OWL_IDS)


# ------------------------------------------------------------------------------- the API
def test_upload_a_photo_serve_it_and_go_back_to_initials(client: TestClient):
    agent = new_agent(client)
    assert agent["avatar"] is None
    response = upload(client, agent["id"], picture())
    assert response.status_code == 200, response.text
    value = response.json()["avatar"]
    assert value.startswith("photo:")

    served = client.get(f"/api/avatars/{value.removeprefix('photo:')}.webp")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"
    assert "immutable" in served.headers["cache-control"]
    assert client.get("/api/avatars/000000000000.webp").status_code == 404
    assert client.get("/api/avatars/..%2Fsecret.webp").status_code == 404

    cleared = client.patch(f"/api/agents/{agent['id']}", json={"avatar": None})
    assert cleared.json()["avatar"] is None


def test_refused_upload_says_why_and_keeps_the_avatar(client: TestClient):
    agent = new_agent(client, avatar="owl:glasses")
    response = upload(client, agent["id"], picture(256, height=100))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "avatar_not_square"
    assert client.get(f"/api/agents/{agent['id']}").json()["avatar"] == "owl:glasses"


def test_owls_and_photos_are_checked_on_create_and_update(client: TestClient):
    agent = new_agent(client, avatar="owl:wizard")
    assert agent["avatar"] == "owl:wizard"
    for bad, code in [
        ("owl:dragon", "avatar_unknown_owl"),
        ("photo:aaaaaaaaaaaa", "avatar_photo_missing"),
    ]:
        response = client.patch(f"/api/agents/{agent['id']}", json={"avatar": bad})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == code
    assert (
        client.patch(f"/api/agents/{agent['id']}", json={"avatar": "selfie.png"}).status_code == 422
    )
    other = client.post("/api/agents", json={"name": "X", "avatar": "owl:dragon"})
    assert other.status_code == 422


def test_duplicate_and_template_keep_the_avatar(client: TestClient):
    agent = new_agent(client)
    photo = upload(client, agent["id"], picture()).json()["avatar"]
    copy = client.post(f"/api/agents/{agent['id']}/duplicate", json={"name": "Dev 2"}).json()
    assert copy["avatar"] == photo
    template = client.post(f"/api/agents/{agent['id']}/save-as-template", json={}).json()
    assert template["avatar"] == photo
    from_template = client.post(
        "/api/agents", json={"template": template["id"], "name": "Dev 3"}
    ).json()
    assert from_template["avatar"] == photo


# ------------------------------------------------------------------ export and import (CA5)
@pytest.mark.parametrize("kind", ["owl", "photo"])
def test_export_and_import_keep_the_avatar(client: TestClient, tmp_path: Path, kind: str):
    agent = new_agent(client, avatar="owl:headphones" if kind == "owl" else None)
    if kind == "photo":
        upload(client, agent["id"], picture())
    exported = client.get(f"/api/agents/{agent['id']}/export").json()
    avatar = exported["agent"]["avatar"]
    if kind == "photo":
        assert avatar.startswith("data:image/webp;base64,")
    else:
        assert avatar == "owl:headphones"

    clean = Settings(_env_file=None, data_dir=tmp_path / "clean", check_sessions_at_startup=False)
    with TestClient(create_app(clean)) as other:
        imported = other.post("/api/agents/import", json={"payload": exported}).json()["agent"]
        if kind == "photo":
            assert imported["avatar"].startswith("photo:")
            digest = imported["avatar"].removeprefix("photo:")
            assert other.get(f"/api/avatars/{digest}.webp").status_code == 200
        else:
            assert imported["avatar"] == "owl:headphones"


def test_an_old_file_or_a_bad_avatar_imports_with_initials(client: TestClient):
    exported = client.get(f"/api/agents/{new_agent(client)['id']}/export").json()
    for avatar in (None, "owl:dragon", "data:image/png;base64,bm90IGFuIGltYWdl", 7):
        payload = {**exported, "agent": {**exported["agent"], "avatar": avatar}}
        if avatar is None:
            payload["agent"].pop("avatar")
        imported = client.post("/api/agents/import", json={"payload": payload})
        assert imported.status_code == 201, imported.text
        assert imported.json()["agent"]["avatar"] is None


# ------------------------------------------------------------------------------- cleanup
def test_unused_photos_are_removed(client: TestClient):
    agent = new_agent(client)
    first = upload(client, agent["id"], picture()).json()["avatar"]
    second = upload(client, agent["id"], picture(128, color=(30, 90, 200))).json()["avatar"]
    assert first != second
    data_dir = Path(client.app.state.settings.data_dir)
    with client.app.state.sessionmaker() as db:
        assert avatars.remove_unused(db, data_dir) == 1
    assert not avatars.photo_path(data_dir, first.removeprefix("photo:")).exists()
    assert avatars.photo_path(data_dir, second.removeprefix("photo:")).exists()


# ------------------------------------------------------------------------------ Architect
def test_the_architect_may_only_pick_an_owl():
    assert check_field(None, {}, "avatar", "owl:crown") == "owl:crown"
    assert check_field(None, {}, "avatar", "crown") == "owl:crown"
    assert check_field(None, {}, "avatar", None) is None
    for bad in ("owl:dragon", "photo:aaaaaaaaaaaa", 3):
        with pytest.raises(Refused):
            check_field(None, {}, "avatar", bad)
