"""The agentic-os MCP server, driven by the official MCP client against a real backend."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import anyio
import httpx
import httpx2
import pytest
from live_server import LiveServer, live_server
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from agentic_os.config import Settings
from agentic_os.models import Agent, MemoryNote, Project, Run, RunEvent
from agentic_os.services.memory import list_notes


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LiveServer]:
    with live_server(Settings(_env_file=None, data_dir=tmp_path / "data")) as live:
        yield live


def seed_run(server: LiveServer, tmp_path: Path, memory: str = "") -> tuple[str, str]:
    """A run row with its token (no CLI needed to exercise the tools)."""
    with server.db() as db:
        agent = Agent(name="Dev", role="Desarrollador", instructions="Escribe tests primero.")
        project = Project(name="Web", path=str(tmp_path), path_key=str(tmp_path))
        db.add_all([agent, project])
        db.flush()
        if memory:
            db.add(MemoryNote(project_id=project.id, text=memory))
        run = Run(
            agent_id=agent.id,
            project_id=project.id,
            agent_name="Dev",
            agent_color="#4FD1C5",
            project_name="Web",
            cli="claude",
            prompt="Arregla el login",
            cwd=str(tmp_path),
        )
        db.add(run)
        db.commit()
        run_id = run.id
    return run_id, server.manager.tokens.issue(run_id)


def call(url: str, tool: str, args: dict | None = None, headers: dict | None = None) -> str:
    async def go() -> str:
        async with (
            httpx2.AsyncClient(headers=headers or {}) as http,
            streamable_http_client(url, http_client=http) as (read, write, *_),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(tool, args or {})
            return result.content[0].text

    return anyio.run(go)


def mcp_url(server: LiveServer, token: str) -> str:
    return f"{server.url}/r/{token}/mcp"


def events(server: LiveServer, run_id: str) -> list[tuple[str, str]]:
    with server.db() as db:
        rows = db.query(RunEvent).filter_by(run_id=run_id).order_by(RunEvent.at).all()
        return [(e.name, e.detail) for e in rows]


def test_tools_update_the_run_the_project_and_the_events(server: LiveServer, tmp_path: Path):
    run_id, token = seed_run(server, tmp_path, memory="Usa pnpm.")
    url = mcp_url(server, token)

    context = call(url, "get_context")
    assert "# Tu rol: Dev · Desarrollador" in context
    assert "Escribe tests primero." in context
    assert "Usa pnpm." in context
    assert "complete_task" in context
    assert "# Tarea\nArregla el login" in context

    call(url, "report_status", {"message": "Leyendo el código del login"})
    call(url, "write_project_memory", {"note": "El login usa OAuth con PKCE."})
    assert "Puedes terminar" in call(url, "complete_task", {"summary": "Login arreglado"})

    with server.db() as db:
        run = db.get(Run, run_id)
        assert run.last_status == "Leyendo el código del login"
        assert run.summary == "Login arreglado"
        assert run.mcp_connected_at is not None
        notes = list_notes(db, run.project_id)
        assert [(n.author_kind, n.author_name, n.agent_id, n.text) for n in notes] == [
            ("user", "", None, "Usa pnpm."),
            ("agent", "Dev", run.agent_id, "El login usa OAuth con PKCE."),
        ]
    names = [name for name, _ in events(server, run_id)]
    assert names == [
        "mcp_connected",
        "get_context",
        "report_status",
        "write_project_memory",
        "complete_task",
    ]


def test_unknown_or_revoked_tokens_are_rejected(server: LiveServer, tmp_path: Path):
    run_id, token = seed_run(server, tmp_path)
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert httpx.post(f"{server.url}/r/{'x' * 40}/mcp", json=body).status_code == 401
    assert httpx.post(f"{server.url}/r/mcp", json=body).status_code == 401
    bearer = {"Authorization": f"Bearer {'y' * 40}"}
    assert httpx.post(f"{server.url}/r/mcp", json=body, headers=bearer).status_code == 401

    server.manager.tokens.revoke(run_id)  # the run ended
    assert httpx.post(mcp_url(server, token), json=body).status_code == 401


def test_a_token_only_acts_on_its_own_run(server: LiveServer, tmp_path: Path):
    mine, token = seed_run(server, tmp_path)
    other, _ = seed_run(server, tmp_path / "otro")
    # A forged run header is replaced by the run the token belongs to.
    forged = {"x-agentic-os-run": other}
    call(mcp_url(server, token), "report_status", {"message": "solo la mía"}, headers=forged)
    with server.db() as db:
        assert db.get(Run, mine).last_status == "solo la mía"
        assert db.get(Run, other).last_status is None
    assert events(server, other) == []


def test_bearer_header_works_like_the_path_token(server: LiveServer, tmp_path: Path):
    run_id, token = seed_run(server, tmp_path)
    bearer = {"Authorization": f"Bearer {token}"}
    call(f"{server.url}/r/mcp", "report_status", {"message": "por cabecera"}, headers=bearer)
    with server.db() as db:
        assert db.get(Run, run_id).last_status == "por cabecera"


def test_only_a_stage_that_can_reject_rejects(server: LiveServer, tmp_path: Path):
    run_id, token = seed_run(server, tmp_path)  # a manual run: no task, no stage
    url = mcp_url(server, token)
    answer = call(url, "complete_task", {"summary": "No me gusta", "verdict": "rejected"})
    assert "no puede rechazar" in answer
    with server.db() as db:
        run = db.get(Run, run_id)
        assert (run.summary, run.verdict) == (None, None)
    assert "complete_task" not in [name for name, _ in events(server, run_id)]

    assert "Puedes terminar" in call(url, "complete_task", {"summary": "Hecho"})
    with server.db() as db:
        assert db.get(Run, run_id).verdict == "approved"
