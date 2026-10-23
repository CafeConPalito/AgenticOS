"""Skill library (phase 17, block 2): skills, their versions and history, import and export."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    KnowledgeScope,
    Skill,
    SkillOriginKind,
    SkillReview,
    SkillVersion,
    VersionAuthor,
)
from agentic_os.schemas.skills import (
    CliImport,
    CliSkillRead,
    DiffFile,
    DiffRead,
    FileRead,
    ImportPath,
    ImportResult,
    SkillCreate,
    SkillDetail,
    SkillEdit,
    SkillRead,
    SkillUpdate,
    VersionRead,
    read_skill,
    read_version,
)
from agentic_os.services.skills import export, history, importer
from agentic_os.services.skills.errors import SkillError
from agentic_os.services.skills.format import (
    SKILL_MD,
    compose_skill_md,
    normalize_path,
    parse_skill_md,
)
from agentic_os.services.skills.library import Author, SkillLibrary

router = APIRouter(tags=["skills"])
DbSession = Annotated[Session, Depends(get_session)]
LEVEL_FIELDS = {"scope", "project_id", "agent_id"}
USER = Author(VersionAuthor.USER, "Tú")


def library(request: Request) -> SkillLibrary:
    return request.app.state.skills


def _read(db: Session, lib: SkillLibrary, skills: list[Skill]) -> list[SkillRead]:
    usage = lib.usage(db, [s.id for s in skills])
    versions = {
        v.id: v
        for v in db.scalars(
            select(SkillVersion).where(
                SkillVersion.id.in_([s.current_version_id for s in skills if s.current_version_id])
            )
        )
    }
    out = []
    for skill in skills:
        used = usage.get(skill.id)
        out.append(
            read_skill(
                skill,
                versions.get(skill.current_version_id or ""),
                used.loaded if used else 0,
                used.last_used if used else None,
            )
        )
    return out


def _detail(db: Session, lib: SkillLibrary, skill: Skill) -> SkillDetail:
    base = _read(db, lib, [skill])[0]
    # A proposed skill has no current version yet: its detail is the proposal.
    version = lib.version(
        db, skill, None if skill.current_version_id else lib.versions(db, skill)[0].id
    )
    parsed = lib.parsed(version)
    return SkillDetail(
        **base.model_dump(),
        body=parsed.body,
        header=parsed.meta,
        file_list=[
            FileRead(path=p, size=e["size"], executable=bool(e.get("executable")))
            for p, e in sorted(version.manifest.items(), key=lambda kv: (kv[0] != SKILL_MD, kv[0]))
        ],
        versions=len(lib.versions(db, skill)),
    )


# --------------------------------------------------------------------------- listing
@router.get("/skills")
def list_skills(
    request: Request,
    db: DbSession,
    scope: KnowledgeScope | None = None,
    project_id: str | None = Query(None),
    agent_id: str | None = Query(None),
    review: SkillReview | None = None,
) -> list[SkillRead]:
    """The skills of one level (or all), proposals included unless `review` says otherwise."""
    query = select(Skill).where(Skill.workspace_id == DEFAULT_WORKSPACE)
    if scope is not None:
        query = query.where(Skill.scope == scope)
    if project_id is not None:
        query = query.where(Skill.project_id == project_id)
    if agent_id is not None:
        query = query.where(Skill.agent_id == agent_id)
    if review is not None:
        query = query.where(Skill.review == review)
    skills = list(db.scalars(query.order_by(Skill.name)))
    return _read(db, library(request), skills)


@router.get("/skills/cli-scan")
def scan_cli_skills(db: DbSession) -> list[CliSkillRead]:
    """The skills the CLIs load by themselves: the person's own and the repositories'."""
    return [CliSkillRead(**vars(item)) for item in importer.scan_cli_skills(db)]


@router.get("/skills/{skill_id}")
def get_skill(skill_id: str, request: Request, db: DbSession) -> SkillDetail:
    lib = library(request)
    return _detail(db, lib, lib.get(db, skill_id))


# --------------------------------------------------------------------------- creating
@router.post("/skills", status_code=status.HTTP_201_CREATED)
def create_skill(payload: SkillCreate, request: Request, db: DbSession) -> SkillDetail:
    lib = library(request)
    meta = {"name": payload.name.strip(), "description": " ".join(payload.description.split())}
    files = {normalize_path(p): f.data() for p, f in payload.files.items()}
    files[SKILL_MD] = compose_skill_md(meta, payload.body).encode("utf-8")
    skill, _ = lib.create(
        db,
        scope=payload.scope,
        project_id=payload.project_id,
        agent_id=payload.agent_id,
        files=files,
        author=USER,
        note=payload.note,
    )
    db.commit()
    return _detail(db, lib, skill)


def _import(
    db: Session, lib: SkillLibrary, path: str, scope: str, project_id, agent_id, label: str
) -> ImportResult:
    """One import, with its own savepoint: a failure leaves the others in."""
    try:
        files = importer.read_path(Path(path))
        with db.begin_nested():
            parsed_name = parse_skill_md(files[SKILL_MD].decode("utf-8")).name
            name = lib.free_name(db, parsed_name, scope, project_id, agent_id)
            if name != parsed_name:
                files = importer.renamed(files, name)
            skill, _ = lib.create(
                db,
                scope=scope,
                project_id=project_id,
                agent_id=agent_id,
                files=files,
                origin=SkillOriginKind.IMPORT,
                author=Author(VersionAuthor.IMPORT, label),
                note=f"Importada de {path}",
            )
    except (SkillError, OSError, KeyError, UnicodeDecodeError) as exc:
        code = exc.code if isinstance(exc, SkillError) else "read_error"
        message = exc.message if isinstance(exc, SkillError) else str(exc)
        return ImportResult(path=path, error_code=code, message=message)
    except ApiError:
        raise  # a level that does not exist: the whole request is wrong
    return ImportResult(
        path=path,
        skill=_read(db, lib, [skill])[0],
        renamed_to=name if name != parsed_name else None,
    )


@router.post("/skills/import", status_code=status.HTTP_201_CREATED)
def import_skill(payload: ImportPath, request: Request, db: DbSession) -> ImportResult:
    """A folder with a SKILL.md, a .zip or a lone SKILL.md on this computer (CA2)."""
    result = _import(
        db,
        library(request),
        payload.path,
        payload.scope,
        payload.project_id,
        payload.agent_id,
        Path(payload.path).name,
    )
    db.commit()
    return result


@router.post("/skills/cli-import", status_code=status.HTTP_201_CREATED)
def import_cli_skills(payload: CliImport, request: Request, db: DbSession) -> list[ImportResult]:
    """Several skills of the CLIs, each to the level the person chose."""
    lib = library(request)
    results = [
        _import(db, lib, item.path, item.scope, item.project_id, item.agent_id, item.path)
        for item in payload.items
    ]
    db.commit()
    return results


# --------------------------------------------------------------------------- changing
@router.patch("/skills/{skill_id}")
def update_skill(
    skill_id: str, payload: SkillUpdate, request: Request, db: DbSession
) -> SkillDetail:
    lib = library(request)
    skill = lib.get(db, skill_id)
    sent = payload.model_fields_set
    if "scope" in sent:
        if payload.scope is None:
            raise ApiError(422, "level_mismatch", "the level cannot be empty", "scope")
        lib.move(db, skill, payload.scope, payload.project_id, payload.agent_id)
    elif sent & LEVEL_FIELDS:
        raise ApiError(422, "level_mismatch", "send the level (scope) with its owner", "scope")
    if payload.enabled is not None:
        lib.set_enabled(skill, payload.enabled)
    db.commit()
    return _detail(db, lib, skill)


@router.post("/skills/{skill_id}/versions", status_code=status.HTTP_201_CREATED)
def save_version(skill_id: str, payload: SkillEdit, request: Request, db: DbSession) -> SkillDetail:
    """Every save from the editor is a new version (CA12)."""
    lib = library(request)
    skill = lib.get(db, skill_id)
    if skill.review == SkillReview.PROPOSED:
        raise ApiError(409, "proposal_pending", "approve or reject the proposal first")
    lib.edit(
        db,
        skill,
        name=payload.name,
        description=payload.description,
        body=payload.body,
        changes={
            normalize_path(p): (f.data() if f is not None else None)
            for p, f in payload.files.items()
        },
        author=USER,
        note=payload.note,
    )
    db.commit()
    return _detail(db, lib, skill)


@router.post("/skills/{skill_id}/restore/{version_id}", status_code=status.HTTP_201_CREATED)
def restore_version(skill_id: str, version_id: str, request: Request, db: DbSession) -> SkillDetail:
    lib = library(request)
    skill = lib.get(db, skill_id)
    lib.restore(db, skill, lib.version(db, skill, version_id), USER)
    db.commit()
    return _detail(db, lib, skill)


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(skill_id: str, request: Request, db: DbSession) -> None:
    """Deletes it with its history and its usage figures (the UI warns first)."""
    lib = library(request)
    lib.delete(db, lib.get(db, skill_id))
    db.commit()


# --------------------------------------------------------------------------- history
@router.get("/skills/{skill_id}/versions")
def list_versions(skill_id: str, request: Request, db: DbSession) -> list[VersionRead]:
    lib = library(request)
    skill = lib.get(db, skill_id)
    return [read_version(v, skill.current_version_id) for v in lib.versions(db, skill)]


@router.get("/skills/{skill_id}/diff")
def diff_versions(
    skill_id: str,
    request: Request,
    db: DbSession,
    to: str | None = Query(None, description="a version id; the current one by default"),
    from_: str | None = Query(None, alias="from", description="by default, the one before `to`"),
) -> DiffRead:
    lib = library(request)
    skill = lib.get(db, skill_id)
    target = lib.version(db, skill, to)
    if from_:
        source = lib.version(db, skill, from_)
    else:
        source = db.get(SkillVersion, target.base_version_id) if target.base_version_id else None
        if source is None:
            source = db.scalar(
                select(SkillVersion)
                .where(SkillVersion.skill_id == skill.id, SkillVersion.number < target.number)
                .order_by(SkillVersion.number.desc())
            )
    pairs = history.diff(lib.store, source.manifest if source else {}, target.manifest)
    return DiffRead(
        from_version=source.number if source else None,
        to_version=target.number,
        files=[DiffFile(change=p.change, diff=p.diff) for p in pairs],
    )


@router.get("/skills/{skill_id}/files/{path:path}")
def read_file(
    skill_id: str,
    path: str,
    request: Request,
    db: DbSession,
    version: str | None = Query(None),
) -> Response:
    lib = library(request)
    skill = lib.get(db, skill_id)
    data = lib.store.read(lib.version(db, skill, version).manifest, path)
    if data is None:
        raise NotFound("skill_file")
    try:
        data.decode("utf-8")
        media = "text/plain; charset=utf-8"
    except UnicodeDecodeError:
        media = "application/octet-stream"
    return Response(data, media_type=media)


@router.get("/skills/{skill_id}/export")
def export_skill(skill_id: str, request: Request, db: DbSession) -> Response:
    lib = library(request)
    skill = lib.get(db, skill_id)
    data = export.to_zip(lib.store, skill, lib.version(db, skill))
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{skill.name}.zip"'},
    )
