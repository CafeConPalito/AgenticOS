"""Which task a branch belongs to (phase 12): the `agentic/T-n` branches of the tasks."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.models import ProjectRepo, Task, TaskRepo
from agentic_os.schemas.git import BranchInfo


def annotate(db: Session, repo: ProjectRepo, branches: list[BranchInfo]) -> list[BranchInfo]:
    """Fills in the task of each task branch (local ones; the remote copy gets it too)."""
    tasks = {
        row.branch: task
        for row, task in db.execute(
            select(TaskRepo, Task)
            .join(Task, Task.id == TaskRepo.task_id)
            .where(TaskRepo.repo_id == repo.id)
        )
    }
    # A task from before the repository rows only has its branch name.
    for task in db.scalars(
        select(Task).where(Task.project_id == repo.project_id, Task.branch.is_not(None))
    ):
        tasks.setdefault(task.branch or "", task)
    for branch in branches:
        name = branch.name.split("/", 1)[1] if branch.remote else branch.name
        task = tasks.get(name)
        if task is not None:
            branch.task_id, branch.task_code = task.id, task.code
            branch.task_title, branch.task_status = task.title, task.status
    return branches
