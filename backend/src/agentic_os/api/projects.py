import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import Project, Task, TaskStatus, WorkspaceMode
from agentic_os.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from agentic_os.services import git, paths

router = APIRouter(tags=["projects"])
DbSession = Annotated[Session, Depends(get_session)]


def get_project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("project")
    return project


def _read(project: Project) -> ProjectRead:
    result = ProjectRead.model_validate(project)
    result.folder_exists = Path(project.path).is_dir()
    if result.folder_exists:
        result.git = git.detect(project.path)
    return result


def _read_many(projects: list[Project]) -> list[ProjectRead]:
    """Git state is computed with subprocesses: detect the projects in parallel."""
    if len(projects) <= 1:
        return [_read(p) for p in projects]
    with ThreadPoolExecutor(max_workers=min(8, len(projects))) as pool:
        return list(pool.map(_read, projects))


def _commit(session: Session) -> None:
    """The only constraint a valid payload can still violate is the unique folder (two
    requests racing past `_check_unique`): report it as the same 409."""
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ApiError(
            409, "project_exists", "a project already uses this folder", "path"
        ) from error


def _check_unique(session: Session, path_key: str, exclude_id: str | None = None) -> None:
    query = select(Project.id).where(
        Project.workspace_id == DEFAULT_WORKSPACE, Project.path_key == path_key
    )
    if exclude_id:
        query = query.where(Project.id != exclude_id)
    if session.scalar(query):
        raise ApiError(409, "project_exists", "a project already uses this folder", "path")


def _check_worktree(path: str, mode: WorkspaceMode) -> None:
    if mode == WorkspaceMode.WORKTREE:
        info = git.detect(path)
        if not (info and info.is_repo):
            raise ApiError(
                422,
                "worktree_requires_git",
                "worktree mode needs a git repository",
                "workspace_mode",
            )


@router.get("/projects")
def list_projects(session: DbSession) -> list[ProjectRead]:
    query = (
        select(Project)
        .where(Project.workspace_id == DEFAULT_WORKSPACE)
        .order_by(Project.updated_at.desc())
    )
    return _read_many(list(session.scalars(query)))


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, session: DbSession) -> ProjectRead:
    path, key = paths.normalize(payload.path)
    _check_unique(session, key)
    paths.ensure_folder(path, create=payload.create_folder)
    _check_worktree(path, payload.workspace_mode)
    values = payload.model_dump(exclude_unset=True, exclude={"create_folder", "path"})
    project = Project(workspace_id=DEFAULT_WORKSPACE, path=path, path_key=key, **values)
    session.add(project)
    _commit(session)
    return _read(project)


@router.get("/projects/{project_id}")
def get_project(project_id: str, session: DbSession) -> ProjectRead:
    return _read(get_project_or_404(session, project_id))


@router.patch("/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate, session: DbSession) -> ProjectRead:
    project = get_project_or_404(session, project_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("path"):
        path, key = paths.normalize(changes.pop("path"))
        _check_unique(session, key, exclude_id=project.id)
        paths.ensure_folder(path, create=False)
        project.path, project.path_key = path, key
    if changes.get("workspace_mode") or "path" in payload.model_fields_set:
        _check_worktree(project.path, changes.get("workspace_mode") or project.workspace_mode)
    for field, value in changes.items():  # nulls are rejected by the schema
        setattr(project, field, value)
    _commit(session)
    return _read(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, session: DbSession) -> None:
    """Removes the project (and its tasks) from Agentic OS. The folder on disk is never
    touched. Not while one of its tasks is running."""
    project = get_project_or_404(session, project_id)
    running = session.scalar(
        select(Task.id).where(Task.project_id == project.id, Task.status == TaskStatus.RUNNING)
    )
    if running:
        raise ApiError(409, "project_busy", "a task of the project is running", "id")
    session.delete(project)
    session.commit()


def open_in_file_manager(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


@router.post("/projects/{project_id}/open", status_code=status.HTTP_204_NO_CONTENT)
def open_project_folder(project_id: str, session: DbSession) -> None:
    project = get_project_or_404(session, project_id)
    if not Path(project.path).is_dir():
        raise ApiError(422, "folder_not_found", "the folder does not exist", "path")
    open_in_file_manager(project.path)
