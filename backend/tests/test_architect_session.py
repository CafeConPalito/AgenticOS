"""The Architect's CLI (phase 19, block 4; CA2, CA4, CA6, CA7): one process per conversation, the
person's messages pasted whole, the reply read from the transcript, the sheet edited through the
MCP tools, asleep and resumed, reset, the agy guard and the token kinds. A real backend and the
fake CLI in a real ConPTY, driven through the service (its API arrives with block 5).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from live_server import in_process_only, live_server
from sqlalchemy import select
from test_scheduler_e2e import settings_for, wait_until

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.errors import ApiError
from agentic_os.models import (
    ArchitectConversation,
    ArchitectMessage,
    CliAccount,
    MessageRole,
    Run,
    RunKind,
    Skill,
)
from agentic_os.services.architect import config as architect_config
from agentic_os.services.architect import tools
from agentic_os.services.architect.service import Live
from agentic_os.services.clis import CliInfo, ModelOption

pytestmark = in_process_only


class FixedClis:
    """The installed CLIs as the tests want them (the real catalog would run the real ones)."""

    def list(self, refresh: bool = False) -> list[CliInfo]:
        return [
            CliInfo(
                id="claude", name="Claude Code", installed=True, models=[ModelOption(id="sonnet")]
            ),
            CliInfo(
                id="agy",
                name="agy",
                installed=True,
                models=[ModelOption(id="gemini-3.8-flash-high")],
            ),
        ]


def _start(server, cli: str, mode: str = "agent") -> tuple[object, str]:
    service = server.app.state.architect
    service.clis = FixedClis()
    with server.db() as db:
        architect_config.save(db, {"cli": cli})
        conversation = service.create(db, mode)
        db.commit()
        return service, conversation.id


def _messages(server, conversation_id: str, role: str = MessageRole.ARCHITECT) -> list[str]:
    with server.db() as db:
        rows = db.scalars(
            select(ArchitectMessage)
            .where(
                ArchitectMessage.conversation_id == conversation_id, ArchitectMessage.role == role
            )
            .order_by(ArchitectMessage.created_at)
        )
        return [m.text for m in rows]


def _conversation(server, conversation_id: str) -> ArchitectConversation:
    with server.db() as db:
        conversation = db.get(ArchitectConversation, conversation_id)
        db.expunge(conversation)
        return conversation


def _send(server, service, conversation_id: str, text: str) -> None:
    with server.db() as db:
        service.send(db, conversation_id, text)
        db.commit()


def _replied(server, conversation_id: str, count: int, timeout: float = 60) -> list[str]:
    assert wait_until(lambda: len(_messages(server, conversation_id)) >= count, timeout), _messages(
        server, conversation_id, MessageRole.SYSTEM
    )
    return _messages(server, conversation_id)


@pytest.mark.parametrize("cli", ["claude", "agy"])
def test_one_cli_takes_every_message_and_fills_the_sheet(tmp_path: Path, cli: str):
    """CA2: the reply arrives from the transcript and the tools fill the sheet live; a message of
    several lines is one turn; every message goes into the same process."""
    with live_server(settings_for(tmp_path)) as server:
        service, conversation_id = _start(server, cli)
        patch = json.dumps({"name": "Redactor", "role": "Redactor del blog", "cli": "claude"})
        _send(
            server,
            service,
            conversation_id,
            f"Quiero un redactor\nFICHA: {patch}\nRESPUESTA: Hecho el nombre",
        )
        assert _replied(server, conversation_id, 1) == ["Hecho el nombre"]
        first_run = _conversation(server, conversation_id).run_id
        sheet = _conversation(server, conversation_id).sheet
        assert sheet["agents"]["main"]["name"] == "Redactor"
        with server.db() as db:
            [reply] = db.scalars(
                select(ArchitectMessage).where(ArchitectMessage.role == MessageRole.ARCHITECT)
            )
            assert {"main.name", "main.role", "main.cli"} <= set(reply.tool_events[0]["fields"])
            run = db.get(Run, first_run)
            assert run.kind == RunKind.ARCHITECT and run.agent_id is None and run.project_id is None
        assert wait_until(lambda: service.state(conversation_id) == "idle", 10)

        _send(
            server,
            service,
            conversation_id,
            "Dos cosas:\nRESPUESTA: primera línea\nRESPUESTA: segunda línea",
        )
        assert _replied(server, conversation_id, 2)[1] == "primera línea\n\nsegunda línea"
        assert _conversation(server, conversation_id).run_id == first_run  # the same CLI


@pytest.mark.parametrize("cli", ["claude", "agy"])
def test_asleep_it_resumes_the_same_conversation_and_reset_starts_clean(tmp_path: Path, cli: str):
    """CA6: closed and resumed with its history; «Reiniciar» starts a CLI without it."""
    with live_server(settings_for(tmp_path)) as server:
        service, conversation_id = _start(server, cli)
        _send(server, service, conversation_id, "Hola\nRESPUESTA: uno")
        _replied(server, conversation_id, 1)
        session_id = _conversation(server, conversation_id).cli_session_id
        assert session_id
        service.sleep(conversation_id)
        assert service.state(conversation_id) == "asleep"

        _send(server, service, conversation_id, "Sigo\nRESPUESTA: dos")
        assert _replied(server, conversation_id, 2)[1] == "dos"
        resumed = _conversation(server, conversation_id)
        assert resumed.cli_session_id == session_id
        with server.db() as db:
            assert db.get(Run, resumed.run_id).cli_session_id == session_id

        with server.db() as db:
            service.reset(db, conversation_id)
        _send(server, service, conversation_id, "De nuevo\nRESPUESTA: tres")
        _replied(server, conversation_id, 3)
        assert _conversation(server, conversation_id).cli_session_id != session_id


def test_a_field_locked_by_the_person_is_refused_to_the_architect(tmp_path: Path):
    with live_server(settings_for(tmp_path)) as server:
        service, conversation_id = _start(server, "claude")
        with server.db() as db:
            answer = service.patch_sheet(db, conversation_id, {"color": "#FF0000"})
            db.commit()
        assert answer["locked"] == ["main.color"]
        out = tmp_path / "answer.json"
        patch = json.dumps({"patch": {"color": "#00FF00", "role": "QA"}})
        _send(
            server,
            service,
            conversation_id,
            f"Cambia el color\nHERRAMIENTA: update_sheet|{patch}|{out}",
        )
        _replied(server, conversation_id, 1)
        refused = json.loads(out.read_text("utf-8"))["refused"]
        assert "request_unlock" in refused["main.color"]
        sheet = _conversation(server, conversation_id).sheet["agents"]["main"]
        assert (sheet["color"], sheet["role"]) == ("#FF0000", "QA")


def test_the_agy_guard_denies_every_tool_but_the_architects(tmp_path: Path):
    """CA4: agy has no flag to take its tools away; its PreToolUse guard asks the backend."""
    with live_server(settings_for(tmp_path)) as server:
        service, conversation_id = _start(server, "agy")
        denied, allowed = tmp_path / "denied.json", tmp_path / "allowed.json"
        _send(
            server,
            service,
            conversation_id,
            f"Prueba\nGUARDIA: read_file|{denied}\nGUARDIA: call_mcp_tool|{allowed}",
        )
        _replied(server, conversation_id, 1)
        assert json.loads(denied.read_text("utf-8"))["decision"] == "deny"
        assert json.loads(allowed.read_text("utf-8"))["decision"] == "allow"


def test_tokens_only_open_their_own_server(tmp_path: Path):
    """CA4: an Architect's token cannot use the agents' MCP server, nor the other way round."""
    with live_server(settings_for(tmp_path)) as server:
        manager = server.manager
        architect = manager.tokens.issue("run-a", "architect")
        agent = manager.tokens.issue("run-b")
        body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        headers = {"Accept": "application/json, text/event-stream"}
        for path, token in (("/r/mcp", architect), ("/a/agent/mcp", agent), ("/a/team/mcp", agent)):
            response = httpx.post(
                server.url + path,
                json=body,
                headers={**headers, "Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 401, path
        assert httpx.post(server.url + "/a/nada/mcp", json=body).status_code == 404


def test_a_reached_daily_limit_says_so_without_starting_the_cli(tmp_path: Path):
    """CA7: the account is checked before every message."""
    with live_server(settings_for(tmp_path)) as server:
        service, conversation_id = _start(server, "claude")
        with server.db() as db:
            for account in db.scalars(select(CliAccount).where(CliAccount.cli == "claude")):
                account.daily_limit = 0.0
            db.commit()
        with server.db() as db, pytest.raises(ApiError) as caught:
            service.send(db, conversation_id, "Hola")
        assert caught.value.code == "architect_unavailable"
        assert "límite diario" in caught.value.message
        with server.db() as db:
            assert db.scalar(select(Run).where(Run.kind == RunKind.ARCHITECT)) is None
            assert db.scalar(select(ArchitectMessage)) is None


def test_interrupting_stops_the_turn_and_keeps_the_cli(tmp_path: Path):
    with live_server(settings_for(tmp_path)) as server:
        service, conversation_id = _start(server, "claude")
        _send(server, service, conversation_id, "Hola\nRESPUESTA: uno")
        _replied(server, conversation_id, 1)
        run_id = _conversation(server, conversation_id).run_id
        _send(server, service, conversation_id, "LARGO")
        assert wait_until(lambda: service.state(conversation_id) == "thinking", 20)
        assert service.interrupt(conversation_id)
        assert wait_until(lambda: service.state(conversation_id) == "idle", 10)
        assert not service.interrupt(conversation_id)  # nothing to stop now
        _send(server, service, conversation_id, "Sigue\nRESPUESTA: dos")
        assert _replied(server, conversation_id, 2)[1] == "dos"
        assert _conversation(server, conversation_id).run_id == run_id


def test_the_conversation_counts_as_an_architect_run_with_its_usage(tmp_path: Path):
    """CA7: the CLI's usage is read from its transcript like an agent's."""
    with live_server(settings_for(tmp_path)) as server:
        service, conversation_id = _start(server, "claude")
        _send(server, service, conversation_id, "Hola\nCONSUMO: 500\nRESPUESTA: uno")
        _replied(server, conversation_id, 1)
        run_id = _conversation(server, conversation_id).run_id

        def counted() -> bool:
            with server.db() as db:
                return db.get(Run, run_id).input_tokens >= 500

        assert wait_until(counted, 20)


def test_each_mode_only_gets_the_tools_of_its_job():
    """Spike S3: designing one agent, the model put it in a pipeline; it has no such tool now."""

    class Backend:
        def mcp_connected(self, run_id: str) -> None: ...
        def call_tool(self, run_id: str, name: str, args: dict) -> str:
            return ""

    def names(toolset: str) -> set[str]:
        server = tools.build(Backend(), toolset)
        return {t.name for t in asyncio.run(server.list_tools())}

    agent, team = names(tools.AGENT), names(tools.TEAM)
    pipeline_tools = {
        "set_pipeline",
        "set_team",
        "use_existing_agent",
        "remove_agent",
        "list_projects",
    }
    assert not pipeline_tools & agent
    assert pipeline_tools <= team
    assert {"update_sheet", "search_skills", "request_unlock", "draft_skill"} <= agent <= team


def test_searches_return_at_most_eight_and_unknown_runs_get_an_error(tmp_path: Path):
    """Spike S4: a search, never a whole catalog."""
    with live_server(settings_for(tmp_path)) as server:
        service, conversation_id = _start(server, "claude")
        with server.db() as db:
            for i in range(20):
                db.add(
                    Skill(
                        workspace_id=DEFAULT_WORKSPACE,
                        name=f"redaccion-{i}",
                        description="Redacción de textos",
                    )
                )
            db.commit()
        service._live[conversation_id] = Live(conversation_id, "run-x", "claude", 1)
        service._by_run["run-x"] = conversation_id
        found = json.loads(
            service.call_tool("run-x", "search_skills", {"query": "redacción textos"})
        )
        assert len(found) == 8
        clis = json.loads(service.call_tool("run-x", "list_clis", {}))
        assert {c["cli"] for c in clis["clis"]} == {"claude", "agy"}
        assert all(a["id"] for c in clis["clis"] for a in c["accounts"])
        assert "error" in json.loads(service.call_tool("run-desconocido", "get_sheet", {}))
        assert "error" in json.loads(service.call_tool("run-x", "borrar_todo", {}))
