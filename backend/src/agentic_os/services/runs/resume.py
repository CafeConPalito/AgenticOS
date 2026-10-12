"""«Reanudar sesión» (phase 08, ADR 0012): continue the CLI conversation of a run that ended
before its time (the app closed, the backend crashed, the user stopped it).

The resumed session is a new run linked to the old one (`resumed_from_id`), with a fresh
context, MCP token and hooks: the CLIs keep none of them in the session (evidence R1).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.errors import ApiError
from agentic_os.models import Cli, Run, RunStatus, Task, TaskStatus
from agentic_os.services import tasks as task_ops
from agentic_os.services.usage.parsers import agy_baseline, claude_baseline

# The conversation already holds the task: the resumed CLI only needs to be told to go on.
RESUME_PROMPT = (
    "La sesión anterior se interrumpió. Continúa con la tarea donde la dejaste. Si ya la "
    "habías terminado, dalo por hecho con complete_task."
)
RESUMABLE = (RunStatus.INTERRUPTED, RunStatus.FAILED, RunStatus.STOPPED, RunStatus.EXITED)
# The error of a resumed run whose CLI no longer has the conversation.
SESSION_MISSING = "session_missing"


def resumed_by(db: Session, run_id: str) -> str | None:
    return db.scalar(select(Run.id).where(Run.resumed_from_id == run_id).limit(1))


def resumable(db: Session, run: Run) -> bool:
    """Whether «Reanudar sesión» is offered. The transcript is only checked when resuming."""
    if RunStatus(run.status) not in RESUMABLE or not run.cli_session_id:
        return False
    if run.parent_run_id or run.error == SESSION_MISSING:
        return False  # a subagent goes with its parent; a lost conversation cannot come back
    if run.agent_id is None or run.project_id is None or resumed_by(db, run.id):
        return False
    if run.task_id:
        # Only the task's latest run, while the task waits for the user (not after a retry).
        task = db.get(Task, run.task_id)
        if task is None or task.status != TaskStatus.WAITING_HUMAN or task_ops.is_live(task):
            return False
        newer = db.scalar(
            select(Run.id)
            .where(
                Run.task_id == task.id,
                Run.parent_run_id.is_(None),
                Run.created_at > run.created_at,
            )
            .limit(1)
        )
        if newer is not None:
            return False
    return True


def check(db: Session, run: Run, transcript: Path | None) -> dict:
    """Raises if the run cannot be resumed; otherwise returns the usage baseline.
    `transcript`: the CLI's record of the conversation (UsageService.transcript)."""
    if not resumable(db, run):
        raise ApiError(409, "not_resumable", "this run cannot be resumed", "id")
    if not Path(run.cwd).is_dir():
        raise ApiError(409, "folder_not_found", "the run's folder no longer exists", "cwd")
    if transcript is None or not transcript.is_file():
        raise ApiError(409, "session_unavailable", "the CLI no longer has this conversation", "id")
    if run.cli == Cli.CLAUDE:
        return claude_baseline(transcript)
    return agy_baseline(transcript)
