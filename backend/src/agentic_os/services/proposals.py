"""Proposals of the Architect and of `propose_agent` (phase 19, plan §3, ADR 0026).

Nothing outside a proposal changes until the person approves it. A new agent exists from the
start as a draft (it can be seen and edited, and receives no tasks), with its skill modes, its
connections and the skills written for it (pending); the documents it should have are linked
when it is approved. A proposal of changes touches nothing until it is applied, whole or field
by field; it keeps the value every field had when it was made, so a field changed by hand since
then is a conflict the person has to settle.

The caller commits: if anything fails while applying, the session is rolled back and nothing
of the proposal stays applied.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    Agent,
    AgentChange,
    AgentStatus,
    ArchitectConversation,
    ChangeSource,
    ConversationStatus,
    InboxKind,
    KnowledgeDoc,
    KnowledgeScope,
    McpAssignment,
    McpConnection,
    Proposal,
    ProposalKind,
    ProposalOrigin,
    ProposalStatus,
    Resolution,
    Run,
    Skill,
    SkillMode,
    SkillModeValue,
    SkillOriginKind,
    SkillReview,
    SkillVersion,
    SourceKind,
    VersionAuthor,
    VersionStatus,
)
from agentic_os.services import inbox
from agentic_os.services.architect import sheet as sheets
from agentic_os.services.connections import library as connection_library
from agentic_os.services.knowledge import config as knowledge_config
from agentic_os.services.knowledge import docs as knowledge_docs
from agentic_os.services.skills.format import SKILL_MD, compose_skill_md
from agentic_os.services.skills.library import Author, SkillLibrary

ARCHITECT = "Arquitecto"
# Sheet fields that are columns of the agent (the references by their column).
COLUMNS = {
    "name": "name",
    "role": "role",
    "description": "description",
    "color": "color",
    "team": "team_id",
    "cli": "cli",
    "account": "account_id",
    "model": "model",
    "permission_mode": "permission_mode",
    "allowed_tools": "allowed_tools",
    "max_concurrency": "max_concurrency",
    "can_spawn_subagents": "can_spawn_subagents",
    "can_create_tasks": "can_create_tasks",
    "can_propose_agents": "can_propose_agents",
    "instructions": "instructions",
}
LISTS = ("skills", "knowledge", "connections")
# How each list is compared: by what identifies an item (and its mode, for skills).
LIST_KEYS = {
    "skills": lambda i: (i["skill_id"], i.get("mode", SkillModeValue.AUTO)),
    "knowledge": lambda i: i["doc_id"],
    "connections": lambda i: i["connection_id"],
}


@dataclass(frozen=True)
class ProposedBy:
    """Who proposes: the Architect in a conversation, or an agent during a run."""

    origin: ProposalOrigin
    conversation_id: str | None = None
    run: Run | None = None
    agent: Agent | None = None
    task_id: str | None = None
    reason: str = ""

    @property
    def change_source(self) -> ChangeSource:
        return (
            ChangeSource.ARCHITECT
            if self.origin == ProposalOrigin.ARCHITECT
            else ChangeSource.AGENT
        )

    def skill_author(self) -> tuple[SkillOriginKind, Author]:
        if self.origin == ProposalOrigin.ARCHITECT:
            return SkillOriginKind.ARCHITECT, Author(kind=VersionAuthor.ARCHITECT, label=ARCHITECT)
        return SkillOriginKind.AGENT, Author(
            kind=VersionAuthor.AGENT,
            label=self.agent.name if self.agent else "",
            agent_id=self.agent.id if self.agent else None,
            run_id=self.run.id if self.run else None,
            task_id=self.task_id,
        )


@dataclass
class FieldChange:
    """One field of a proposal of changes, as the review shows it."""

    field: str
    before: Any  # when the proposal was made
    after: Any  # proposed
    current: Any  # now
    conflict: bool  # changed by hand since the proposal was made
    diff: str = ""  # the instructions, as a unified diff


@dataclass
class Applied:
    proposal: Proposal
    fields: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # what could not be done, in Spanish


# ---------------------------------------------------------------------- the agent as a sheet
def agent_sheet(db: Session, agent: Agent) -> dict:
    """An existing agent in the sheet's format: the starting point to improve it and the base
    of a proposal of changes. Only what belongs to the agent itself: skills with a mode of its
    own, documents of its level and connections assigned to it."""
    values: dict[str, Any] = {key: getattr(agent, column) for key, column in COLUMNS.items()}
    values["allowed_tools"] = list(agent.allowed_tools)
    values["id"] = agent.id
    modes = db.scalars(select(SkillMode).where(SkillMode.agent_id == agent.id))
    values["skills"] = sorted(
        (
            {"skill_id": m.skill_id, "name": skill.name, "mode": m.mode}
            for m in modes
            if (skill := db.get(Skill, m.skill_id)) is not None
        ),
        key=lambda s: s["name"],
    )
    docs = db.scalars(
        select(KnowledgeDoc).where(
            KnowledgeDoc.scope == KnowledgeScope.AGENT, KnowledgeDoc.agent_id == agent.id
        )
    )
    values["knowledge"] = sorted(
        ({"doc_id": d.id, "title": d.title} for d in docs), key=lambda d: d["title"]
    )
    assigned = db.scalars(
        select(McpAssignment).where(
            McpAssignment.scope == KnowledgeScope.AGENT, McpAssignment.agent_id == agent.id
        )
    )
    values["connections"] = sorted(
        (
            {"connection_id": a.connection_id, "name": connection.name}
            for a in assigned
            if (connection := db.get(McpConnection, a.connection_id)) is not None
        ),
        key=lambda c: c["name"],
    )
    return values


def _same(key: str, a: Any, b: Any) -> bool:
    if key in LISTS:
        return {LIST_KEYS[key](i) for i in a or []} == {LIST_KEYS[key](i) for i in b or []}
    if key == "allowed_tools":
        return set(a or []) == set(b or [])
    return (a or None) == (b or None)


# --------------------------------------------------------------------------------- creating
def _not_ready(issues: Iterable[sheets.Issue]) -> None:
    errors = [i for i in issues if i.level == "error"]
    if errors:
        raise ApiError(
            422,
            "sheet_not_ready",
            "the sheet still has problems",
            extra={"issues": sheets.issues_payload(errors)},
        )


def _skill_files(item: Mapping) -> dict[str, bytes]:
    meta = {"name": item["name"], "description": item["description"]}
    return {SKILL_MD: compose_skill_md(meta, item["body"]).encode("utf-8")}


def _new_skills(
    db: Session, lib: SkillLibrary, agent: Agent, items: Iterable[Mapping], by: ProposedBy
) -> list[str]:
    origin, author = by.skill_author()
    created = []
    for item in items:
        skill, _ = lib.create(
            db,
            scope=KnowledgeScope.AGENT,
            project_id=None,
            agent_id=agent.id,
            files=_skill_files(item),
            origin=origin,
            author=author,
            note=f"Escrita para {agent.name}",
            proposed=True,
        )
        created.append(skill.id)
    return created


def _set_skill_modes(db: Session, agent_id: str, wanted: Mapping[str, str]) -> None:
    """The agent's own modes become `wanted` (skill id → mode); «auto» is the default (no row)."""
    rows = {
        m.skill_id: m for m in db.scalars(select(SkillMode).where(SkillMode.agent_id == agent_id))
    }
    for skill_id, row in rows.items():
        mode = wanted.get(skill_id, SkillModeValue.AUTO)
        if mode == SkillModeValue.AUTO:
            db.delete(row)
        else:
            row.mode = mode
    for skill_id, mode in wanted.items():
        if skill_id not in rows and mode != SkillModeValue.AUTO and db.get(Skill, skill_id):
            db.add(SkillMode(skill_id=skill_id, agent_id=agent_id, mode=mode))
    db.flush()


def _set_connections(db: Session, agent_id: str, wanted: Iterable[str]) -> None:
    """The connections assigned to the agent itself become `wanted` (ids)."""
    wanted = set(wanted)
    rows = list(
        db.scalars(
            select(McpAssignment).where(
                McpAssignment.scope == KnowledgeScope.AGENT, McpAssignment.agent_id == agent_id
            )
        )
    )
    for row in rows:
        if row.connection_id not in wanted:
            db.delete(row)
    for connection_id in wanted - {r.connection_id for r in rows}:
        connection = db.get(McpConnection, connection_id)
        if connection is not None:
            connection_library.assign(db, connection, KnowledgeScope.AGENT, agent_id=agent_id)
    db.flush()


def _link_docs(db: Session, agent: Agent, doc_ids: Iterable[str]) -> list[str]:
    """Adds to the agent's level a document with the same source as each one (by reference,
    like every document): it is processed again for this level. Returns what could not be."""
    notes: list[str] = []
    limits = knowledge_config.load(db)
    for doc_id in doc_ids:
        source = db.get(KnowledgeDoc, doc_id)
        if source is None:
            notes.append("Un documento elegido ya no existe.")
            continue
        if source.scope == KnowledgeScope.AGENT and source.agent_id == agent.id:
            continue
        try:
            if source.source_kind == SourceKind.URL and source.url:
                knowledge_docs.add_url(db, KnowledgeScope.AGENT, None, agent.id, source.url)
                continue
            [result] = knowledge_docs.add_files(
                db, KnowledgeScope.AGENT, None, agent.id, [source.path or ""], limits
            )
        except ApiError as error:
            notes.append(f"«{source.title}» no se pudo vincular: {error.message}.")
            continue
        if result.doc is None and result.error_code != "already_added":
            notes.append(f"«{source.title}» no se pudo vincular: {result.message}.")
    return notes


def _inbox_item(db: Session, proposal: Proposal, agent: Agent, title: str, by: ProposedBy) -> None:
    detail = by.reason or agent.role
    item = inbox.create(db, InboxKind.PROPOSAL, title, detail, run=by.run, proposal_id=proposal.id)
    if by.run is None:  # the Architect: the item is about the agent it designed
        item.agent_id, item.agent_name, item.agent_color = agent.id, agent.name, agent.color


def _mark_conversation(db: Session, by: ProposedBy, status: ConversationStatus, **values) -> None:
    if not by.conversation_id:
        return
    conversation = db.get(ArchitectConversation, by.conversation_id)
    if conversation is not None:
        conversation.status = status
        for key, value in values.items():
            setattr(conversation, key, value)


def create_new_agent(
    db: Session,
    lib: SkillLibrary,
    catalog: sheets.Catalog,
    sheet: Mapping,
    by: ProposedBy,
    ref: str = sheets.MAIN,
) -> Proposal:
    """A new agent as a draft, with its skill modes, connections and pending skills."""
    values = dict((sheet.get("agents") or {}).get(ref) or {})
    _not_ready(sheets.agent_issues(catalog, values, ref))
    proposal = Proposal(
        workspace_id=DEFAULT_WORKSPACE,
        kind=ProposalKind.NEW_AGENT,
        origin=by.origin,
        conversation_id=by.conversation_id,
        source_agent_id=by.agent.id if by.agent else None,
        source_run_id=by.run.id if by.run else None,
        source_task_id=by.task_id,
        reason=by.reason,
        payload={"sheet": sheets.copy_sheet(sheet), "ref": ref},
    )
    db.add(proposal)
    db.flush()
    agent = Agent(
        workspace_id=DEFAULT_WORKSPACE,
        status=AgentStatus.DRAFT,
        proposal_id=proposal.id,
        template=values.get("template"),
        **{
            column: values[key]
            for key, column in COLUMNS.items()
            if key in values and values[key] is not None
        },
    )
    agent.model = agent.model or ""
    db.add(agent)
    db.flush()
    _set_skill_modes(db, agent.id, {s["skill_id"]: s["mode"] for s in values.get("skills") or []})
    _set_connections(db, agent.id, [c["connection_id"] for c in values.get("connections") or []])
    skill_ids = _new_skills(db, lib, agent, values.get("new_skills") or [], by)
    proposal.target_agent_id = agent.id
    proposal.payload = {**proposal.payload, "agent_id": agent.id, "new_skill_ids": skill_ids}
    title = (
        f"Agente propuesto por el Arquitecto: {agent.name}"
        if by.origin == ProposalOrigin.ARCHITECT
        else f"{by.agent.name if by.agent else 'Un agente'} propone un agente: {agent.name}"
    )
    _inbox_item(db, proposal, agent, title, by)
    _mark_conversation(db, by, ConversationStatus.PROPOSED, agent_id=agent.id)
    db.flush()
    return proposal


def create_agent_changes(
    db: Session,
    lib: SkillLibrary,
    catalog: sheets.Catalog,
    agent: Agent,
    base: Mapping,
    sheet: Mapping,
    by: ProposedBy,
    ref: str = sheets.MAIN,
) -> Proposal:
    """Changes to an active agent: `base` is the agent as the conversation found it (from
    `agent_sheet`), the sheet what it should become. Only the fields that differ are proposed."""
    values = dict((sheet.get("agents") or {}).get(ref) or {})
    _not_ready(sheets.agent_issues(catalog, values, ref))
    fields = [
        key
        for key in (*COLUMNS, *LISTS)
        if key in values and not _same(key, base.get(key), values.get(key))
    ]
    if not fields and not values.get("new_skills"):
        raise ApiError(422, "no_changes", "the sheet does not change anything of the agent")
    proposal = Proposal(
        workspace_id=DEFAULT_WORKSPACE,
        kind=ProposalKind.AGENT_CHANGES,
        origin=by.origin,
        conversation_id=by.conversation_id,
        reason=by.reason,
        target_agent_id=agent.id,
        payload={
            "fields": fields,
            "base": {key: base.get(key) for key in fields},
            "after": {key: values.get(key) for key in fields},
        },
    )
    db.add(proposal)
    db.flush()
    skill_ids = _new_skills(db, lib, agent, values.get("new_skills") or [], by)
    proposal.payload = {**proposal.payload, "new_skill_ids": skill_ids}
    _inbox_item(db, proposal, agent, f"Cambios propuestos para {agent.name}", by)
    _mark_conversation(db, by, ConversationStatus.PROPOSED)
    db.flush()
    return proposal


# ---------------------------------------------------------------------------------- review
def get(db: Session, proposal_id: str) -> Proposal:
    proposal = db.get(Proposal, proposal_id)
    if proposal is None or proposal.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("proposal")
    return proposal


def _instructions_diff(before: str, after: str) -> str:
    lines = difflib.unified_diff(
        (before or "").splitlines(), (after or "").splitlines(), "antes", "después", lineterm=""
    )
    return "\n".join(lines)


def changes(db: Session, proposal: Proposal) -> list[FieldChange]:
    """The fields of a proposal of changes against the agent as it is now."""
    if proposal.kind != ProposalKind.AGENT_CHANGES:
        return []
    agent = db.get(Agent, proposal.target_agent_id) if proposal.target_agent_id else None
    if agent is None:
        raise NotFound("agent")
    now = agent_sheet(db, agent)
    result = []
    for key in proposal.payload.get("fields", []):
        before = proposal.payload["base"].get(key)
        after = proposal.payload["after"].get(key)
        result.append(
            FieldChange(
                field=key,
                before=before,
                after=after,
                current=now.get(key),
                conflict=not _same(key, before, now.get(key)),
                diff=_instructions_diff(before, after) if key == "instructions" else "",
            )
        )
    return result


def new_skills(db: Session, proposal: Proposal) -> list[Skill]:
    """The skills written for this proposal that are still waiting for it."""
    ids = proposal.payload.get("new_skill_ids") or []
    skills = [db.get(Skill, i) for i in ids]
    return [s for s in skills if s is not None and s.review == SkillReview.PROPOSED]


# -------------------------------------------------------------------------------- deciding
def _pending(proposal: Proposal) -> None:
    if proposal.status != ProposalStatus.PENDING:
        raise ApiError(409, "proposal_decided", "the proposal was already decided")


def _settle_skills(db: Session, lib: SkillLibrary, proposal: Proposal, skip: Iterable[str]) -> None:
    skip = set(skip)
    for skill in new_skills(db, proposal):
        if skill.id in skip:
            db.delete(skill)
            continue
        version = db.scalar(
            select(SkillVersion).where(
                SkillVersion.skill_id == skill.id, SkillVersion.status == VersionStatus.PROPOSED
            )
        )
        if version is not None:
            lib.accept(db, skill, version)


def _resolve(db: Session, proposal: Proposal, resolution: Resolution) -> None:
    for item in inbox.pending(db, kinds=(InboxKind.PROPOSAL,)):
        if item.proposal_id == proposal.id:
            inbox.resolve(db, item, resolution)


def _log_change(db: Session, proposal: Proposal, agent: Agent, fields: Mapping[str, Any]) -> None:
    source = (
        ChangeSource.ARCHITECT
        if proposal.origin == ProposalOrigin.ARCHITECT
        else ChangeSource.AGENT
    )
    db.add(
        AgentChange(
            agent_id=agent.id,
            source=source,
            proposal_id=proposal.id,
            conversation_id=proposal.conversation_id,
            fields=dict(fields),
        )
    )


def _apply_field(db: Session, agent: Agent, key: str, before: Any, after: Any) -> list[str]:
    if key in COLUMNS:
        value = after
        if key == "model":
            value = value or ""
        setattr(agent, COLUMNS[key], value)
        return []
    if key == "skills":
        _set_skill_modes(db, agent.id, {s["skill_id"]: s["mode"] for s in after or []})
        return []
    if key == "connections":
        _set_connections(db, agent.id, [c["connection_id"] for c in after or []])
        return []
    # knowledge: link the new ones, remove from the agent's level the ones taken away
    kept = {d["doc_id"] for d in after or []}
    for item in before or []:
        if item["doc_id"] not in kept:
            doc = db.get(KnowledgeDoc, item["doc_id"])
            if doc is not None and doc.scope == KnowledgeScope.AGENT and doc.agent_id == agent.id:
                knowledge_docs.remove(db, doc)
    added = [
        d["doc_id"] for d in after or [] if d["doc_id"] not in {i["doc_id"] for i in before or []}
    ]
    return _link_docs(db, agent, added)


def _logged(key: str, before: Any, after: Any) -> dict:
    if key == "instructions":
        return {"diff": _instructions_diff(before, after)}
    return {"before": before, "after": after}


def approve(
    db: Session,
    lib: SkillLibrary,
    proposal: Proposal,
    *,
    fields: Iterable[str] | None = None,
    choices: Mapping[str, str] | None = None,
    skip_skills: Iterable[str] = (),
) -> Applied:
    """Applies the proposal. For changes: `fields` (all by default) and, for each field in
    conflict, `choices[field]` = «proposed» or «current»."""
    _pending(proposal)
    agent = db.get(Agent, proposal.target_agent_id) if proposal.target_agent_id else None
    if agent is None:
        raise NotFound("agent")
    applied = Applied(proposal)
    if proposal.kind == ProposalKind.NEW_AGENT:
        agent.status = AgentStatus.ACTIVE
        agent.archived_at = None
        _settle_skills(db, lib, proposal, skip_skills)
        values = proposal.payload["sheet"]["agents"][proposal.payload["ref"]]
        applied.notes += _link_docs(db, agent, [d["doc_id"] for d in values.get("knowledge") or []])
        _log_change(db, proposal, agent, {"created": {"name": agent.name, "role": agent.role}})
        proposal.status = ProposalStatus.APPLIED
    elif proposal.kind == ProposalKind.AGENT_CHANGES:
        pending = changes(db, proposal)
        wanted = set(fields) if fields is not None else {c.field for c in pending}
        unknown = wanted - {c.field for c in pending}
        if unknown:
            raise ApiError(422, "unknown_field", f"not in the proposal: {sorted(unknown)}")
        choices = dict(choices or {})
        unsettled = [
            c.field
            for c in pending
            if c.field in wanted
            and c.conflict
            and choices.get(c.field) not in ("proposed", "current")
        ]
        if unsettled:
            raise ApiError(
                409,
                "conflicts",
                "some fields changed since the proposal",
                extra={"fields": unsettled},
            )
        logged = {}
        for change in pending:
            if change.field not in wanted:
                continue
            if change.conflict and choices[change.field] == "current":
                continue
            applied.notes += _apply_field(db, agent, change.field, change.current, change.after)
            applied.fields.append(change.field)
            logged[change.field] = _logged(change.field, change.current, change.after)
        _settle_skills(db, lib, proposal, skip_skills)
        if logged:
            _log_change(db, proposal, agent, logged)
        proposal.applied_fields = applied.fields
        everything = len(applied.fields) == len(pending) and not list(skip_skills)
        proposal.status = ProposalStatus.APPLIED if everything else ProposalStatus.PARTIAL
    else:
        raise ApiError(422, "unsupported_proposal", f"{proposal.kind} is not supported yet")
    proposal.decided_at = utcnow()
    _resolve(db, proposal, Resolution.APPROVED)
    by = ProposedBy(proposal.origin, proposal.conversation_id)
    _mark_conversation(db, by, ConversationStatus.APPLIED)
    db.flush()
    return applied


def reject(
    db: Session, lib: SkillLibrary, proposal: Proposal, *, archive: bool = False
) -> Proposal:
    """Discards the proposal: its new agent is deleted (or archived, out of every list), the
    skills written for it go, and a proposal of changes leaves the agent as it was."""
    _pending(proposal)
    for skill in new_skills(db, proposal):
        db.delete(skill)
    if proposal.kind == ProposalKind.NEW_AGENT and proposal.target_agent_id:
        agent = db.get(Agent, proposal.target_agent_id)
        if agent is not None and agent.status == AgentStatus.DRAFT:
            if archive:
                agent.archived_at = utcnow()
            else:
                proposal.target_agent_id = None
                db.delete(agent)
    proposal.status = ProposalStatus.REJECTED
    proposal.decided_at = utcnow()
    _resolve(db, proposal, Resolution.REJECTED)
    by = ProposedBy(proposal.origin, proposal.conversation_id)
    _mark_conversation(db, by, ConversationStatus.DISCARDED)
    db.flush()
    return proposal


def record_hand_edit(db: Session, agent: Agent, fields: Iterable[str]) -> None:
    """A change made in the editor: only which fields, for the History tab."""
    names = sorted({key for key, column in COLUMNS.items() if column in set(fields)})
    if names:
        db.add(AgentChange(agent_id=agent.id, source=ChangeSource.USER, fields={"fields": names}))
