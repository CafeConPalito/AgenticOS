"""The calls an agent makes to the tools of external servers (phase 18, block 7, CA11 and CA13).

They arrive as tool hooks (spikes S1 and S2): Claude's `PreToolUse` / `PostToolUse` /
`PostToolUseFailure` for `mcp__<server>__<tool>`, and agy's `PreToolUse` / `PostToolUse` for its
generic `call_mcp_tool` (the server comes with the plugin's prefix in `ServerName`). Each call is a
`RunToolCall`; the first one that works marks the connection of the run as connected. The calls
to our own `agentic-os` server are recorded elsewhere and ignored here.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import utcnow
from agentic_os.models import Cli, Run, RunConnection, RunConnectionStatus, RunToolCall
from agentic_os.services.connections.redact import Redactor
from agentic_os.services.connections.runtime import AGY_PREFIX

OWN_SERVER = "agentic-os"
ERROR_LIMIT = 500


@dataclass(frozen=True)
class Call:
    phase: str  # «start», «end» or «fail»
    server: str
    tool: str
    key: str  # the CLI's id of the call, to pair the start with its end
    error: str = ""
    duration_ms: int | None = None


def parse(cli: str, event: str, payload: object) -> Call | None:
    """The external call a tool hook is about, or None (not a tool hook, or one of our own)."""
    data = payload if isinstance(payload, dict) else {}
    if cli == Cli.CLAUDE:
        name = str(data.get("tool_name") or "")
        if not name.startswith("mcp__"):
            return None
        _, _, rest = name.partition("__")
        server, _, tool = rest.partition("__")
        if not server or not tool or server == OWN_SERVER:
            return None
        key = str(data.get("tool_use_id") or "")
        if event == "PreToolUse":
            return Call("start", server, tool, key)
        duration = data.get("duration_ms")
        duration = int(duration) if isinstance(duration, int | float) else None
        if event == "PostToolUse":
            return Call("end", server, tool, key, duration_ms=duration)
        if event == "PostToolUseFailure":
            return Call("fail", server, tool, key, str(data.get("error") or ""), duration)
        return None
    call = data.get("toolCall") if isinstance(data.get("toolCall"), dict) else {}
    if call.get("name") != "call_mcp_tool":
        return None
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    server = str(args.get("ServerName") or "").removeprefix(AGY_PREFIX)
    tool = str(args.get("ToolName") or "")
    if not server or not tool or server == OWN_SERVER:
        return None
    key = f"{data.get('conversationId') or ''}:{data.get('stepIdx') or ''}"
    if event == "PreToolUse":
        return Call("start", server, tool, key)
    if event == "PostToolUse":
        error = str(data.get("error") or "")
        return Call("fail" if error else "end", server, tool, key, error)
    return None


def _clean(text: str, secrets: frozenset[str]) -> str:
    redactor = Redactor(set(secrets))
    return (redactor.feed(text) + redactor.flush())[:ERROR_LIMIT] if text else ""


def record(db: Session, run: Run, call: Call, secrets: frozenset[str] = frozenset()) -> bool:
    """Keeps the call. False if the run was not given a connection of that name."""
    connection = db.scalar(
        select(RunConnection).where(
            RunConnection.run_id == run.id, RunConnection.connection_name == call.server
        )
    )
    if connection is None:
        return False
    if call.phase == "start":
        db.add(
            RunToolCall(
                run_id=run.id,
                connection_name=call.server,
                tool=call.tool,
                call_key=call.key,
                started_at=utcnow(),
            )
        )
        db.flush()
        return True
    row = db.scalar(
        select(RunToolCall)
        .where(
            RunToolCall.run_id == run.id,
            RunToolCall.call_key == call.key,
            RunToolCall.connection_name == call.server,
            RunToolCall.ok.is_(None),
        )
        .order_by(RunToolCall.started_at.desc())
    )
    if row is None:  # an end without its start: the call is still worth knowing
        row = RunToolCall(
            run_id=run.id,
            connection_name=call.server,
            tool=call.tool,
            call_key=call.key,
            started_at=utcnow(),
        )
        db.add(row)
    row.ok = call.phase == "end"
    row.error = "" if row.ok else _clean(call.error, secrets) or "(sin detalle)"
    if call.duration_ms is not None:
        row.duration_ms = call.duration_ms
    else:
        started = row.started_at
        row.duration_ms = max(0, int((utcnow() - started).total_seconds() * 1000))
    if row.ok and connection.status == RunConnectionStatus.SENT:
        connection.status = RunConnectionStatus.CONNECTED
    db.flush()
    return True
