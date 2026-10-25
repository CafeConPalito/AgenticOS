from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base

SCHEDULER_PAUSED = "scheduler_paused"
NOTIFICATIONS = "notifications"  # JSON: which Inbox kinds notify, and the sound
USAGE_LIMITS = "usage_limits"  # JSON: {"claude_usd": float | null, "agy_tokens": int | null}
LOG_RETENTION = "log_retention"  # JSON: {"days": int | null} (null: never delete)
SWITCH_THRESHOLD = "switch_threshold"  # percent of a subscription window that triggers the alert
KNOWLEDGE = "knowledge"  # JSON: the knowledge library's limits and switches (phase 14)
DICTATION = "dictation"  # JSON: the dictation settings (phase 16)
SKILLS = "skills"  # JSON: the skill library's budgets, proposals and registries (phase 17)
CONNECTIONS = "connections"  # JSON: the MCP connections' timeouts and registries (phase 18)


class AppState(Base):
    """Small global switches that must survive a restart (e.g. the scheduler pause)."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
