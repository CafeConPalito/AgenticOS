"""Proposals (phase 19, block 3; CA5, CA12, CA14): a new agent is a draft until approved; a
proposal of changes touches nothing until it is applied, whole or field by field, and a field
changed by hand since it was made is a conflict."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.migrate import upgrade_to_head
from agentic_os.db.session import create_db_engine, database_url, make_sessionmaker
from agentic_os.errors import ApiError
from agentic_os.models import (
    Agent,
    AgentChange,
    AgentStatus,
    ArchitectConversation,
    ConversationStatus,
    DocStatus,
    InboxItem,
    InboxKind,
    InboxStatus,
    KnowledgeDoc,
    KnowledgeScope,
    McpAssignment,
    McpConnection,
    ProposalKind,
    ProposalOrigin,
    ProposalStatus,
    Resolution,
    Skill,
    SkillMode,
    SkillOriginKind,
    SkillReview,
    SourceKind,
)
from agentic_os.services import proposals
from agentic_os.services.architect import sheet as S
from agentic_os.services.clis import CliInfo, ModelOption
from agentic_os.services.skills.library import SkillLibrary
from agentic_os.services.skills.store import SkillStore

CLIS = [
    CliInfo(id="claude", name="claude", installed=True, models=[ModelOption(id="sonnet")]),
    CliInfo(id="agy", name="agy", installed=True, models=[]),
]
BY_ARCHITECT = proposals.ProposedBy(ProposalOrigin.ARCHITECT)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    upgrade_to_head(engine)
    with make_sessionmaker(engine)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def lib(tmp_path: Path) -> SkillLibrary:
    return SkillLibrary(SkillStore(tmp_path / "data"))


@pytest.fixture
def world(db: Session, tmp_path: Path) -> dict:
    guide = tmp_path / "marca.md"
    guide.write_text("# Guía de marca\n", "utf-8")
    rows = {
        "seo": Skill(workspace_id=DEFAULT_WORKSPACE, name="seo-basico", description="SEO"),
        "tone": Skill(workspace_id=DEFAULT_WORKSPACE, name="tono", description="Tono"),
        "doc": KnowledgeDoc(
            workspace_id=DEFAULT_WORKSPACE,
            title="Guía de marca",
            source_kind=SourceKind.FILE,
            path=str(guide),
            status=DocStatus.READY,
        ),
        "github": McpConnection(workspace_id=DEFAULT_WORKSPACE, name="github"),
        "fetch": McpConnection(workspace_id=DEFAULT_WORKSPACE, name="fetch"),
        "qa": Agent(
            workspace_id=DEFAULT_WORKSPACE,
            name="QA",
            role="QA",
            cli="claude",
            model="sonnet",
            instructions="Comprueba los criterios.\nNo corrijas el código.",
        ),
    }
    db.add_all(rows.values())
    db.flush()
    return rows


def catalog(db: Session) -> S.Catalog:
    return S.Catalog.load(db, CLIS, DEFAULT_WORKSPACE)


def writer_sheet(db: Session, **extra) -> dict:
    values = {
        "name": "Redactor",
        "role": "Redactor del blog",
        "cli": "claude",
        "model": "sonnet",
        "instructions": "Escribe posts.",
        "skills": [{"name": "seo-basico", "mode": "always"}],
        "knowledge": ["Guía de marca"],
        "connections": ["fetch"],
        "new_skills": [{"name": "estilo-blog", "description": "Estilo", "body": "# Estilo"}],
        **extra,
    }
    result = S.apply_patch(catalog(db), {}, values)
    assert result.refused == {}
    return result.sheet


def proposal_items(db: Session) -> list[InboxItem]:
    return list(db.scalars(select(InboxItem).where(InboxItem.kind == InboxKind.PROPOSAL)))


# ---------------------------------------------------------------------------- new agents
def test_a_new_agent_is_a_draft_with_its_skills_and_connections(db, lib, world):
    proposal = proposals.create_new_agent(db, lib, catalog(db), writer_sheet(db), BY_ARCHITECT)
    assert proposal.kind == ProposalKind.NEW_AGENT
    agent = db.get(Agent, proposal.target_agent_id)
    assert (agent.status, agent.proposal_id, agent.name) == (
        AgentStatus.DRAFT,
        proposal.id,
        "Redactor",
    )
    modes = {m.skill_id: m.mode for m in db.scalars(select(SkillMode))}
    assert modes == {world["seo"].id: "always"}
    assigned = db.scalars(
        select(McpAssignment.connection_id).where(McpAssignment.agent_id == agent.id)
    )
    assert list(assigned) == [world["fetch"].id]
    [written] = proposals.new_skills(db, proposal)
    assert (written.name, written.scope, written.agent_id) == ("estilo-blog", "agent", agent.id)
    assert (written.review, written.origin) == (SkillReview.PROPOSED, SkillOriginKind.ARCHITECT)
    # documents are linked only when it is approved
    assert db.scalar(select(KnowledgeDoc).where(KnowledgeDoc.agent_id == agent.id)) is None
    [item] = proposal_items(db)
    assert (item.proposal_id, item.agent_name) == (proposal.id, "Redactor")
    assert "Arquitecto" in item.title


def test_a_sheet_with_problems_makes_no_proposal(db, lib, world):
    sheet = S.apply_patch(catalog(db), {}, {"name": "Sin rol", "cli": "claude"}).sheet
    with pytest.raises(ApiError) as caught:
        proposals.create_new_agent(db, lib, catalog(db), sheet, BY_ARCHITECT)
    assert caught.value.code == "sheet_not_ready"
    fields = {i["field"] for i in caught.value.extra["issues"]}
    assert fields == {"main.role", "main.instructions"}
    assert db.scalar(select(Agent).where(Agent.name == "Sin rol")) is None


def test_approving_activates_it_accepts_its_skills_and_links_its_documents(db, lib, world):
    proposal = proposals.create_new_agent(db, lib, catalog(db), writer_sheet(db), BY_ARCHITECT)
    applied = proposals.approve(db, lib, proposal)
    agent = db.get(Agent, proposal.target_agent_id)
    assert agent.status == AgentStatus.ACTIVE
    assert proposal.status == ProposalStatus.APPLIED and proposal.decided_at is not None
    skill = db.scalar(select(Skill).where(Skill.name == "estilo-blog"))
    assert skill.review == SkillReview.NONE and skill.current_version_id
    linked = db.scalar(select(KnowledgeDoc).where(KnowledgeDoc.agent_id == agent.id))
    assert (linked.scope, linked.path) == (KnowledgeScope.AGENT, world["doc"].path)
    assert applied.notes == []
    [item] = proposal_items(db)
    assert (item.status, item.resolution) == (InboxStatus.RESOLVED, Resolution.APPROVED)
    [change] = db.scalars(select(AgentChange))
    assert change.source == "architect" and "created" in change.fields


def test_a_skill_unticked_at_approval_is_dropped(db, lib, world):
    proposal = proposals.create_new_agent(db, lib, catalog(db), writer_sheet(db), BY_ARCHITECT)
    [written] = proposals.new_skills(db, proposal)
    proposals.approve(db, lib, proposal, skip_skills=[written.id])
    assert db.scalar(select(Skill).where(Skill.name == "estilo-blog")) is None


def test_a_document_that_is_gone_does_not_stop_the_approval(db, lib, world):
    proposal = proposals.create_new_agent(db, lib, catalog(db), writer_sheet(db), BY_ARCHITECT)
    Path(world["doc"].path).unlink()
    applied = proposals.approve(db, lib, proposal)
    assert db.get(Agent, proposal.target_agent_id).status == AgentStatus.ACTIVE
    assert len(applied.notes) == 1 and "Guía de marca" in applied.notes[0]


@pytest.mark.parametrize("archive", [False, True])
def test_rejecting_deletes_or_archives_the_draft_and_drops_its_skills(db, lib, world, archive):
    conversation = ArchitectConversation(workspace_id=DEFAULT_WORKSPACE)
    db.add(conversation)
    db.flush()
    by = proposals.ProposedBy(ProposalOrigin.ARCHITECT, conversation_id=conversation.id)
    proposal = proposals.create_new_agent(db, lib, catalog(db), writer_sheet(db), by)
    agent_id = proposal.target_agent_id
    assert conversation.status == ConversationStatus.PROPOSED and conversation.agent_id == agent_id
    proposals.reject(db, lib, proposal, archive=archive)
    agent = db.get(Agent, agent_id)
    if archive:
        assert agent.archived_at is not None and agent.status == AgentStatus.DRAFT
    else:
        assert agent is None
    assert db.scalar(select(Skill).where(Skill.name == "estilo-blog")) is None
    assert proposal.status == ProposalStatus.REJECTED
    assert conversation.status == ConversationStatus.DISCARDED
    [item] = proposal_items(db)
    assert item.resolution == Resolution.REJECTED


def test_a_decided_proposal_cannot_be_decided_again(db, lib, world):
    proposal = proposals.create_new_agent(db, lib, catalog(db), writer_sheet(db), BY_ARCHITECT)
    proposals.approve(db, lib, proposal)
    for decide in (
        lambda: proposals.approve(db, lib, proposal),
        lambda: proposals.reject(db, lib, proposal),
    ):
        with pytest.raises(ApiError) as caught:
            decide()
        assert caught.value.code == "proposal_decided"


# ------------------------------------------------------------------------ changes to an agent
def improve(db: Session, world: dict, patch: dict) -> tuple[dict, dict]:
    base = proposals.agent_sheet(db, world["qa"])
    sheet = S.copy_sheet({"agents": {"main": base}})
    result = S.apply_patch(catalog(db), sheet, patch)
    assert result.refused == {}
    return base, result.sheet


def test_only_the_fields_that_differ_are_proposed_and_nothing_changes_yet(db, lib, world):
    base, sheet = improve(
        db,
        world,
        {
            "instructions": "Comprueba los criterios.\nRechaza si falta un test.",
            "connections": ["github"],
            "model": "sonnet",
        },
    )
    proposal = proposals.create_agent_changes(
        db, lib, catalog(db), world["qa"], base, sheet, BY_ARCHITECT
    )
    assert proposal.payload["fields"] == ["instructions", "connections"]
    assert world["qa"].instructions.endswith("No corrijas el código.")
    assert db.scalar(select(McpAssignment)) is None
    [instructions, connections] = proposals.changes(db, proposal)
    assert not instructions.conflict and "+Rechaza si falta un test." in instructions.diff
    assert connections.after == [{"connection_id": world["github"].id, "name": "github"}]


def test_a_sheet_that_changes_nothing_is_not_a_proposal(db, lib, world):
    base, sheet = improve(db, world, {"model": "sonnet"})
    with pytest.raises(ApiError) as caught:
        proposals.create_agent_changes(db, lib, catalog(db), world["qa"], base, sheet, BY_ARCHITECT)
    assert caught.value.code == "no_changes"


def test_applying_some_fields_changes_only_those_and_logs_them(db, lib, world):
    base, sheet = improve(
        db,
        world,
        {
            "role": "QA estricto",
            "instructions": "Nuevo",
            "skills": [{"name": "tono", "mode": "never"}],
        },
    )
    proposal = proposals.create_agent_changes(
        db, lib, catalog(db), world["qa"], base, sheet, BY_ARCHITECT
    )
    applied = proposals.approve(db, lib, proposal, fields=["role", "skills"])
    qa = world["qa"]
    assert qa.role == "QA estricto" and qa.instructions.startswith("Comprueba")
    assert db.scalar(select(SkillMode.mode).where(SkillMode.agent_id == qa.id)) == "never"
    assert applied.fields == ["role", "skills"]
    assert proposal.status == ProposalStatus.PARTIAL and proposal.applied_fields == [
        "role",
        "skills",
    ]
    [change] = db.scalars(select(AgentChange))
    assert change.fields["role"] == {"before": "QA", "after": "QA estricto"}
    assert set(change.fields) == {"role", "skills"}


def test_a_field_changed_by_hand_since_is_a_conflict_to_settle(db, lib, world):
    base, sheet = improve(db, world, {"role": "QA estricto", "description": "Muy estricto"})
    proposal = proposals.create_agent_changes(
        db, lib, catalog(db), world["qa"], base, sheet, BY_ARCHITECT
    )
    world["qa"].role = "QA manual"  # the person edits it meanwhile
    db.flush()
    by_field = {c.field: c for c in proposals.changes(db, proposal)}
    assert by_field["role"].conflict and by_field["role"].current == "QA manual"
    assert not by_field["description"].conflict
    with pytest.raises(ApiError) as caught:
        proposals.approve(db, lib, proposal)
    assert caught.value.code == "conflicts" and caught.value.extra["fields"] == ["role"]
    proposals.approve(db, lib, proposal, choices={"role": "current"})
    assert world["qa"].role == "QA manual" and world["qa"].description == "Muy estricto"
    assert proposal.status == ProposalStatus.PARTIAL


def test_documents_and_connections_of_the_agent_follow_the_sheet(db, lib, world):
    own = KnowledgeDoc(
        workspace_id=DEFAULT_WORKSPACE,
        title="Notas del QA",
        scope=KnowledgeScope.AGENT,
        agent_id=world["qa"].id,
        source_kind=SourceKind.URL,
        url="https://example.com/notas",
    )
    db.add(own)
    db.add(McpAssignment(connection_id=world["fetch"].id, scope="agent", agent_id=world["qa"].id))
    db.flush()
    base, sheet = improve(db, world, {"knowledge": ["Guía de marca"], "connections": ["github"]})
    proposal = proposals.create_agent_changes(
        db, lib, catalog(db), world["qa"], base, sheet, BY_ARCHITECT
    )
    proposals.approve(db, lib, proposal)
    docs = db.scalars(select(KnowledgeDoc).where(KnowledgeDoc.agent_id == world["qa"].id))
    assert [d.path for d in docs] == [world["doc"].path]  # its own note went, the guide came
    assigned = db.scalars(
        select(McpAssignment.connection_id).where(McpAssignment.agent_id == world["qa"].id)
    )
    assert list(assigned) == [world["github"].id]


def test_a_hand_edit_is_logged_by_field_names(db, world):
    proposals.record_hand_edit(db, world["qa"], ["role", "instructions", "using_fallback_until"])
    db.flush()
    [change] = db.scalars(select(AgentChange))
    assert (change.source, change.fields) == ("user", {"fields": ["instructions", "role"]})


def test_editing_an_agent_from_the_api_logs_the_fields(client):
    agent = client.post("/api/agents", json={"name": "Dev"}).json()
    client.patch(f"/api/agents/{agent['id']}", json={"role": "Backend", "name": "Dev"})
    settings = client.app.state.settings
    engine = create_db_engine(database_url(settings))
    with make_sessionmaker(engine)() as session:
        [change] = session.scalars(select(AgentChange))
        assert change.fields == {"fields": ["role"]}
    engine.dispose()
