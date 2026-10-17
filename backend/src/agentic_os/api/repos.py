"""The git repositories of a project (phase 12, ADR 0016)."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.api.projects import get_project_or_404
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import ProjectRepo, TaskRepo
from agentic_os.schemas.repo import RepoLink, RepoRead, RepoUpdate
from agentic_os.services import git, repos

router = APIRouter(tags=["repos"])
DbSession = Annotated[Session, Depends(get_session)]


def get_repo_or_404(session: Session, repo_id: str) -> ProjectRepo:
    repo = session.get(ProjectRepo, repo_id)
    if repo is None or repo.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("repo")
    return repo


def _read(repo: ProjectRepo) -> RepoRead:
    result = RepoRead.model_validate(repo)
    if not repo.missing and Path(repo.path).is_dir():
        result.git = git.detect(repo.path)
    return result


def read_many(items: list[ProjectRepo]) -> list[RepoRead]:
    """Git state is computed with subprocesses: detect the repositories in parallel."""
    if len(items) <= 1:
        return [_read(r) for r in items]
    with ThreadPoolExecutor(max_workers=min(8, len(items))) as pool:
        return list(pool.map(_read, items))


@router.get("/projects/{project_id}/repos")
def list_repos(project_id: str, session: DbSession) -> list[RepoRead]:
    project = get_project_or_404(session, project_id)
    found = repos.ensure(session, project)
    session.commit()
    return read_many(found)


@router.post("/projects/{project_id}/repos/scan")
def scan_repos(project_id: str, session: DbSession) -> list[RepoRead]:
    """«Volver a buscar»: looks for repositories again and refreshes the list."""
    project = get_project_or_404(session, project_id)
    found = repos.sync(session, project)
    session.commit()
    return read_many(found)


@router.post("/projects/{project_id}/repos", status_code=status.HTTP_201_CREATED)
def link_repo(project_id: str, payload: RepoLink, session: DbSession) -> RepoRead:
    project = get_project_or_404(session, project_id)
    repos.ensure(session, project)
    repo = repos.link(session, project, payload.path, payload.name)
    session.commit()
    return _read(repo)


@router.patch("/repos/{repo_id}")
def update_repo(repo_id: str, payload: RepoUpdate, session: DbSession) -> RepoRead:
    repo = get_repo_or_404(session, repo_id)
    changes = payload.model_dump(exclude_unset=True)
    if any(value is None for key, value in changes.items() if key != "forge"):
        raise ApiError(422, "null_not_allowed", "null is not a valid value", "body")
    if "base_branch" in changes and not git.branch_exists(repo.path, changes["base_branch"]):
        raise ApiError(422, "unknown_branch", "the base branch does not exist", "base_branch")
    for field, value in changes.items():
        setattr(repo, field, value)
    session.commit()
    return _read(repo)


@router.delete("/repos/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_repo(repo_id: str, session: DbSession) -> None:
    """Takes the repository off the project's list. The folder on disk is never touched. Not
    while a task still has a worktree in it."""
    repo = get_repo_or_404(session, repo_id)
    busy = session.scalar(
        select(TaskRepo.id).where(TaskRepo.repo_id == repo.id, TaskRepo.worktree_path.is_not(None))
    )
    if busy:
        raise ApiError(409, "repo_busy", "a task has a worktree in this repository", "id")
    session.delete(repo)
    session.commit()
