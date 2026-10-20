"""Pictures found while converting a document (phase 14).

The converters put every picture they find into an `ImageCollector`, which writes it to a work
folder, drops what is useless (tiny icons, repeated pictures, formats nobody can read) and hands
back the reference to put in the Markdown: `![alt](kimg:N)`. Block 4 stores the kept pictures
and reads them with OCR; here they are only found, measured and listed.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MIN_SIDE = 64  # px: icons, bullets and separators are not worth reading
KEPT_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}
EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}

# A picture embedded as a data URI, or a marker of where we are in the document (page or slide).
_TOKEN = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\(data:image/[\w.+-]+;base64,(?P<data>[A-Za-z0-9+/=\s]+)\)"
    r"|<!--\s*(?P<kind>page|Slide number|sheet):\s*(?P<where>[^>]*?)\s*-->"
)
_WHERE = {"page": "p. {}", "Slide number": "diapositiva {}", "sheet": "hoja {}"}


@dataclass
class PendingImage:
    n: int
    file: str  # name inside the work folder
    mime: str
    width: int
    height: int
    sha256: str
    location: str  # "p. 3", "diapositiva 2", or ""
    kind: str  # "embedded" (inside the document) or "page" (a scanned page, rendered)

    def as_dict(self) -> dict:
        return asdict(self)


class ImageCollector:
    """Writes the pictures of one document into `folder` and numbers the ones it keeps."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.images: list[PendingImage] = []
        self._by_hash: dict[str, int] = {}
        self.dropped = 0  # tiny, unreadable or repeated pictures left out

    def add(
        self, data: bytes, location: str = "", kind: str = "embedded", keep_small: bool = False
    ) -> int | None:
        """Keeps a picture and returns its number, or None if it is not worth keeping.
        The same picture twice gets the same number. `keep_small`: a picture the user added
        themselves, or a page, is never filtered by size."""
        digest = hashlib.sha256(data).hexdigest()
        if digest in self._by_hash:
            return self._by_hash[digest]
        try:
            with Image.open(io.BytesIO(data)) as picture:
                picture.load()
                width, height = picture.size
                fmt = picture.format or ""
                if fmt not in KEPT_FORMATS:  # BMP, TIFF…: re-encoded so every reader opens it
                    out = io.BytesIO()
                    picture.convert("RGBA" if "A" in picture.getbands() else "RGB").save(out, "PNG")
                    data, fmt = out.getvalue(), "PNG"
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            self.dropped += 1  # EMF, WMF, SVG…
            return None
        if not keep_small and min(width, height) < MIN_SIDE:
            self.dropped += 1
            return None
        mime = KEPT_FORMATS[fmt]
        n = len(self.images)
        name = f"img-{n}{EXTENSIONS[mime]}"
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / name).write_bytes(data)
        self.images.append(PendingImage(n, name, mime, width, height, digest, location, kind))
        self._by_hash[digest] = n
        return n


def ref(n: int) -> str:
    return f"kimg:{n}"


_REF = re.compile(r"!\[(?P<alt>[^\]]*)\]\(kimg:(?P<n>\d+)\)")


def quoted(text: str) -> str:
    """The text read from a picture, as a block quote under it."""
    lines = [stripped for stripped in (raw.strip() for raw in text.splitlines()) if stripped]
    if not lines:
        return ""
    head = f"\n\n> Texto de la imagen: {lines[0]}"
    return head + "".join(f"\n> {line}" for line in lines[1:])


def described(text: str) -> str:
    """What an AI said a picture shows, as a block quote marked as generated."""
    flat = " ".join(text.split())
    return f"\n\n> Descripción generada: {flat}" if flat else ""


def compose(
    markdown: str,
    images: list[dict],
    texts: dict[int, str],
    descriptions: dict[int, str] | None = None,
) -> tuple[str, list[dict]]:
    """Puts what the OCR read (and, if asked, what an AI says it shows) into the Markdown.
    Returns it and the pictures worth keeping.

    - A picture of a document keeps its reference and gets its text below as a quote, then its
      description.
    - A scanned page that was read *is* its text: the picture is replaced and not kept.
    - A scanned page nobody could read (a photo, a drawing) stays as a picture.
    - A reference to a picture we do not have disappears."""
    by_number = {image["n"]: image for image in images}
    kept: dict[int, dict] = {}

    def replace(match: re.Match[str]) -> str:
        number = int(match.group("n"))
        image = by_number.get(number)
        if image is None:
            return ""
        text = texts.get(number, "").strip()
        if image["kind"] == "page":
            if text:
                return text
            kept[number] = image
            return match.group(0)
        first = number not in kept
        kept[number] = image
        extra = ""
        if first:
            extra = quoted(text) + described((descriptions or {}).get(number, ""))
        return match.group(0) + extra

    return _REF.sub(replace, markdown), [kept[n] for n in sorted(kept)]


def extract_data_uris(markdown: str, collector: ImageCollector) -> str:
    """Moves the pictures embedded as `data:` URIs into the collector and leaves a reference.
    The page or slide markers it passes tell where each picture is."""
    where = ""
    pieces: list[str] = []
    last = 0
    for match in _TOKEN.finditer(markdown):
        pieces.append(markdown[last : match.start()])
        last = match.end()
        if match.group("kind"):
            where = _WHERE[match.group("kind")].format(match.group("where"))
            pieces.append(match.group(0))
            continue
        try:
            data = base64.b64decode(re.sub(r"\s+", "", match.group("data")), validate=True)
        except (binascii.Error, ValueError):
            collector.dropped += 1
            continue
        n = collector.add(data, location=where)
        if n is not None:
            pieces.append(f"![{match.group('alt')}]({ref(n)})")
    pieces.append(markdown[last:])
    return "".join(pieces)
