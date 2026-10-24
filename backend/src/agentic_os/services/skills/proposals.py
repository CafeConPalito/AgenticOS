"""Skills the agents propose (phase 17, block 5): `propose_skill`, and the person's decision.

A proposal is a version waiting for the person: of a new skill (the skill itself is
`review = proposed`, invisible to every run) or a new version of an existing one (the current
version stays until approval, CA11). Approving with executable files requires that the person
opened every one of them (CA13). Rejecting keeps only a fingerprint, to tell an agent that tries
again (CA10)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    InboxItem,
    InboxKind,
    InboxStatus,
    KnowledgeScope,
    Resolution,
    Run,
    Skill,
    SkillOriginKind,
    SkillRejection,
    SkillReview,
    SkillVersion,
    Task,
    VersionAuthor,
    VersionStatus,
)
from agentic_os.services import inbox
from agentic_os.services.knowledge.docs import validate_level
from agentic_os.services.skills import config as skills_config
from agentic_os.services.skills import selection as sel
from agentic_os.services.skills.errors import SkillError
from agentic_os.services.skills.format import SKILL_MD, compose_skill_md, normalize_path
from agentic_os.services.skills.library import Author, SkillLibrary, vector_text

LEVEL_WORDS = {"general": "general", "project": "project", "proyecto": "project", "agent": "agent"}
LEVELS = {"general": "general", "project": "del proyecto", "agent": "de agente"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _date(moment) -> str:
    return moment.strftime("%d/%m/%Y") if moment else "antes"


def _author(db: Session, run: Run) -> Author:
    task = db.get(Task, run.task_id) if run.task_id else None
    return Author(
        VersionAuthor.AGENT,
        run.agent_name,
        run.agent_id,
        run.id,
        run.task_id,
        task.title if task else "",
    )


def _vector(lib: SkillLibrary, name: str, description: str) -> tuple[np.ndarray | None, str]:
    model = lib.model() if lib.model else None
    if lib.embed is None or model is None:
        return None, ""
    vectors = lib.embed([vector_text(name, description)])
    return (vectors[0] if vectors is not None and len(vectors) else None), model


def _cosine(a: np.ndarray, blob: bytes | None) -> float:
    if blob is None:
        return -1.0
    b = np.frombuffer(blob, dtype=np.float32)
    return float(a @ b / ((np.linalg.norm(a) * np.linalg.norm(b)) or 1.0))


def _similar(
    db: Session,
    lib: SkillLibrary,
    visible: Sequence[Skill],
    skill_md: bytes,
    name: str,
    description: str,
    threshold: float,
    ignore: Skill | None,
) -> str | None:
    """Why this proposal already exists (exact copy, very close to a skill or a pending
    proposal, or rejected before), or None. Without a model only exact copies count."""
    sha = _sha(skill_md)
    pending = list(
        db.scalars(
            select(Skill).where(
                Skill.workspace_id == DEFAULT_WORKSPACE, Skill.review == SkillReview.PROPOSED
            )
        )
    )
    others = [s for s in [*visible, *pending] if ignore is None or s.id != ignore.id]
    for skill in others:
        version = (
            db.get(SkillVersion, skill.current_version_id) if skill.current_version_id else None
        )
        if version is None:
            version = db.scalar(
                select(SkillVersion)
                .where(SkillVersion.skill_id == skill.id)
                .order_by(SkillVersion.number.desc())
            )
        entry = (version.manifest or {}).get(SKILL_MD) if version else None
        if entry and entry["sha256"] == sha:
            state = "pendiente de revisar" if skill.review == SkillReview.PROPOSED else "ya existe"
            return f"Ya hay una skill igual: «{skill.name}» ({state})."
    for version in db.scalars(
        select(SkillVersion).where(SkillVersion.status == VersionStatus.PROPOSED)
    ):
        entry = (version.manifest or {}).get(SKILL_MD)
        if entry and entry["sha256"] == sha:
            owner = db.get(Skill, version.skill_id)
            return f"Ya hay una propuesta igual pendiente de revisar: «{owner.name}»."
    for rejection in db.scalars(select(SkillRejection).where(SkillRejection.md_sha256 == sha)):
        return _rejected(rejection)
    vector, model = _vector(lib, name, description)
    if vector is None or threshold <= 0:
        return None
    for skill in others:
        if skill.vector_model == model and _cosine(vector, skill.vector) >= threshold:
            state = "pendiente de revisar" if skill.review == SkillReview.PROPOSED else "ya existe"
            return (
                f"Ya hay una skill muy parecida: «{skill.name}» ({state}): {skill.description} "
                "Si quieres mejorarla, propón una versión nueva con `replaces`."
            )
    for rejection in db.scalars(select(SkillRejection).where(SkillRejection.vector_model == model)):
        if _cosine(vector, rejection.vector) >= threshold:
            return _rejected(rejection)
    return None


def _rejected(rejection: SkillRejection) -> str:
    reason = f" Motivo: {rejection.reason}" if rejection.reason else ""
    return (
        f"La persona ya rechazó una skill muy parecida («{rejection.name}», el "
        f"{_date(rejection.created_at)}).{reason}"
    )


def propose(
    db: Session,
    lib: SkillLibrary,
    run: Run,
    name: str,
    description: str,
    body: str,
    files: Mapping[str, str] | None = None,
    remove: Sequence[str] = (),
    level: str = "",
    replaces: str = "",
    note: str = "",
    duplicate_threshold: float = 0.0,
) -> tuple[str, str]:
    """(the answer for the agent, a one-line detail for the run's events). Commits."""
    settings = skills_config.load(db)
    label = (name or replaces or "?").strip()[:80]
    if not settings.proposals_enabled:
        return (
            "Las propuestas de skills están desactivadas en los ajustes de la aplicación. Si lo "
            "que has aprendido es importante, cuéntalo en tu resumen.",
            "desactivadas",
        )
    made = db.scalar(
        select(func.count())
        .select_from(InboxItem)
        .where(InboxItem.kind == InboxKind.SKILL, InboxItem.run_id == run.id)
    )
    if (made or 0) >= settings.proposals_per_run:
        return (
            f"Ya has propuesto {made} skill(s) en esta ejecución (el máximo es "
            f"{settings.proposals_per_run}). Espera a que la persona la revise.",
            f"{label} → límite por ejecución",
        )
    suggested = LEVEL_WORDS.get(level.strip().lower()) if level.strip() else ""
    if suggested is None:
        return (
            "`level` debe ser «general», «project» o «agent» (o vacío: lo decide la persona).",
            f"{label} → nivel no válido",
        )
    from agentic_os.services.skills.runtime import agent_ids

    visible = sel.visible(db, run.project_id, agent_ids(db, run))
    replaced: Skill | None = None
    if replaces.strip():
        wanted = replaces.strip().split(":")[-1]
        replaced = next((s for s in visible if s.name == wanted or s.id == wanted), None)
        if replaced is None:
            names = ", ".join(s.name for s in visible[:20]) or "ninguna"
            return (
                f"En `replaces`: no tienes ninguna skill llamada «{replaces}». Las que tienes: "
                f"{names}.",
                f"{label} → skill no encontrada",
            )
    try:
        new_files, final_name, final_description = _files(
            lib, db, replaced, name, description, body, files or {}, remove
        )
    except SkillError as error:
        return f"La skill no es válida: {error.message}", f"{label} → {error.code}"

    reason = _similar(
        db,
        lib,
        visible,
        new_files[SKILL_MD],
        final_name,
        final_description,
        duplicate_threshold,
        replaced,
    )
    if reason:
        return f"{reason} No se ha creado la propuesta.", f"{final_name} → parecida"

    author = _author(db, run)
    try:
        if replaced is None:
            scope = suggested or KnowledgeScope.AGENT
            project_id = run.project_id if scope == KnowledgeScope.PROJECT else None
            agent_id = run.agent_id if scope == KnowledgeScope.AGENT else None
            if (scope == KnowledgeScope.PROJECT and not project_id) or (
                scope == KnowledgeScope.AGENT and not agent_id
            ):
                scope, project_id, agent_id = KnowledgeScope.GENERAL, None, None
            skill, version = lib.create(
                db,
                scope=scope,
                project_id=project_id,
                agent_id=agent_id,
                files=new_files,
                origin=SkillOriginKind.AGENT,
                author=author,
                note=note.strip()[:500] or "Propuesta",
                proposed=True,
            )
        else:
            skill = replaced
            version = lib.add_version(
                db, skill, new_files, author, note.strip()[:500], status=VersionStatus.PROPOSED
            )
    except SkillError as error:
        if error.code == "name_taken":
            return (
                f"{error.message} Si quieres mejorarla, propón una versión nueva con `replaces`.",
                f"{final_name} → nombre ocupado",
            )
        if error.code == "no_changes":
            return "La versión que propones es igual a la actual.", f"{final_name} → sin cambios"
        return f"La skill no es válida: {error.message}", f"{final_name} → {error.code}"
    version.suggested_scope = suggested
    executables = [p for p, e in version.manifest.items() if e.get("executable")]
    kind = "Nueva versión propuesta" if replaced else "Skill propuesta"
    detail = [final_description]
    if version.note and version.note != "Propuesta":
        detail.append(version.note)
    if executables:
        detail.append(f"Trae {len(executables)} fichero(s) ejecutable(s): revísalos antes.")
    inbox.create(
        db,
        InboxKind.SKILL,
        f"{kind}: {final_name}",
        " ".join(detail),
        run=run,
        skill_version_id=version.id,
    )
    db.commit()
    what = f"una versión nueva de «{replaced.name}»" if replaced else f"la skill «{final_name}»"
    return (
        f"Propuesta registrada: {what}. Queda pendiente de que la persona la revise; hasta "
        "entonces ningún agente la usa. Sigue con tu trabajo.",
        f"{final_name} → propuesta ({'versión nueva' if replaced else LEVELS[skill.scope]})",
    )


def _files(
    lib: SkillLibrary,
    db: Session,
    replaced: Skill | None,
    name: str,
    description: str,
    body: str,
    files: Mapping[str, str],
    remove: Sequence[str],
) -> tuple[dict[str, bytes], str, str]:
    """The whole proposed skill, its name and its description. A new version starts from the
    current one: the agent sends what changes (and `remove`), the rest stays."""
    base: dict[str, bytes] = {}
    meta: dict = {}
    if replaced is not None:
        current = lib.version(db, replaced)
        base = lib.files(current)
        parsed = lib.parsed(current)
        meta = dict(parsed.meta)
        body = body if body.strip() else parsed.body
    if name.strip():
        meta["name"] = name.strip()
    if description.strip():
        meta["description"] = " ".join(description.split())
    for path in remove:
        base.pop(normalize_path(path), None)
    for path, text in files.items():
        key = normalize_path(path)
        if key == SKILL_MD:
            raise SkillError(
                "bad_path", "El SKILL.md va en `name`, `description` y `body`, no en `files`."
            )
        base[key] = str(text).encode("utf-8")
    base[SKILL_MD] = compose_skill_md(meta, body).encode("utf-8")
    return base, str(meta.get("name", "")), str(meta.get("description", ""))


# ------------------------------------------------------------------ the decision
def _pending_items(db: Session, version: SkillVersion) -> list[InboxItem]:
    return list(
        db.scalars(
            select(InboxItem).where(
                InboxItem.skill_version_id == version.id,
                InboxItem.status == InboxStatus.PENDING,
            )
        )
    )


def proposal(db: Session, version_id: str) -> tuple[Skill, SkillVersion]:
    version = db.get(SkillVersion, version_id)
    if version is None or version.status != VersionStatus.PROPOSED:
        raise ApiError(409, "not_proposed", "the version is not a proposal waiting for review")
    return db.get(Skill, version.skill_id), version


def accept(
    db: Session,
    lib: SkillLibrary,
    version_id: str,
    *,
    opened: Sequence[str],
    name: str | None = None,
    description: str | None = None,
    body: str | None = None,
    changes: Mapping[str, bytes | None] | None = None,
    scope: str | None = None,
    project_id: str | None = None,
    agent_id: str | None = None,
) -> Skill:
    """The person approves the proposal, maybe edited and at another level (a new skill only).
    Every executable file of what the agent proposed must have been opened (CA13)."""
    skill, version = proposal(db, version_id)
    executables = sorted(p for p, e in version.manifest.items() if e.get("executable"))
    missing = [p for p in executables if p not in {normalize_path(o) for o in opened}]
    if missing:
        raise ApiError(
            409,
            "scripts_not_opened",
            "open every executable file before approving",
            extra={"files": missing},
        )
    edited = (name, description, body) != (None, None, None) or bool(changes)
    if edited:
        files = lib.files(version)
        parsed = lib.parsed(version)
        meta = dict(parsed.meta)
        if name is not None:
            meta["name"] = name.strip()
        if description is not None:
            meta["description"] = " ".join(description.split())
        files[SKILL_MD] = compose_skill_md(meta, parsed.body if body is None else body).encode()
        for path, data in (changes or {}).items():
            key = normalize_path(path)
            if data is None:
                files.pop(key, None)
            else:
                files[key] = data
        lib.replace_files(version, files)
        version.note = f"{version.note} · editada al aprobar".strip(" ·")
    if scope is not None:
        if skill.review != SkillReview.PROPOSED:
            raise ApiError(422, "level_mismatch", "a new version keeps the skill's level", "scope")
        validate_level(db, scope, project_id, agent_id)
        final = lib.parsed(version).name
        SkillLibrary.check_name(db, final, scope, project_id, agent_id, exclude=skill.id)
        skill.scope, skill.project_id, skill.agent_id = scope, project_id, agent_id
    lib.accept(db, skill, version)
    for item in _pending_items(db, version):
        inbox.resolve(db, item, Resolution.APPROVED)
    return skill


def reject(db: Session, lib: SkillLibrary, version_id: str, reason: str = "") -> None:
    """Rejected: only its fingerprint stays (an agent proposing it again is told), its files go.
    A rejected new skill is deleted; a rejected new version leaves the skill as it was."""
    skill, version = proposal(db, version_id)
    skill_md = lib.store.read(version.manifest, SKILL_MD) or b""
    parsed = lib.parsed(version)
    vector, model = _vector(lib, parsed.name, parsed.description)
    db.add(
        SkillRejection(
            name=parsed.name,
            md_sha256=_sha(skill_md),
            vector=np.ascontiguousarray(vector, dtype=np.float32).tobytes()
            if vector is not None
            else None,
            vector_model=model,
            agent_id=version.agent_id,
            reason=reason.strip()[:500],
        )
    )
    for item in _pending_items(db, version):
        inbox.resolve(db, item, Resolution.REJECTED, reason.strip() or None)
    if skill.review == SkillReview.PROPOSED:
        db.delete(skill)
    else:
        version.status = VersionStatus.REJECTED
        version.decided_at = utcnow()
        version.manifest = {}
    db.flush()
    lib.collect(db)
