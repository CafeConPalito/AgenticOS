"""Migration 0021 (phase 19, block 1): conversations with the Architect, proposals and the drafts
they create, the history of an agent's configuration, the person's templates, and the kinds
«architect» (runs, skills) and «proposal» (Inbox)."""

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-25 21:00:00.000000"


def _engine(settings: Settings, revision: str):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, revision)
    return engine, config


def _agent(agent_id: str) -> str:
    return (
        "INSERT INTO agents (id, workspace_id, created_at, updated_at, name, role, description,"
        " color, cli, model, instructions, permission_mode, allowed_tools, max_concurrency,"
        " can_spawn_subagents, can_create_tasks, status, fallback_model) VALUES"
        f" ('{agent_id}', 'default', '{NOW}', '{NOW}', 'Dev', '', '', '#fff', 'claude', '', '',"
        " 'ask', '[]', 1, 0, 0, 'active', '')"
    )


def _conversation(conversation_id: str, mode: str = "agent", status: str = "open") -> str:
    return (
        "INSERT INTO architect_conversations (id, workspace_id, created_at, updated_at, mode,"
        " title, status, model, sheet, locked_fields) VALUES"
        f" ('{conversation_id}', 'default', '{NOW}', '{NOW}', '{mode}', '', '{status}', '',"
        " '{}', '[]')"
    )


def _proposal(proposal_id: str, kind: str = "new_agent", origin: str = "architect", **refs) -> str:
    columns = ", ".join(refs)
    values = ", ".join(f"'{v}'" for v in refs.values())
    extra_columns = f", {columns}" if refs else ""
    extra_values = f", {values}" if refs else ""
    return (
        "INSERT INTO proposals (id, workspace_id, created_at, updated_at, kind, origin, status,"
        f" reason, payload, applied_fields{extra_columns}) VALUES ('{proposal_id}', 'default',"
        f" '{NOW}', '{NOW}', '{kind}', '{origin}', 'pending', '', '{{}}', '[]'{extra_values})"
    )


def _skill(skill_id: str, origin: str) -> str:
    return (
        "INSERT INTO skills (id, workspace_id, created_at, updated_at, name, scope, project_id,"
        " agent_id, enabled, review, origin, description, model_invocable, vector_model) VALUES"
        f" ('{skill_id}', 'default', '{NOW}', '{NOW}', '{skill_id}', 'general', NULL, NULL,"
        f" 1, 'proposed', '{origin}', 'd', 1, '')"
    )


def test_tables_and_columns_exist_after_the_upgrade(settings: Settings):
    engine, _ = _engine(settings, "0021")
    inspector = inspect(engine)
    assert {
        "architect_conversations",
        "architect_messages",
        "proposals",
        "agent_changes",
        "agent_templates",
    } <= set(inspector.get_table_names())
    agents = {c["name"] for c in inspector.get_columns("agents")}
    assert {"can_propose_agents", "proposal_id", "archived_at"} <= agents
    assert "proposal_id" in {c["name"] for c in inspector.get_columns("inbox_items")}
    kind = next(c for c in inspector.get_columns("runs") if c["name"] == "kind")
    assert kind["type"].length == 12


def test_existing_agents_cannot_propose_agents(settings: Settings):
    engine, config = _engine(settings, "0020")
    with engine.begin() as db:
        db.execute(text(_agent("a1")))
    command.upgrade(config, "0021")
    with engine.begin() as db:
        row = db.execute(
            text("SELECT can_propose_agents, proposal_id, archived_at FROM agents")
        ).one()
    assert tuple(row) == (0, None, None)


@pytest.mark.parametrize(
    "statement",
    [
        _conversation("c1", mode="pipeline"),
        _conversation("c1", status="done"),
        _proposal("p1", kind="skill"),
        _proposal("p1", origin="user"),
    ],
)
def test_modes_kinds_and_states_are_closed_lists(settings: Settings, statement: str):
    engine, _ = _engine(settings, "0021")
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(statement))


def test_a_template_name_is_unique(settings: Settings):
    engine, _ = _engine(settings, "0021")
    insert = (
        "INSERT INTO agent_templates (id, workspace_id, created_at, updated_at, name, description,"
        " color, payload) VALUES ('{id}', 'default', '" + NOW + "', '" + NOW + "', 'Redactor',"
        " '', '#fff', '{{}}')"
    )
    with engine.begin() as db:
        db.execute(text(insert.format(id="t1")))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(insert.format(id="t2")))


def test_deleting_a_conversation_keeps_its_proposal_and_drops_its_messages(settings: Settings):
    engine, _ = _engine(settings, "0021")
    with engine.begin() as db:
        db.execute(text("PRAGMA foreign_keys = ON"))
        db.execute(text(_conversation("c1")))
        db.execute(
            text(
                "INSERT INTO architect_messages (id, conversation_id, role, text, tool_events,"
                f" created_at) VALUES ('m1', 'c1', 'user', 'hola', '[]', '{NOW}')"
            )
        )
        db.execute(text(_proposal("p1", conversation_id="c1")))
    with engine.begin() as db:
        db.execute(text("PRAGMA foreign_keys = ON"))
        db.execute(text("DELETE FROM architect_conversations WHERE id = 'c1'"))
        assert db.execute(text("SELECT count(*) FROM architect_messages")).scalar() == 0
        assert db.execute(text("SELECT conversation_id FROM proposals")).scalar() is None


def test_deleting_a_proposal_leaves_its_drafts_and_deleting_the_agent_its_changes(
    settings: Settings,
):
    engine, _ = _engine(settings, "0021")
    with engine.begin() as db:
        db.execute(text("PRAGMA foreign_keys = ON"))
        db.execute(text(_proposal("p1")))
        db.execute(text(_agent("a1")))
        db.execute(text("UPDATE agents SET proposal_id = 'p1', status = 'draft'"))
        db.execute(
            text(
                "INSERT INTO agent_changes (id, agent_id, source, proposal_id, fields, created_at)"
                f" VALUES ('x1', 'a1', 'architect', 'p1', '{{}}', '{NOW}')"
            )
        )
    with engine.begin() as db:
        db.execute(text("PRAGMA foreign_keys = ON"))
        db.execute(text("DELETE FROM proposals WHERE id = 'p1'"))
        assert db.execute(text("SELECT proposal_id FROM agents")).scalar() is None
        assert db.execute(text("SELECT proposal_id FROM agent_changes")).scalar() is None
        db.execute(text("DELETE FROM agents WHERE id = 'a1'"))
        assert db.execute(text("SELECT count(*) FROM agent_changes")).scalar() == 0


def test_the_architect_kinds_are_accepted_only_after_the_migration(settings: Settings):
    inbox = (
        "INSERT INTO inbox_items (id, workspace_id, created_at, updated_at, kind, status,"
        " agent_name, agent_color, project_name, project_color, title, detail, options)"
        f" VALUES ('i1', 'default', '{NOW}', '{NOW}', 'proposal', 'pending', '', '#fff', '',"
        " '#fff', 'Agente propuesto', '', '[]')"
    )
    engine, config = _engine(settings, "0020")
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(inbox))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(_skill("s1", "architect")))
    command.upgrade(config, "0021")
    with engine.begin() as db:
        db.execute(text(inbox))
        db.execute(text(_skill("s1", "architect")))


def test_downgrade_removes_everything_new(settings: Settings):
    engine, config = _engine(settings, "0021")
    with engine.begin() as db:
        db.execute(text(_agent("a1")))
        db.execute(text(_proposal("p1", target_agent_id="a1", kind="agent_changes")))
        db.execute(text("UPDATE agents SET proposal_id = 'p1'"))
        db.execute(text(_skill("s1", "architect")))
    command.downgrade(config, "0020")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert not {"architect_conversations", "proposals", "agent_changes", "agent_templates"} & tables
    assert "proposal_id" not in {c["name"] for c in inspector.get_columns("agents")}
    with engine.begin() as db:
        assert db.execute(text("SELECT origin FROM skills")).scalar() == "user"
        assert db.execute(text("SELECT count(*) FROM agents")).scalar() == 1
