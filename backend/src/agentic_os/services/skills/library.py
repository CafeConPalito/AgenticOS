"""The skill library (phase 17, block 2): create, edit (every save is a new version), restore, move,
switch off and delete skills, and keep the vector each one is selected by (spike S4)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    RunSkill,
    Skill,
    SkillOriginKind,
    SkillReview,
    SkillVersion,
    VersionAuthor,
    VersionStatus,
)
from agentic_os.services.knowledge.docs import validate_level
from agentic_os.services.skills import history
from agentic_os.services.skills.errors import SkillError
from agentic_os.services.skills.format import (
    SKILL_MD,
    CheckedSkill,
    check_files,
    compose_skill_md,
    parse_skill_md,
)
from agentic_os.services.skills.store import Manifest, SkillStore, manifest_hashes

log = structlog.get_logger()

# texts → their vectors, or None when there is no meaning model (or it failed)
Embed = Callable[[list[str]], np.ndarray | None]


@dataclass(frozen=True)
class Author:
    kind: VersionAuthor = VersionAuthor.USER
    label: str = ""
    agent_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    task_title: str = ""


DEFAULT_AUTHOR = Author()


@dataclass
class Usage:
    loaded: int = 0
    last_used: datetime | None = None


def vector_text(name: str, description: str) -> str:
    """What a skill is selected by: its name and its description (spike S4)."""
    return f"{name.replace('-', ' ')}: {description}"


class SkillLibrary:
    def __init__(
        self,
        store: SkillStore,
        embed: Embed | None = None,
        model: Callable[[], str | None] | None = None,
    ) -> None:
        self.store = store
        self.embed = embed
        self.model = model  # id of the active meaning model, or None

    # ------------------------------------------------------------------- reading
    @staticmethod
    def get(db: Session, skill_id: str) -> Skill:
        skill = db.get(Skill, skill_id)
        if skill is None or skill.workspace_id != DEFAULT_WORKSPACE:
            raise NotFound("skill")
        return skill

    @staticmethod
    def version(db: Session, skill: Skill, version_id: str | None = None) -> SkillVersion:
        """A version of the skill (its current one by default)."""
        wanted = version_id or skill.current_version_id
        version = db.get(SkillVersion, wanted) if wanted else None
        if version is None or version.skill_id != skill.id:
            raise NotFound("skill_version")
        return version

    @staticmethod
    def versions(db: Session, skill: Skill) -> list[SkillVersion]:
        return list(
            db.scalars(
                select(SkillVersion)
                .where(SkillVersion.skill_id == skill.id)
                .order_by(SkillVersion.number.desc())
            )
        )

    def files(self, version: SkillVersion) -> dict[str, bytes]:
        return self.store.read_files(version.manifest)

    def parsed(self, version: SkillVersion):
        return parse_skill_md(self.store.read(version.manifest, SKILL_MD).decode("utf-8"))

    @staticmethod
    def usage(db: Session, skill_ids: list[str]) -> dict[str, Usage]:
        """How many runs loaded each skill, and when the last one did."""
        if not skill_ids:
            return {}
        rows = db.execute(
            select(RunSkill.skill_id, func.count(), func.max(RunSkill.loaded_at))
            .where(RunSkill.skill_id.in_(skill_ids), RunSkill.loaded_via.is_not(None))
            .group_by(RunSkill.skill_id)
        ).all()
        return {skill_id: Usage(count, last) for skill_id, count, last in rows}

    # ------------------------------------------------------------------ creating
    @staticmethod
    def _name_free(
        db: Session,
        name: str,
        scope: str,
        project_id: str | None,
        agent_id: str | None,
        exclude: str | None = None,
    ) -> None:
        query = select(Skill.id).where(
            Skill.workspace_id == DEFAULT_WORKSPACE,
            Skill.name == name,
            Skill.scope == scope,
            Skill.project_id.is_(None) if project_id is None else Skill.project_id == project_id,
            Skill.agent_id.is_(None) if agent_id is None else Skill.agent_id == agent_id,
        )
        if exclude:
            query = query.where(Skill.id != exclude)
        if db.scalar(query) is not None:
            raise SkillError(
                "name_taken",
                f"Ya hay una skill llamada «{name}» en ese nivel.",
                name=name,
            )

    @staticmethod
    def free_name(
        db: Session, name: str, scope: str, project_id: str | None, agent_id: str | None
    ) -> str:
        """`name`, or `name-2`, `name-3`… if it is taken at that level (imports)."""
        for n in range(1, 1000):
            candidate = name if n == 1 else f"{name[: 64 - len(str(n)) - 1]}-{n}"
            try:
                SkillLibrary._name_free(db, candidate, scope, project_id, agent_id)
            except SkillError:
                continue
            return candidate
        raise SkillError("name_taken", f"Ya hay demasiadas skills llamadas «{name}».", name=name)

    def create(
        self,
        db: Session,
        *,
        scope: str,
        project_id: str | None,
        agent_id: str | None,
        files: Mapping[str, bytes],
        origin: SkillOriginKind = SkillOriginKind.USER,
        author: Author = DEFAULT_AUTHOR,
        note: str = "",
        proposed: bool = False,
    ) -> tuple[Skill, SkillVersion]:
        """A new skill with its first version. `proposed`: an agent's proposal, invisible until
        the person approves it (its version is pending and the skill has no current one)."""
        validate_level(db, scope, project_id, agent_id)
        checked = check_files(dict(files))
        self._name_free(db, checked.parsed.name, scope, project_id, agent_id)
        skill = Skill(
            name=checked.parsed.name,
            scope=scope,
            project_id=project_id,
            agent_id=agent_id,
            origin=origin,
            review=SkillReview.PROPOSED if proposed else SkillReview.NONE,
            description=checked.parsed.description,
            model_invocable=checked.parsed.model_invocable,
        )
        db.add(skill)
        db.flush()
        version = self._add(
            db,
            skill,
            checked,
            author,
            note or ("Propuesta" if proposed else "Creada"),
            VersionStatus.PROPOSED if proposed else VersionStatus.ACCEPTED,
        )
        return skill, version

    def _add(
        self,
        db: Session,
        skill: Skill,
        checked: CheckedSkill,
        author: Author,
        note: str,
        status: VersionStatus,
        base: SkillVersion | None = None,
        restored_from: SkillVersion | None = None,
    ) -> SkillVersion:
        number = (
            db.scalar(
                select(func.max(SkillVersion.number)).where(SkillVersion.skill_id == skill.id)
            )
            or 0
        ) + 1
        version = SkillVersion(
            skill_id=skill.id,
            number=number,
            status=status,
            manifest=self.store.put_files(checked.files),
            description=checked.parsed.description,
            tokens=checked.tokens,
            author_kind=author.kind,
            author_label=author.label,
            agent_id=author.agent_id,
            run_id=author.run_id,
            task_id=author.task_id,
            task_title=author.task_title,
            note=note,
            base_version_id=base.id if base else None,
            restored_from_id=restored_from.id if restored_from else None,
        )
        db.add(version)
        db.flush()
        if status == VersionStatus.ACCEPTED:
            self._make_current(skill, version, checked.parsed.name)
            skill.model_invocable = checked.parsed.model_invocable
        return version

    def accept(self, db: Session, skill: Skill, version: SkillVersion) -> None:
        """A proposed version (block 5) becomes the current one."""
        checked = check_files(self.files(version))
        if checked.parsed.name != skill.name:
            self._name_free(
                db, checked.parsed.name, skill.scope, skill.project_id, skill.agent_id, skill.id
            )
        version.status = VersionStatus.ACCEPTED
        version.decided_at = utcnow()
        skill.review = SkillReview.NONE
        self._make_current(skill, version, checked.parsed.name)
        skill.model_invocable = checked.parsed.model_invocable

    def replace_files(self, version: SkillVersion, files: Mapping[str, bytes]) -> CheckedSkill:
        """Rewrites a pending proposal with the person's edits (it is still one version)."""
        checked = check_files(dict(files))
        version.manifest = self.store.put_files(checked.files)
        version.description = checked.parsed.description
        version.tokens = checked.tokens
        return checked

    def _make_current(self, skill: Skill, version: SkillVersion, name: str) -> None:
        changed = (skill.name, skill.description) != (name, version.description)
        skill.current_version_id = version.id
        skill.name = name
        skill.description = version.description
        skill.updated_at = utcnow()
        if changed or skill.vector is None:
            self.refresh_vector(skill)

    # ------------------------------------------------------------------- editing
    def add_version(
        self,
        db: Session,
        skill: Skill,
        files: Mapping[str, bytes],
        author: Author = DEFAULT_AUTHOR,
        note: str = "",
        *,
        status: VersionStatus = VersionStatus.ACCEPTED,
        restored_from: SkillVersion | None = None,
    ) -> SkillVersion:
        """A new version with `files` (the whole skill). Accepted, it becomes the current one;
        proposed, it waits for the person and changes nothing yet (CA11)."""
        checked = check_files(dict(files))
        if checked.parsed.name != skill.name:
            self._name_free(
                db, checked.parsed.name, skill.scope, skill.project_id, skill.agent_id, skill.id
            )
        current = (
            db.get(SkillVersion, skill.current_version_id) if skill.current_version_id else None
        )
        manifest = self.store.put_files(checked.files)
        if current is not None and manifest == current.manifest and restored_from is None:
            raise SkillError("no_changes", "No hay cambios respecto a la versión actual.")
        if not note:
            note = history.summary(
                history.diff(self.store, current.manifest if current else {}, manifest)
            )
        return self._add(
            db, skill, checked, author, note, status, base=current, restored_from=restored_from
        )

    def edit(
        self,
        db: Session,
        skill: Skill,
        *,
        name: str | None = None,
        description: str | None = None,
        body: str | None = None,
        changes: Mapping[str, bytes | None] | None = None,
        author: Author = DEFAULT_AUTHOR,
        note: str = "",
    ) -> SkillVersion:
        """Saves what the editor sends: the header fields and the body, and the support files
        added, replaced or removed (None). A `SKILL.md` among `changes` replaces it whole."""
        current = self.version(db, skill)
        files = self.files(current)
        changes = dict(changes or {})
        if SKILL_MD not in changes and (name, description, body) != (None, None, None):
            parsed = self.parsed(current)
            meta = dict(parsed.meta)
            if name is not None:
                meta["name"] = name.strip()
            if description is not None:
                meta["description"] = " ".join(description.split())
            files[SKILL_MD] = compose_skill_md(meta, parsed.body if body is None else body).encode(
                "utf-8"
            )
        for path, data in changes.items():
            if data is None:
                if path == SKILL_MD:
                    raise SkillError("no_skill_md", "No se puede quitar el SKILL.md.")
                files.pop(path, None)
            else:
                files[path] = data
        return self.add_version(db, skill, files, author, note)

    def restore(
        self, db: Session, skill: Skill, version: SkillVersion, author: Author = DEFAULT_AUTHOR
    ) -> SkillVersion:
        """A new version with the files of `version` (nothing is deleted from the history)."""
        if version.status != VersionStatus.ACCEPTED:
            raise ApiError(409, "not_restorable", "only an accepted version can be restored")
        return self.add_version(
            db,
            skill,
            self.files(version),
            Author(VersionAuthor.RESTORE, author.label, author.agent_id),
            f"Restaurada la versión {version.number}",
            restored_from=version,
        )

    def set_enabled(self, skill: Skill, enabled: bool) -> None:
        skill.enabled = enabled
        skill.updated_at = utcnow()

    def move(
        self, db: Session, skill: Skill, scope: str, project_id: str | None, agent_id: str | None
    ) -> None:
        validate_level(db, scope, project_id, agent_id)
        self._name_free(db, skill.name, scope, project_id, agent_id, skill.id)
        skill.scope, skill.project_id, skill.agent_id = scope, project_id, agent_id
        skill.updated_at = utcnow()

    def delete(self, db: Session, skill: Skill) -> None:
        """Deletes the skill, its versions and its usage (the UI warns first), then its files."""
        db.delete(skill)
        db.flush()
        self.collect(db)

    def collect(self, db: Session) -> int:
        """Removes the stored files no version uses any more."""
        manifests: list[Manifest] = list(db.scalars(select(SkillVersion.manifest)))
        return self.store.collect(manifest_hashes(manifests))

    # ------------------------------------------------------------------- vectors
    def refresh_vector(self, skill: Skill) -> None:
        model = self.model() if self.model else None
        if self.embed is None or model is None:
            skill.vector, skill.vector_model = None, ""
            return
        vectors = self.embed([vector_text(skill.name, skill.description)])
        if vectors is None or not len(vectors):
            skill.vector, skill.vector_model = None, ""
            return
        skill.vector = np.ascontiguousarray(vectors[0], dtype=np.float32).tobytes()
        skill.vector_model = model

    def refresh_stale(self, db: Session) -> int:
        """Gives a vector of the active model to the skills that have none or another's (after
        the model changes). Returns how many were done."""
        model = self.model() if self.model else None
        if self.embed is None or model is None:
            return 0
        stale = list(
            db.scalars(
                select(Skill).where(
                    Skill.workspace_id == DEFAULT_WORKSPACE,
                    Skill.current_version_id.is_not(None),
                    Skill.vector_model != model,
                )
            )
        )
        if not stale:
            return 0
        vectors = self.embed([vector_text(s.name, s.description) for s in stale])
        if vectors is None:
            return 0
        for skill, vector in zip(stale, vectors, strict=True):
            skill.vector = np.ascontiguousarray(vector, dtype=np.float32).tobytes()
            skill.vector_model = model
        log.info("skills_vectors_refreshed", count=len(stale), model=model)
        return len(stale)


def refresh_skill_vectors(sessions, library: SkillLibrary) -> int:
    """`library.refresh_stale` in a session of its own (at startup and after a re-index)."""
    with sessions() as db:
        done = library.refresh_stale(db)
        db.commit()
    return done
