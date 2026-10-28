"""The third-party license list of «Acerca de» (phase 20, block 7; CA10, CA14)."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIST = ROOT / "frontend" / "src" / "generated" / "third-party-licenses.json"
LOCKFILES = ("package-lock.json", "backend/uv.lock", "desktop/src-tauri/Cargo.lock")
# What GPL-3.0-or-later may ship next to (spike S5): permissive, weak copyleft and the GPL.
COMPATIBLE = (
    "MIT",
    "ISC",
    "BSD",
    "Apache",
    "0BSD",
    "Zlib",
    "Unlicense",
    "Unicode",
    "MPL",
    "LGPL",
    "GPL",
    "PSF",
    "Python Software Foundation",
    "CC0",
    "MIT-0",
    "MIT-CMU",
    "OFL",
    "UFL",
    "CNRI-Python",
    "BlueOak",
)


def test_the_list_is_not_behind_the_lockfiles():
    """Regenerate it with `uv run --project backend python scripts/licenses.py`."""
    saved = json.loads(LIST.read_text(encoding="utf-8"))["lockfiles"]
    current = {
        name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in LOCKFILES
    }
    assert saved == current


def test_every_package_has_a_license_compatible_with_the_gpl():
    packages = json.loads(LIST.read_text(encoding="utf-8"))["packages"]
    assert {p["ecosystem"] for p in packages} == {"npm", "python", "rust"}
    unknown = [p["name"] for p in packages if p["license"] == "UNKNOWN"]
    assert unknown == []
    odd = [
        (p["name"], p["license"])
        for p in packages
        if not any(word in p["license"] for word in COMPATIBLE)
    ]
    assert odd == []
