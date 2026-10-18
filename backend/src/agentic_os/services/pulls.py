"""Pull requests of a task: one per repository where it left work (phase 12, ADR 0018)."""

from __future__ import annotations

import contextlib

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.models import Project, Task, TaskEvent, TaskEventKind
from agentic_os.services import integration
from agentic_os.services import tasks as task_ops
from agentic_os.services.forges import forge_for
from agentic_os.services.forges.base import NewPull, PullRequest
from agentic_os.services.gitx import remote
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo


class RepoPull(BaseModel):
    repo_id: str
    name: str
    status: str  # created | nothing | failed
    pull: PullRequest | None = None
    error_code: str | None = None
    message: str = ""


def _summary(db: Session, task: Task) -> str:
    return (
        db.scalar(
            select(TaskEvent.detail)
            .where(
                TaskEvent.task_id == task.id,
                TaskEvent.kind.in_(
                    [TaskEventKind.STAGE_COMPLETED.value, TaskEventKind.COMPLETED_MANUALLY.value]
                ),
            )
            .order_by(TaskEvent.seq.desc())
            .limit(1)
        )
        or ""
    )


def _stats(repo: Repo, base: str, branch: str) -> str:
    return (repo.attempt("diff", "--shortstat", f"{base}...{branch}") or "").strip()


def description(db: Session, task: Task, member: integration.RepoCheck, repo: Repo) -> str:
    parts = [_summary(db, task).strip()]
    stats = _stats(repo, member.base or "", member.branch)
    if stats:
        parts.append(f"**Cambios:** {stats}")
    parts.append(f"Tarea de Agentic OS: {task.code} · {task.title}")
    return "\n\n".join(p for p in parts if p)


def create_for_task(
    db: Session, task: Task, project: Project, *, draft: bool = False, push: bool = True
) -> list[RepoPull]:
    """Pushes each branch and opens a pull request into its base. With several repositories the
    descriptions link to each other. A repository that fails does not stop the others."""
    checked = integration.check(db, task, project)
    results: list[RepoPull] = []
    made: list[tuple[RepoPull, int]] = []
    forges = {}
    for item in checked.repos:
        out = RepoPull(repo_id=item.repo_id, name=item.name, status="nothing")
        results.append(out)
        if item.ahead == 0 or not item.base or item.state in ("missing", "integrated"):
            continue
        row = next(
            m.repo for m in integration.members(db, task, project) if m.repo.id == item.repo_id
        )
        repo = Repo(row.path)
        try:
            forge = forge_for(row, repo, interactive=True)
            if push:
                name = remote.default_remote(repo, item.branch)
                repo.run("push", "-u", name, item.branch, timeout=300, interactive=True)
            body = description(db, task, item, repo)
            if made:
                body += "\n\nRelacionados: " + ", ".join(
                    f"{r.name}: {r.pull.url}" for r, _ in made if r.pull
                )
            pull = forge.create(
                NewPull(
                    title=f"{task.code}: {task.title}",
                    body=body,
                    head=item.branch,
                    base=item.base,
                    draft=draft,
                )
            )
        except GitxError as error:
            out.status, out.error_code, out.message = "failed", error.code, error.message
            continue
        out.status, out.pull = "created", pull
        forges[item.repo_id] = (forge, body)
        made.append((out, pull.number))
    if len(made) > 1:  # the first ones could not link to the later ones yet
        links = "\n\nRelacionados: " + ", ".join(
            f"{r.name}: {r.pull.url}" for r, _ in made if r.pull
        )
        for out, number in made[:-1]:
            forge, body = forges[out.repo_id]
            if "Relacionados:" not in body:
                with contextlib.suppress(GitxError):  # only the cross-link would be missing
                    forge.describe(number, body + links)
    if made:
        names = ", ".join(r.name for r, _ in made)
        task_ops.add_event(db, task, TaskEventKind.INTEGRATED, f"pull request: {names}")
    return results
