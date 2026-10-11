from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base

SCHEDULER_PAUSED = "scheduler_paused"


class AppState(Base):
    """Small global switches that must survive a restart (e.g. the scheduler pause)."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
