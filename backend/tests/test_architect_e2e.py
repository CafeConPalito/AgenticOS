"""The Architect end to end (phase 19, block 11; CA1, CA11): a real backend and the fake CLI in a
real ConPTY, driven only through the API so it also runs against the packaged backend. A
conversation fills the sheet, becomes a draft, the draft is approved and gets a task done."""

from __future__ import annotations

import json
from pathlib import Path

from live_server import live_server
from test_scheduler_e2e import Api, settings_for, wait_until


def converse(api: Api, conversation_id: str, text: str, replies: int) -> dict:
    """A message to the Architect and the conversation once it has answered `replies` times."""
    api.post(f"/api/architect/conversations/{conversation_id}/messages", {"text": text})
    path = f"/api/architect/conversations/{conversation_id}"

    def answered() -> bool:
        messages = api.get(path)["messages"]
        return len([m for m in messages if m["role"] == "architect"]) >= replies

    assert wait_until(answered, 90), api.get(path)["messages"]
    return api.get(path)


def test_a_conversation_becomes_an_approved_agent_that_does_a_task(tmp_path: Path):
    """CA1, CA11: conversation → sheet → draft → approval → a task completed by the new agent."""
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        api.client_put("/api/settings/architect", {"cli": "claude"})
        project = api.post("/api/projects", {"name": "Blog", "path": str(_folder(tmp_path))})
        conversation = api.post("/api/architect/conversations", {"mode": "agent"})
        patch = json.dumps(
            {
                "name": "Redactor",
                "role": "Redactor del blog",
                "cli": "claude",
                "instructions": "Escribe posts cercanos.",
            }
        )
        after = converse(
            api,
            conversation["id"],
            f"Quiero un redactor\nFICHA: {patch}\nRESPUESTA: Ficha lista",
            replies=1,
        )
        assert after["sheet"]["ready"] is True, after["sheet"]["issues"]
        assert after["sheet"]["sheet"]["agents"]["main"]["name"] == "Redactor"

        proposal = api.post(f"/api/architect/conversations/{conversation['id']}/propose")
        assert proposal["kind"] == "new_agent" and proposal["target_agent_id"]
        agent_id = proposal["target_agent_id"]
        assert api.get(f"/api/agents/{agent_id}")["status"] == "draft"

        api.post(f"/api/proposals/{proposal['id']}/approve", {})
        assert api.get(f"/api/agents/{agent_id}")["status"] == "active"

        api.client_put(
            f"/api/projects/{project['id']}/pipeline",
            {"name": "Solo", "stages": [{"name": "Redacción", "agent_id": agent_id}]},
        )
        task = api.post(
            "/api/tasks",
            {"project_id": project["id"], "title": "escribe el primer post; TERMINA: hecho"},
        )
        done = api.wait_status(task["id"], "done", "waiting_human", timeout=240)
        assert done["status"] == "done", done


def _folder(root: Path) -> Path:
    folder = root / "blog"
    folder.mkdir(exist_ok=True)
    return folder
