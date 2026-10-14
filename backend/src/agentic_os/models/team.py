from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, WorkspaceMixin


class Team(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    """A named group of agents (phase 10). It only organizes: Inicio groups the agents by team.
    An agent belongs to at most one (`Agent.team_id`)."""

    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
