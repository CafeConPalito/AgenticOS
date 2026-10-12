"""The app version is declared in several manifests; they must all agree (phase 08)."""

import json
import re
import tomllib
from pathlib import Path

from agentic_os import __version__

REPO = Path(__file__).resolve().parents[2]


def declared_versions() -> dict[str, str]:
    def toml(path: str, *keys: str) -> str:
        data = tomllib.loads((REPO / path).read_text("utf-8"))
        for key in keys:
            data = data[key]
        return str(data)

    def package(path: str) -> str:
        return json.loads((REPO / path).read_text("utf-8"))["version"]

    return {
        "backend/pyproject.toml": toml("backend/pyproject.toml", "project", "version"),
        "desktop/src-tauri/Cargo.toml": toml("desktop/src-tauri/Cargo.toml", "package", "version"),
        "desktop/src-tauri/tauri.conf.json": package("desktop/src-tauri/tauri.conf.json"),
        "package.json": package("package.json"),
        "frontend/package.json": package("frontend/package.json"),
        "desktop/package.json": package("desktop/package.json"),
    }


def test_every_manifest_declares_the_backend_version():
    assert declared_versions() == dict.fromkeys(declared_versions(), __version__)


def test_the_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
