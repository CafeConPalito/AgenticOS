"""A skill as a `.zip` (phase 17): its folder, named after it, as of one version."""

from __future__ import annotations

import io
import zipfile

from agentic_os.models import Skill, SkillVersion
from agentic_os.services.skills.store import SkillStore


def to_zip(store: SkillStore, skill: Skill, version: SkillVersion) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, entry in sorted(version.manifest.items()):
            archive.writestr(f"{skill.name}/{path}", store.get(entry["sha256"]))
    return buffer.getvalue()
