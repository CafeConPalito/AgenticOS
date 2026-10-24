"""Content-addressed store of skill files (phase 17, ADR 0024).

Every file is kept once by its SHA-256 under `<data_dir>/skills/blobs/<aa>/<sha256>`, so ten
versions of a skill that only change `SKILL.md` share the rest. A version is a manifest
{path: {"sha256", "size", "executable"}}. Nothing here knows about the database: the caller
says which hashes are still referenced when it cleans up.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

from agentic_os.services.skills.format import is_executable, normalize_path

Manifest = dict[str, dict]


class SkillStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir) / "skills"
        self.blobs = self.root / "blobs"

    def _path(self, sha: str) -> Path:
        return self.blobs / sha[:2] / sha

    def put(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        target = self._path(sha)
        if target.exists():
            return sha
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(temp, target)  # another writer of the same content is harmless
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise
        return sha

    def get(self, sha: str) -> bytes:
        return self._path(sha).read_bytes()

    def has(self, sha: str) -> bool:
        return self._path(sha).exists()

    def put_files(self, files: Mapping[str, bytes]) -> Manifest:
        return {
            path: {
                "sha256": self.put(data),
                "size": len(data),
                "executable": is_executable(path, data),
            }
            for path, data in sorted(files.items())
        }

    def read_files(self, manifest: Manifest) -> dict[str, bytes]:
        return {path: self.get(entry["sha256"]) for path, entry in manifest.items()}

    def read(self, manifest: Manifest, path: str) -> bytes | None:
        """One file of a version, by its path in the manifest (never outside it)."""
        entry = manifest.get(normalize_path(path))
        return self.get(entry["sha256"]) if entry else None

    def materialize(self, manifest: Manifest, dest: Path) -> Path:
        """Writes the version's folder at `dest` (replacing what was there)."""
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for path, entry in manifest.items():
            target = dest.joinpath(*normalize_path(path).split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.get(entry["sha256"]))
        return dest

    def collect(self, referenced: Iterable[str]) -> int:
        """Deletes the blobs nobody references; returns the bytes freed."""
        keep = set(referenced)
        freed = 0
        if not self.blobs.exists():
            return 0
        for folder in self.blobs.iterdir():
            if not folder.is_dir():
                continue
            for blob in folder.iterdir():
                if blob.name not in keep and not blob.name.startswith(".tmp-"):
                    freed += blob.stat().st_size
                    blob.unlink(missing_ok=True)
            if not any(folder.iterdir()):
                folder.rmdir()
        return freed


def manifest_hashes(manifests: Iterable[Manifest]) -> set[str]:
    return {entry["sha256"] for manifest in manifests for entry in manifest.values()}
