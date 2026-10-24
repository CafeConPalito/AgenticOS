"""Skill library (phase 17, block 2): skills, their versions and history, import and export."""

from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    Agent,
    InboxItem,
    InboxStatus,
    KnowledgeScope,
    Pipeline,
    Run,
    RunSkill,
    Skill,
    SkillMode,
    SkillModeValue,
    SkillOrigin,
    SkillOriginKind,
    SkillReview,
    SkillVersion,
    Stage,
    VersionAuthor,
    VersionStatus,
)
from agentic_os.schemas.skills import (
    ApplyUpdate,
    CardRead,
    CliImport,
    CliSkillRead,
    DiffFile,
    DiffRead,
    FileRead,
    ImportPath,
    ImportResult,
    InstallRead,
    InstallRequest,
    ListingRead,
    ModesWrite,
    OriginRead,
    PreviewRead,
    PreviewRequest,
    ProposalAccept,
    ProposalRead,
    ProposalReject,
    RegistryRead,
    RunSkillRead,
    SkillCreate,
    SkillDetail,
    SkillEdit,
    SkillModeRead,
    SkillRead,
    SkillSettingsRead,
    SkillSettingsWrite,
    SkillUpdate,
    StatsDayRead,
    StatsRowRead,
    StatsRunRead,
    StatsTableRead,
    TryCandidate,
    TryExcluded,
    TryRead,
    TryRequest,
    UpdatePreviewRead,
    VersionRead,
    read_skill,
    read_version,
)
from agentic_os.services.skills import config as skills_config
from agentic_os.services.skills import export, history, importer, selection
from agentic_os.services.skills import proposals as skill_proposals
from agentic_os.services.skills import runtime as skill_runtime
from agentic_os.services.skills import stats as skill_stats
from agentic_os.services.skills.errors import SkillError
from agentic_os.services.skills.format import (
    SKILL_MD,
    compose_skill_md,
    normalize_path,
    parse_skill_md,
)
from agentic_os.services.skills.library import Author, SkillLibrary
from agentic_os.services.skills.registries import service as registries

router = APIRouter(tags=["skills"])
# Fixed paths of two segments (/skills/<word>): registered before /skills/{skill_id}.
static = APIRouter(tags=["skills"])
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


@static.get("/skills/cli-scan")
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


# --------------------------------------------------------------------- use (block 3)
def _modes_view(
    db: Session,
    lib: SkillLibrary,
    skills: list[Skill],
    agent_id: str | None,
    stage_id: str | None,
    own: str,
) -> list[SkillModeRead]:
    """`own` is whose modes are edited here: «agent» or «stage»."""
    effective = selection.modes(db, skills, agent_id, stage_id)
    target = SkillMode.agent_id == agent_id if own == "agent" else SkillMode.stage_id == stage_id
    rows = db.scalars(
        select(SkillMode).where(SkillMode.skill_id.in_([s.id for s in skills]), target)
    )
    mine = {r.skill_id: r.mode for r in rows}
    reads = _read(db, lib, skills)
    return [
        SkillModeRead(
            skill=read,
            mode=mine.get(skill.id, SkillModeValue.AUTO),
            effective=effective[skill.id][0],
            set_by=effective[skill.id][1],
        )
        for skill, read in zip(skills, reads, strict=True)
    ]


def _save_modes(
    db: Session, modes: dict[str, str], *, agent_id: str | None = None, stage_id: str | None = None
) -> None:
    target = SkillMode.agent_id == agent_id if agent_id else SkillMode.stage_id == stage_id
    for skill_id, mode in modes.items():
        if db.get(Skill, skill_id) is None:
            raise NotFound("skill")
        row = db.scalar(select(SkillMode).where(SkillMode.skill_id == skill_id, target))
        if mode == SkillModeValue.AUTO:
            if row is not None:
                db.delete(row)
        elif row is None:
            db.add(SkillMode(skill_id=skill_id, agent_id=agent_id, stage_id=stage_id, mode=mode))
        else:
            row.mode = mode


def _agent_skills(db: Session, agent_id: str) -> list[Skill]:
    """Every skill an agent may get in some run: general, its own and the projects'."""
    return list(
        db.scalars(
            select(Skill)
            .where(
                Skill.workspace_id == DEFAULT_WORKSPACE,
                Skill.review == SkillReview.NONE,
                (Skill.scope != KnowledgeScope.AGENT) | (Skill.agent_id == agent_id),
            )
            .order_by(Skill.name)
        )
    )


@router.get("/agents/{agent_id}/skill-modes")
def get_agent_modes(agent_id: str, request: Request, db: DbSession) -> list[SkillModeRead]:
    if db.get(Agent, agent_id) is None:
        raise NotFound("agent")
    lib = library(request)
    return _modes_view(db, lib, _agent_skills(db, agent_id), agent_id, None, "agent")


@router.put("/agents/{agent_id}/skill-modes")
def put_agent_modes(
    agent_id: str, payload: ModesWrite, request: Request, db: DbSession
) -> list[SkillModeRead]:
    if db.get(Agent, agent_id) is None:
        raise NotFound("agent")
    _save_modes(db, payload.modes, agent_id=agent_id)
    db.commit()
    return get_agent_modes(agent_id, request, db)


def _stage_scope(db: Session, stage_id: str) -> tuple[Stage, Pipeline]:
    stage = db.get(Stage, stage_id)
    if stage is None:
        raise NotFound("stage")
    return stage, db.get(Pipeline, stage.pipeline_id)


@router.get("/stages/{stage_id}/skill-modes")
def get_stage_modes(stage_id: str, request: Request, db: DbSession) -> list[SkillModeRead]:
    """The skills a run of this stage can see (its agent's, its project's and the general
    ones), with what the stage says and what a run gets (the stage wins over the agent)."""
    stage, pipeline = _stage_scope(db, stage_id)
    agents = [stage.agent_id] if stage.agent_id else []
    skills = selection.visible(db, pipeline.project_id, agents)
    return _modes_view(db, library(request), skills, stage.agent_id, stage.id, "stage")


@router.put("/stages/{stage_id}/skill-modes")
def put_stage_modes(
    stage_id: str, payload: ModesWrite, request: Request, db: DbSession
) -> list[SkillModeRead]:
    _stage_scope(db, stage_id)
    _save_modes(db, payload.modes, stage_id=stage_id)
    db.commit()
    return get_stage_modes(stage_id, request, db)


@router.post("/skills/try")
def try_selection(payload: TryRequest, request: Request, db: DbSession) -> TryRead:
    """What a run would get for this text, agent and stage: the same choice and the same
    section (the «Probador» of the spec, B)."""
    lib = library(request)
    agent = db.get(Agent, payload.agent_id) if payload.agent_id else None
    stage = db.get(Stage, payload.stage_id) if payload.stage_id else None
    project_id = payload.project_id
    if stage is not None and project_id is None:
        project_id = db.get(Pipeline, stage.pipeline_id).project_id
    skills = selection.visible(db, project_id, [agent.id] if agent else [])
    ranker = request.app.state.run_manager.skill_ranker()
    settings = skills_config.load(db)
    query = selection.task_query(
        payload.text, "", stage.name if stage else "", agent.role if agent else ""
    )
    chosen = selection.select_skills(
        skills,
        selection.modes(db, skills, agent.id if agent else None, stage.id if stage else None),
        query,
        limit=settings.candidates,
        embed_query=ranker.embed_query,
        model=ranker.model,
        floor=ranker.floor,
        words_floor=settings.words_floor,
    )
    items = [
        skill_runtime.Item(o.kind, o.skill.name, o.skill.description, o.skill.current_version_id)
        for o in chosen.offered
    ]
    every = {s.id: r for s, r in zip(skills, _read(db, lib, skills), strict=True)}
    return TryRead(
        method=chosen.method,
        always=[every[o.skill.id] for o in chosen.always],
        candidates=[
            TryCandidate(skill=every[o.skill.id], rank=o.rank, score=o.score)
            for o in chosen.candidates
        ],
        excluded=[TryExcluded(skill=every[s.id], reason=why) for s, why in chosen.excluded],
        section=skill_runtime.render(db, lib, items, lambda name: f"<carpeta>/{name}"),
    )


@router.get("/runs/{run_id}/skills")
def run_skills(run_id: str, db: DbSession) -> list[RunSkillRead]:
    if db.get(Run, run_id) is None:
        raise NotFound("run")
    rows = db.execute(
        select(RunSkill, SkillVersion.number)
        .outerjoin(SkillVersion, SkillVersion.id == RunSkill.version_id)
        .where(RunSkill.run_id == run_id)
        .order_by(RunSkill.offered, RunSkill.rank, RunSkill.skill_name)
    ).all()
    return [
        RunSkillRead(
            skill_id=row.skill_id,
            skill_name=row.skill_name,
            offered=row.offered,
            rank=row.rank,
            score=row.score,
            loaded_via=row.loaded_via,
            loaded_at=row.loaded_at,
            version=number,
        )
        for row, number in rows
    ]


# ------------------------------------------------------------- proposals (block 5)
def _proposal(db: Session, lib: SkillLibrary, version: SkillVersion) -> ProposalRead:
    skill = db.get(Skill, version.skill_id)
    parsed = lib.parsed(version)
    item = db.scalar(
        select(InboxItem.id).where(
            InboxItem.skill_version_id == version.id, InboxItem.status == InboxStatus.PENDING
        )
    )
    return ProposalRead(
        skill=_read(db, lib, [skill])[0],
        version=read_version(version, skill.current_version_id),
        new_skill=skill.review == SkillReview.PROPOSED,
        suggested_scope=version.suggested_scope,
        body=parsed.body,
        header=parsed.meta,
        files=[
            FileRead(path=p, size=e["size"], executable=bool(e.get("executable")))
            for p, e in sorted(version.manifest.items(), key=lambda kv: (kv[0] != SKILL_MD, kv[0]))
        ],
        executables=sorted(p for p, e in version.manifest.items() if e.get("executable")),
        inbox_item_id=item,
    )


@router.get("/skills/proposals/pending")
def list_proposals(request: Request, db: DbSession) -> list[ProposalRead]:
    """What the agents proposed and waits for the person, newest first."""
    lib = library(request)
    versions = db.scalars(
        select(SkillVersion)
        .join(Skill, Skill.id == SkillVersion.skill_id)
        .where(
            Skill.workspace_id == DEFAULT_WORKSPACE,
            SkillVersion.status == VersionStatus.PROPOSED,
        )
        .order_by(SkillVersion.created_at.desc())
    )
    return [_proposal(db, lib, v) for v in versions]


@router.get("/skills/proposals/{version_id}")
def get_proposal(version_id: str, request: Request, db: DbSession) -> ProposalRead:
    _, version = skill_proposals.proposal(db, version_id)
    return _proposal(db, library(request), version)


@router.post("/skills/proposals/{version_id}/accept")
def accept_proposal(
    version_id: str, payload: ProposalAccept, request: Request, db: DbSession
) -> SkillDetail:
    """The person approves it, maybe edited and (a new skill) at another level. Every
    executable file must have been opened first (CA13)."""
    lib = library(request)
    skill = skill_proposals.accept(
        db,
        lib,
        version_id,
        opened=payload.opened_files,
        name=payload.name,
        description=payload.description,
        body=payload.body,
        changes={p: (f.data() if f is not None else None) for p, f in payload.files.items()},
        scope=payload.scope,
        project_id=payload.project_id,
        agent_id=payload.agent_id,
    )
    db.commit()
    return _detail(db, lib, skill)


@router.post("/skills/proposals/{version_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_proposal(
    version_id: str, payload: ProposalReject, request: Request, db: DbSession
) -> None:
    skill_proposals.reject(db, library(request), version_id, payload.reason)
    db.commit()


def _settings_read(db: Session) -> SkillSettingsRead:
    values = asdict(skills_config.load(db))
    key = values.pop("skillsmp_key")
    values["registries"] = registries.enabled(db)
    return SkillSettingsRead(**values, skillsmp_key_set=bool(key))


@router.get("/settings/skills")
def get_skill_settings(db: DbSession) -> SkillSettingsRead:
    return _settings_read(db)


@router.put("/settings/skills")
def put_skill_settings(payload: SkillSettingsWrite, db: DbSession) -> SkillSettingsRead:
    values = payload.model_dump(exclude_none=True)
    if "registries" in values:
        values["registries"] = {
            k: v for k, v in values["registries"].items() if k in registries.SWITCHABLE
        }
    skills_config.save(db, values)
    db.commit()
    return _settings_read(db)


# ------------------------------------------------------------- registries (block 6)
def explorer(request: Request) -> registries.RegistryService:
    return request.app.state.skill_registries


def _cards(db: Session, listing: registries.Listing) -> ListingRead:
    installed = {(o.source, o.ref): o.skill_id for o in db.scalars(select(SkillOrigin))}
    return ListingRead(
        cards=[
            CardRead(**asdict(c), installed_skill_id=installed.get((c.source, c.ref)))
            for c in listing.cards
        ],
        errors=listing.errors,
        attribution=listing.attribution,
    )


def _preview_read(db: Session, preview: registries.Preview) -> PreviewRead:
    fetched = preview.fetched
    parsed = parse_skill_md(fetched.files[SKILL_MD].decode("utf-8"))
    card = _cards(db, registries.Listing(cards=[fetched.card])).cards[0]
    return PreviewRead(
        id=preview.id,
        card=card,
        revision=fetched.revision,
        repo_url=fetched.repo_url,
        path=fetched.path,
        license=fetched.license,
        security=fetched.security,
        name=preview.name,
        body=parsed.body,
        header=parsed.meta,
        files=[
            FileRead(path=p, size=len(d), executable=p in preview.executables)
            for p, d in sorted(fetched.files.items(), key=lambda kv: (kv[0] != SKILL_MD, kv[0]))
        ],
        executables=preview.executables,
    )


@static.get("/skills/registries")
def list_registries(request: Request, db: DbSession) -> list[RegistryRead]:
    return [RegistryRead(**s) for s in explorer(request).status(db)]


@router.get("/skills/registries/popular")
def popular_skills(
    request: Request, db: DbSession, source: str | None = None, page: int = Query(1, ge=1)
) -> ListingRead:
    """The most used skills (the open ranking plus the sources that list without a query)."""
    return _cards(db, explorer(request).popular(db, source, page))


@router.get("/skills/registries/search")
def search_skills(
    request: Request,
    db: DbSession,
    q: str = Query(..., min_length=1, max_length=500),
    source: str | None = None,
    page: int = Query(1, ge=1),
) -> ListingRead:
    """Search in every enabled source (a GitHub address lists that repository's skills). A source
    that fails is in `errors`: the others still answer (CA18)."""
    return _cards(db, explorer(request).search(db, q, source, page))


@router.post("/skills/registries/preview")
def preview_skill(payload: PreviewRequest, request: Request, db: DbSession) -> PreviewRead:
    """Downloads the skill at a fixed revision, to review it before installing (CA16)."""
    return _preview_read(db, explorer(request).preview(db, payload.source, payload.ref))


@router.get("/skills/registries/previews/{preview_id}/files/{path:path}")
def preview_file(preview_id: str, path: str, request: Request) -> Response:
    preview = explorer(request).load(preview_id)
    data = preview.fetched.files.get(normalize_path(path))
    if data is None:
        raise NotFound("skill_file")
    try:
        data.decode("utf-8")
        media = "text/plain; charset=utf-8"
    except UnicodeDecodeError:
        media = "application/octet-stream"
    return Response(data, media_type=media)


@router.post("/skills/registries/install", status_code=status.HTTP_201_CREATED)
def install_skill(payload: InstallRequest, request: Request, db: DbSession) -> InstallRead:
    """Installs exactly what was previewed, at the chosen level. Every executable file must have
    been opened first."""
    lib = library(request)
    skill, renamed_to = explorer(request).install(
        db,
        payload.preview_id,
        payload.scope,
        payload.project_id,
        payload.agent_id,
        payload.opened_files,
    )
    db.commit()
    return InstallRead(skill=_detail(db, lib, skill), renamed_to=renamed_to)


def _origin_read(origin: SkillOrigin) -> OriginRead:
    return OriginRead(
        source=origin.source,
        title=registries.SOURCES[origin.source].title,
        ref=origin.ref,
        repo_url=origin.repo_url,
        revision=origin.revision,
        latest_revision=origin.latest_revision,
        update_available=bool(origin.latest_revision and origin.latest_revision != origin.revision),
        license=origin.license,
        security=origin.security,
        checked_at=origin.checked_at,
    )


@router.get("/skills/{skill_id}/origin")
def skill_origin(skill_id: str, request: Request, db: DbSession) -> OriginRead | None:
    library(request).get(db, skill_id)
    origin = db.get(SkillOrigin, skill_id)
    return _origin_read(origin) if origin else None


@router.post("/skills/updates/check")
def check_updates(request: Request, db: DbSession) -> dict[str, str]:
    """Asks the sources for news of what was installed; returns the skills whose source failed."""
    failed = explorer(request).check_updates(db)
    db.commit()
    return failed


@router.post("/skills/{skill_id}/update-preview")
def update_preview(skill_id: str, request: Request, db: DbSession) -> UpdatePreviewRead:
    """The source's current version and what it changes against the skill now (CA17)."""
    skill = library(request).get(db, skill_id)
    preview, pairs = explorer(request).update_preview(db, skill)
    return UpdatePreviewRead(
        preview=_preview_read(db, preview),
        files=[DiffFile(change=p.change, diff=p.diff) for p in pairs],
    )


@router.post("/skills/{skill_id}/update")
def apply_update(
    skill_id: str, payload: ApplyUpdate, request: Request, db: DbSession
) -> SkillDetail:
    lib = library(request)
    skill = lib.get(db, skill_id)
    explorer(request).apply_update(db, skill, payload.preview_id, payload.opened_files)
    db.commit()
    return _detail(db, lib, skill)


# ------------------------------------------------------------ usage statistics (block 10)
def _filters(
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    agent_id: str | None = None,
    team_id: str | None = None,
    project_id: str | None = None,
    pipeline_id: str | None = None,
    stage_id: str | None = None,
    cli: str | None = None,
    account_id: str | None = None,
    model: str | None = None,
    scope: KnowledgeScope | None = None,
    origin: SkillOriginKind | None = None,
    via: Literal["context", "tool", "native"] | None = None,
    unused: Literal["never_loaded", "never_offered"] | None = None,
    skill_id: str | None = None,
) -> skill_stats.Filters:
    return skill_stats.Filters(
        from_,
        to,
        agent_id,
        team_id,
        project_id,
        pipeline_id,
        stage_id,
        cli,
        account_id,
        model,
        scope,
        origin,
        via,
        unused,
        skill_id,
    )


StatsFilters = Annotated[skill_stats.Filters, Depends(_filters)]
GroupBy = Literal["agent", "team", "project", "pipeline", "stage", "cli", "account", "model"]


@static.get("/skills/stats")
def stats_table(
    db: DbSession,
    filters: StatsFilters,
    group_by: GroupBy | None = None,
    sort: str = "loaded",
    desc: bool = True,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> StatsTableRead:
    """The figures of every skill (or of each skill per group), filtered and sorted (spec E)."""
    result = skill_stats.table(db, filters, group_by, sort, desc, limit, offset)
    return StatsTableRead(rows=[StatsRowRead(**asdict(r)) for r in result.rows], total=result.total)


@router.get("/skills/stats/daily")
def stats_daily(
    db: DbSession, filters: StatsFilters, skill_ids: str = Query("", max_length=4000)
) -> list[StatsDayRead]:
    ids = [s for s in skill_ids.split(",") if s]
    return [StatsDayRead(**d) for d in skill_stats.daily(db, filters, ids)]


@router.get("/skills/stats/runs")
def stats_runs(
    db: DbSession,
    filters: StatsFilters,
    group_by: GroupBy | None = None,
    group_key: str | None = None,
) -> list[StatsRunRead]:
    """The runs behind a figure (spec E: «clic en una cifra»), newest first."""
    return [
        StatsRunRead(
            run_id=run.id,
            started_at=run.started_at or run.created_at,
            skill_id=row.skill_id,
            skill_name=row.skill_name,
            version=number,
            offered=row.offered,
            loaded_via=row.loaded_via,
            agent_name=run.agent_name,
            project_name=run.project_name,
            stage_name=row.stage_name,
            pipeline_name=row.pipeline_name,
            cli=run.cli,
            model=run.model,
            account_label=run.account_label,
            status=run.status,
            verdict=run.verdict,
            cost_usd=run.cost_usd,
            task_id=run.task_id,
        )
        for row, run, number in skill_stats.runs(db, filters, group_by, group_key)
    ]


@static.get("/skills/stats.csv")
def stats_csv(db: DbSession, filters: StatsFilters, group_by: GroupBy | None = None) -> Response:
    result = skill_stats.table(db, filters, group_by, limit=100_000)
    return Response(
        skill_stats.to_csv(result.rows, grouped=group_by is not None),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="uso-de-skills.csv"'},
    )
