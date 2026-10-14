from enum import StrEnum

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, WorkspaceMixin


class Cli(StrEnum):
    CLAUDE = "claude"
    AGY = "agy"


class PermissionMode(StrEnum):
    AUTONOMOUS = "autonomous"
    RESTRICTED = "restricted"
    ASK = "ask"


class AgentStatus(StrEnum):
    ACTIVE = "active"
    DRAFT = "draft"


class Tool(StrEnum):
    READ = "read"
    EDIT = "edit"
    TERMINAL = "terminal"
    GIT = "git"
    WEB = "web"
    BROWSER = "browser"
    MCP_AGENTIC_OS = "mcp_agentic_os"


MAX_CONCURRENCY = 5


def _in(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{v.value}'" for v in enum)
    return f"{column} IN ({values})"


class Agent(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint(_in("cli", Cli), name="cli"),
        CheckConstraint(_in("permission_mode", PermissionMode), name="permission_mode"),
        CheckConstraint(_in("status", AgentStatus), name="status"),
        CheckConstraint(f"max_concurrency BETWEEN 1 AND {MAX_CONCURRENCY}", name="max_concurrency"),
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    color: Mapped[str] = mapped_column(String(9), nullable=False, default="#8FB4FF")
    cli: Mapped[str] = mapped_column(String(16), nullable=False, default=Cli.CLAUDE)
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    permission_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PermissionMode.ASK
    )
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    can_spawn_subagents: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_create_tasks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=AgentStatus.ACTIVE)
    template: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Phase 10. No team: shown under «Sin equipo». No account: the default one of its CLI.
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cli_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
