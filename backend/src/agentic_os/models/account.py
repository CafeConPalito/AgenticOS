from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, CheckConstraint, Float, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, WorkspaceMixin
from agentic_os.models.agent import Cli


class SessionState(StrEnum):
    OK = "ok"  # the CLI says the session is logged in
    DOWN = "down"  # logged out (or expired): its agents cannot start
    UNKNOWN = "unknown"  # not checked yet, or the CLI cannot tell


def _in(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{v.value}'" for v in enum)
    return f"{column} IN ({values})"


class CliAccount(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    """One login of a CLI (phase 10, ADR 0014).

    `config_dir` is the folder the CLI keeps that login in (`CLAUDE_CONFIG_DIR` for Claude
    Code). Null marks the **system account**: the CLI's own configuration, the one the person
    already had. Every installed CLI has one, so nothing changes until a second account is added.
    """

    __tablename__ = "cli_accounts"
    __table_args__ = (
        CheckConstraint(_in("cli", Cli), name="cli"),
        CheckConstraint(_in("session_state", SessionState), name="session_state"),
        # One default per CLI, enforced by the database (partial unique index).
        Index(
            "uq_cli_accounts_default_per_cli",
            "cli",
            unique=True,
            sqlite_where=text("is_default = 1"),
            postgresql_where=text("is_default"),
        ),
    )

    cli: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    plan: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    config_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    session_state: Mapped[str] = mapped_column(
        String(8), nullable=False, default=SessionState.UNKNOWN
    )
    session_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # Daily limit (phase 07) of this account: USD for Claude Code, tokens for agy. Null: none.
    daily_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The last value of each subscription window, read from the CLI's status line:
    # {window_id: {"used_pct": float, "resets_at": iso str, "read_at": iso str}}. The ids are the
    # CLI's own (`five_hour`, `seven_day`; agy: `gemini-5h`, `3p-weekly`…); the UI names them.
    quota: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    @property
    def is_system(self) -> bool:
        return self.config_dir is None
