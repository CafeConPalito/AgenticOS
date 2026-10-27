"""Templates and agents as files (phase 19, block 7; CA8, CA9): an agent exported without
secrets or local ids, saved as a template and created again from it with another account, and
imported into a clean installation where what is missing is listed and left out."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import (
    Agent,
    CliAccount,
    KnowledgeDoc,
    KnowledgeScope,
    McpAssignment,
    McpConnection,
    Skill,
    SkillMode,
    SourceKind,
)
from agentic_os.services.skills.format import SKILL_MD, compose_skill_md


def _skill_files(name: str) -> dict[str, bytes]:
    md = compose_skill_md({"name": name, "description": f"Cómo hacer {name}."}, f"# {name}\nPasos.")
    return {SKILL_MD: md.encode()}


def _writer(client: TestClient) -> dict:
    """An agent with a mode on a library skill, a skill of its own, a connection (with a secret
    in the catalog) and a document of its level."""
    agent = client.post(
        "/api/agents",
        json={"name": "Redactor", "role": "Redactor", "instructions": "Escribe.", "cli": "claude"},
    ).json()
    lib = client.app.state.run_manager.skill_library
    with client.app.state.sessionmaker() as db:
        general, _ = lib.create(
            db, scope="general", project_id=None, agent_id=None, files=_skill_files("seo-basico")
        )
        lib.create(
            db,
            scope="agent",
            project_id=None,
            agent_id=agent["id"],
            files=_skill_files("tono-propio"),
        )
        db.add(SkillMode(skill_id=general.id, agent_id=agent["id"], mode="always"))
        github = McpConnection(
            workspace_id=DEFAULT_WORKSPACE,
            name="github",
            headers={"Authorization": "Bearer ${secret:TOKEN}"},
            secret_keys=["TOKEN"],
        )
        db.add(github)
        db.flush()
        db.add(McpAssignment(connection_id=github.id, scope="agent", agent_id=agent["id"]))
        db.add(
            KnowledgeDoc(
                workspace_id=DEFAULT_WORKSPACE,
                title="Guía de estilo",
                scope=KnowledgeScope.AGENT,
                agent_id=agent["id"],
                source_kind=SourceKind.URL,
                url="https://example.com/estilo",
            )
        )
        db.commit()
    return agent


def test_an_export_has_no_secrets_nor_local_ids(client: TestClient):
    agent = _writer(client)
    exported = client.get(f"/api/agents/{agent['id']}/export").json()
    assert (exported["format"], exported["version"]) == ("agentic-os.agent", 1)
    assert exported["agent"]["name"] == "Redactor" and "id" not in exported["agent"]
    assert "account_id" not in exported["agent"] and "team_id" not in exported["agent"]
    assert exported["skills"]["modes"] == [{"name": "seo-basico", "mode": "always"}]
    [own] = exported["skills"]["own"]
    assert own["name"] == "tono-propio" and "Pasos." in own["files"]["SKILL.md"]
    assert exported["connections"] == ["github"]
    assert exported["knowledge"] == [
        {"title": "Guía de estilo", "kind": "url", "source": "https://example.com/estilo"}
    ]
    text = str(exported)
    assert "Bearer" not in text and agent["id"] not in text


def test_a_template_creates_the_agent_again_with_another_account(client: TestClient):
    """CA8."""
    agent = _writer(client)
    template = client.post(
        f"/api/agents/{agent['id']}/save-as-template", json={"name": "Redactor base"}
    ).json()
    assert template["own"] and (
        template["skills"],
        template["connections"],
        template["documents"],
    ) == (2, 1, 1)
    listed = client.get("/api/agent-templates").json()
    assert [t["id"] for t in listed if t["own"]] == [template["id"]]
    assert len([t for t in listed if not t["own"]]) == 5  # the fixed ones
    with client.app.state.sessionmaker() as db:
        other = CliAccount(cli="claude", label="empresa")
        db.add(other)
        db.commit()
        other_id = other.id
    created = client.post(
        "/api/agents",
        json={"template": template["id"], "name": "Redactor 2", "account_id": other_id},
    ).json()
    assert (created["name"], created["account_id"], created["status"]) == (
        "Redactor 2",
        other_id,
        "active",
    )
    assert created["template"] == template["id"]
    with client.app.state.sessionmaker() as db:
        assert (
            db.scalar(select(SkillMode.mode).where(SkillMode.agent_id == created["id"])) == "always"
        )
        own = db.scalar(select(Skill).where(Skill.agent_id == created["id"]))
        assert own.name == "tono-propio"
        assert db.scalar(select(McpAssignment).where(McpAssignment.agent_id == created["id"]))
        assert db.scalar(select(KnowledgeDoc).where(KnowledgeDoc.agent_id == created["id"])).url


def test_templates_are_renamed_duplicated_and_deleted_but_not_the_fixed_ones(client: TestClient):
    agent = _writer(client)
    template = client.post(f"/api/agents/{agent['id']}/save-as-template").json()
    assert template["name"] == "Redactor"
    again = client.post(f"/api/agents/{agent['id']}/save-as-template").json()
    assert again["name"] == "Redactor (2)"
    renamed = client.patch(f"/api/agent-templates/{template['id']}", json={"name": "Blog"}).json()
    assert renamed["name"] == "Blog"
    copy = client.post(f"/api/agent-templates/{template['id']}/duplicate").json()
    assert copy["name"] == "Blog (2)"
    assert client.delete(f"/api/agent-templates/{copy['id']}").status_code == 204
    assert client.patch("/api/agent-templates/writer", json={"name": "x"}).status_code == 404
    assert client.delete("/api/agent-templates/writer").status_code == 404


def test_importing_into_a_clean_installation_leaves_out_what_is_missing(
    client: TestClient, tmp_path: Path
):
    """CA9."""
    exported = client.get(f"/api/agents/{_writer(client)['id']}/export").json()
    clean = Settings(_env_file=None, data_dir=tmp_path / "clean", check_sessions_at_startup=False)
    with TestClient(create_app(clean)) as other:
        preview = other.post("/api/agents/import/preview", json={"payload": exported}).json()
        assert preview["missing_skills"] == ["seo-basico"]
        assert preview["missing_connections"] == ["github"]
        assert preview["own_skills"] == ["tono-propio"]
        imported = other.post(
            "/api/agents/import", json={"payload": exported, "name": "Redactor importado"}
        )
        assert imported.status_code == 201, imported.text
        body = imported.json()
        assert body["agent"]["status"] == "draft" and body["agent"]["name"] == "Redactor importado"
        assert any("seo-basico" in n for n in body["notes"]) and any(
            "github" in n for n in body["notes"]
        )
        with other.app.state.sessionmaker() as db:
            agent = db.get(Agent, body["agent"]["id"])
            assert db.scalar(select(Skill.name).where(Skill.agent_id == agent.id)) == "tono-propio"
            assert db.scalar(select(SkillMode)) is None
            assert db.scalar(select(KnowledgeDoc).where(KnowledgeDoc.agent_id == agent.id)).url


def test_a_file_that_is_not_an_agent_is_refused(client: TestClient):
    for payload in (
        {"format": "otra-cosa"},
        {"format": "agentic-os.agent", "version": 9, "agent": {"name": "x"}},
    ):
        response = client.post("/api/agents/import/preview", json={"payload": payload})
        assert response.status_code == 422
