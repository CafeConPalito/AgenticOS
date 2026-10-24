"""Which connections a run receives (phase 18, block 4, CA5 and CA6).

The active connections given to the general level, to the run's project or to its agent, minus
the ones taken away from the agent or from the pipeline stage the run is in (a branch is a
stage). A subagent is resolved with its own agent, not its parent's, and the internal headless
runs (the branch decider, the image describer) do not ask at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import (
    KnowledgeScope,
    McpAssignment,
    McpConnection,
    McpExclusion,
)

LEVEL_RANK = {KnowledgeScope.GENERAL: 1, KnowledgeScope.PROJECT: 2, KnowledgeScope.AGENT: 3}


@dataclass
class Effective:
    connection: McpConnection
    level: str  # the most concrete level it came from
    tools: list[dict] = field(default_factory=list)  # the ones the run will see
    tokens: int = 0


@dataclass
class Excluded:
    connection: McpConnection
    level: str
    reason: str  # «disabled», «agent» or «stage»


@dataclass
class Report:
    effective: list[Effective] = field(default_factory=list)
    excluded: list[Excluded] = field(default_factory=list)

    @property
    def total_tools(self) -> int:
        return sum(len(e.tools) for e in self.effective)

    @property
    def total_tokens(self) -> int:
        return sum(e.tokens for e in self.effective)


def allowed_tools(connection: McpConnection) -> list[dict]:
    """The tools of the last test that the person lets the agents use."""
    if connection.tool_mode == "selected":
        wanted = set(connection.allowed_tools)
        return [t for t in connection.tools if t["name"] in wanted]
    return list(connection.tools)


def estimate_tokens(tools: list[dict]) -> int:
    """About what the tools' names, descriptions and schemas cost in the agent's context."""
    chars = sum(
        len(
            json.dumps(
                {"n": t["name"], "d": t.get("description", ""), "s": t.get("input_schema", {})}
            )
        )
        for t in tools
    )
    return round(chars / 4)


def resolve(
    db: Session, agent_id: str | None, project_id: str | None, stage_id: str | None
) -> Report:
    level = [McpAssignment.scope == KnowledgeScope.GENERAL]
    if project_id:
        level.append(McpAssignment.project_id == project_id)
    if agent_id:
        level.append(McpAssignment.agent_id == agent_id)
    rows = db.execute(
        select(McpAssignment, McpConnection)
        .join(McpConnection, McpConnection.id == McpAssignment.connection_id)
        .where(McpConnection.workspace_id == DEFAULT_WORKSPACE, or_(*level))
        .order_by(McpConnection.name)
    ).all()
    best: dict[str, tuple[McpConnection, str]] = {}
    for assignment, connection in rows:
        current = best.get(connection.id)
        if current is None or LEVEL_RANK[assignment.scope] > LEVEL_RANK[current[1]]:
            best[connection.id] = (connection, assignment.scope)

    removed_by_agent: set[str] = set()
    removed_by_stage: set[str] = set()
    clauses = []
    if agent_id:
        clauses.append(McpExclusion.agent_id == agent_id)
    if stage_id:
        clauses.append(McpExclusion.stage_id == stage_id)
    if clauses:
        for row in db.scalars(select(McpExclusion).where(or_(*clauses))):
            (removed_by_stage if row.stage_id else removed_by_agent).add(row.connection_id)

    report = Report()
    for connection, scope in sorted(best.values(), key=lambda pair: pair[0].name):
        if not connection.enabled:
            report.excluded.append(Excluded(connection, scope, "disabled"))
        elif connection.id in removed_by_stage:
            report.excluded.append(Excluded(connection, scope, "stage"))
        elif connection.id in removed_by_agent:
            report.excluded.append(Excluded(connection, scope, "agent"))
        else:
            tools = allowed_tools(connection)
            report.effective.append(Effective(connection, scope, tools, estimate_tokens(tools)))
    return report


# -- exclusions ---------------------------------------------------------------------------------
def excluded_ids(
    db: Session, *, agent_id: str | None = None, stage_id: str | None = None
) -> list[str]:
    column = McpExclusion.agent_id if agent_id else McpExclusion.stage_id
    return list(
        db.scalars(select(McpExclusion.connection_id).where(column == (agent_id or stage_id)))
    )


def set_exclusions(
    db: Session,
    connection_ids: list[str],
    *,
    agent_id: str | None = None,
    stage_id: str | None = None,
) -> None:
    """Replaces the connections taken away from an agent or from a stage."""
    wanted = set(connection_ids)
    known = set(
        db.scalars(
            select(McpConnection.id).where(
                McpConnection.workspace_id == DEFAULT_WORKSPACE, McpConnection.id.in_(wanted)
            )
        )
    )
    column = McpExclusion.agent_id if agent_id else McpExclusion.stage_id
    owner = agent_id or stage_id
    for row in db.scalars(select(McpExclusion).where(column == owner)):
        if row.connection_id in wanted & known:
            wanted.discard(row.connection_id)
        else:
            db.delete(row)
    for connection_id in wanted & known:
        db.add(McpExclusion(connection_id=connection_id, agent_id=agent_id, stage_id=stage_id))
    db.flush()
