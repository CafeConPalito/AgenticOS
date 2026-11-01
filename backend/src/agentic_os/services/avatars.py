"""Agent avatars (phase 20, ADR 0027): an owl of the gallery or a cropped photo.

The photo is cropped in the interface; only the crop reaches the backend, which checks it and
writes it again as a small WebP without metadata, named by its hash. The original is never
stored. `Agent.avatar` (and a saved template's) is null, `owl:<id>` or `photo:<hash>`.
Phase 24: `Project.avatar` is null or `photo:<hash>` (projects have no owls).
"""

import base64
import hashlib
import io
import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.errors import ApiError
from agentic_os.models import Agent, Project
from agentic_os.models.proposal import AgentTemplateRow

# The gallery: frontend/src/assets/owls/<id>.svg, drawn by scripts/owls.py (a test compares).
OWL_IDS = (
    "beanie",
    "book",
    "bow-tie",
    "crown",
    "glasses",
    "grad-cap",
    "headphones",
    "monocle",
    "plain",
    "scarf",
    "sunglasses",
    "top-hat",
    "wizard",
)

SIDE = 256  # the stored crop: SIDE x SIDE WebP
MAX_CROP_SIDE = 512  # what the interface may send (it sends SIDE)
MAX_CROP_BYTES = 300 * 1024
ACCEPTED = {"PNG", "WEBP", "JPEG"}
DIGEST = re.compile(r"^[0-9a-f]{12}$")
_PHOTO = re.compile(r"^photo:([0-9a-f]{12})$")
_VALUE = re.compile(r"^(owl:[a-z0-9-]{1,40}|photo:[0-9a-f]{12})$")
_DATA_URL = re.compile(r"^data:image/(png|webp|jpeg);base64,([A-Za-z0-9+/=]+)$")


def folder(data_dir: Path) -> Path:
    return data_dir / "avatars"


def photo_path(data_dir: Path, digest: str) -> Path:
    return folder(data_dir) / f"{digest}.webp"


def check(
    data_dir: Path, value: str | None, field: str = "avatar", owls: bool = True
) -> str | None:
    """A value the agent may take: null, an owl of the gallery or a photo that is stored.
    `owls=False` (projects): only null or a photo."""
    if value is None:
        return None
    if not _VALUE.match(value):
        raise ApiError(422, "avatar_invalid", "not an avatar value", field)
    if not owls and value.startswith("owl:"):
        raise ApiError(422, "avatar_no_owls", "only a photo can be used here", field)
    if value.startswith("owl:") and value[4:] not in OWL_IDS:
        raise ApiError(422, "avatar_unknown_owl", "no such owl in the gallery", field)
    photo = _PHOTO.match(value)
    if photo and not photo_path(data_dir, photo.group(1)).is_file():
        raise ApiError(422, "avatar_photo_missing", "the photo is not stored", field)
    return value


def save_crop(data_dir: Path, data: bytes) -> str:
    """Checks a crop and stores it as WebP without metadata; returns `photo:<hash>`."""
    if len(data) > MAX_CROP_BYTES:
        raise ApiError(413, "avatar_too_big", "the crop is too heavy", "avatar")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ACCEPTED:
                raise ApiError(415, "avatar_format", "PNG, WebP or JPEG only", "avatar")
            width, height = image.size
            if width != height or width > MAX_CROP_SIDE:
                raise ApiError(422, "avatar_not_square", "a square crop up to 512 px", "avatar")
            image.load()
            pixels = image.convert("RGBA").resize((SIDE, SIDE), Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError) as error:
        raise ApiError(415, "avatar_format", "not an image", "avatar") from error
    out = io.BytesIO()
    # A fresh image: no EXIF, ICC or any other metadata of the source travels on.
    pixels.save(out, format="WEBP", quality=85, method=6)
    encoded = out.getvalue()
    digest = hashlib.sha256(encoded).hexdigest()[:12]
    target = photo_path(data_dir, digest)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(encoded)
        tmp.replace(target)
    return f"photo:{digest}"


def to_export(data_dir: Path, value: str | None) -> str | None:
    """For `agentic-os.agent`: an owl as it is, a photo inlined as a data URL."""
    photo = _PHOTO.match(value or "")
    if not photo:
        return value
    path = photo_path(data_dir, photo.group(1))
    if not path.is_file():
        return None
    return "data:image/webp;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def from_import(data_dir: Path, value: object) -> str | None:
    """The avatar of an imported agent; anything that does not fit is left out (initials)."""
    if not isinstance(value, str):
        return None
    inlined = _DATA_URL.match(value)
    if inlined:
        try:
            return save_crop(data_dir, base64.b64decode(inlined.group(2), validate=True))
        except (ApiError, ValueError):
            return None
    if value.startswith("owl:") and value[4:] in OWL_IDS:
        return value
    photo = _PHOTO.match(value)
    if photo and photo_path(data_dir, photo.group(1)).is_file():
        return value
    return None


def remove_unused(db: Session, data_dir: Path) -> int:
    """Deletes the stored photos no agent, template nor project uses; returns how many."""
    used = {
        value[len("photo:") :]
        for model in (Agent, AgentTemplateRow, Project)
        for value in db.scalars(select(model.avatar).where(model.avatar.like("photo:%")))
    }
    removed = 0
    for path in folder(data_dir).glob("*.webp"):
        if path.stem not in used:
            path.unlink(missing_ok=True)
            removed += 1
    for leftover in folder(data_dir).glob("*.tmp"):
        leftover.unlink(missing_ok=True)
    return removed
