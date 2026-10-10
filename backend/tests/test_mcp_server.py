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
from agentic_os.models import Agent, Project, Run, RunEvent


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LiveServer]:
    with live_server(Settings(_env_file=None, data_dir=tmp_path / "data")) as live:
        yield live


def seed_run(server: LiveServer, tmp_path: Path, memory: str = "") -> tuple[str, str]:
    """A run row with its token (no CLI needed to exercise the tools)."""
    with server.db() as db:
        agent = Agent(name="Dev", role="Desarrollador", instructions="Escribe tests primero.")
        project = Project(name="Web", path=str(tmp_path), path_key=str(tmp_path), memory=memory)
        db.add_all([agent, project])
        db.flush()
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
        memory = db.get(Project, run.project_id).memory
    assert memory.startswith("Usa pnpm.\n\n### ")
    assert memory.endswith("· Dev\nEl login usa OAuth con PKCE.")
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
