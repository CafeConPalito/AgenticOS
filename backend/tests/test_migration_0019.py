"""Migration 0019 (phase 17, block 1): skills, their versions, modes, origins, what each run was
offered and the Inbox kind «skill»."""

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-23 20:00:00.000000"


def _engine(settings: Settings, revision: str):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, revision)
    return engine, config


def _skill(skill_id: str, name: str = "revision", scope: str = "general", **level) -> str:
    project = f"'{level['project']}'" if "project" in level else "NULL"
    agent = f"'{level['agent']}'" if "agent" in level else "NULL"
    return (
        "INSERT INTO skills (id, workspace_id, created_at, updated_at, name, scope, project_id,"
        " agent_id, enabled, review, origin, description, model_invocable, vector_model) VALUES"
        f" ('{skill_id}', 'default', '{NOW}', '{NOW}', '{name}', '{scope}', {project}, {agent},"
        " 1, 'none', 'user', 'd', 1, '')"
    )


def _agent(agent_id: str) -> str:
    return (
        "INSERT INTO agents (id, workspace_id, created_at, updated_at, name, role, description,"
        " color, cli, model, instructions, permission_mode, allowed_tools, max_concurrency,"
        " can_spawn_subagents, can_create_tasks, status, fallback_model) VALUES"
        f" ('{agent_id}', 'default', '{NOW}', '{NOW}', 'Dev', '', '', '#fff', 'claude', '', '',"
        " 'ask', '[]', 1, 0, 0, 'active', '')"
    )


def test_tables_exist_after_the_upgrade(settings: Settings):
    engine, _ = _engine(settings, "0019")
    tables = set(inspect(engine).get_table_names())
    assert {
        "skills",
        "skill_versions",
        "skill_modes",
        "skill_origins",
        "run_skills",
        "skill_rejections",
    } <= tables
    assert "skill_version_id" in {c["name"] for c in inspect(engine).get_columns("inbox_items")}


def test_a_name_is_unique_per_level_even_for_general_skills(settings: Settings):
    engine, _ = _engine(settings, "0019")
    with engine.begin() as db:
        db.execute(text(_agent("a1")))
        db.execute(text(_skill("s1")))
        db.execute(text(_skill("s2", scope="agent", agent="a1")))  # same name, other level
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(_skill("s3")))  # NULL project and agent must still clash


def test_the_level_must_match_its_ids(settings: Settings):
    engine, _ = _engine(settings, "0019")
    with engine.begin() as db:
        db.execute(text(_agent("a1")))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(_skill("s1", scope="project", agent="a1")))


def test_a_mode_targets_an_agent_or_a_stage_not_both(settings: Settings):
    engine, _ = _engine(settings, "0019")
    with engine.begin() as db:
        db.execute(text(_agent("a1")))
        db.execute(text(_skill("s1")))
        db.execute(text("INSERT INTO skill_modes VALUES ('m1', 's1', 'a1', NULL, 'always')"))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text("INSERT INTO skill_modes VALUES ('m2', 's1', NULL, NULL, 'never')"))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text("INSERT INTO skill_modes VALUES ('m3', 's1', 'a1', NULL, 'sometimes')"))


def test_the_inbox_accepts_the_skill_kind_only_after_the_migration(settings: Settings):
    insert = (
        "INSERT INTO inbox_items (id, workspace_id, created_at, updated_at, kind, status,"
        " agent_name, agent_color, project_name, project_color, title, detail, options)"
        f" VALUES ('i1', 'default', '{NOW}', '{NOW}', 'skill', 'pending', '', '#fff', '',"
        " '#fff', 'Skill propuesta', '', '[]')"
    )
    engine, config = _engine(settings, "0018")
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(insert))
    command.upgrade(config, "0019")
    with engine.begin() as db:
        db.execute(text(insert))


def test_downgrade_removes_everything_new(settings: Settings):
    engine, config = _engine(settings, "0019")
    with engine.begin() as db:
        db.execute(text(_skill("s1")))
    command.downgrade(config, "0018")
    inspector = inspect(engine)
    assert "skills" not in inspector.get_table_names()
    assert "skill_version_id" not in {c["name"] for c in inspector.get_columns("inbox_items")}
