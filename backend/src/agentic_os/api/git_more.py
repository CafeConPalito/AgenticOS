"""The rest of the Git tab: stash, tags, remotes, submodules, LFS, worktrees, upkeep, settings,
cloning and a terminal in the repository (phase 12, bloque 4)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, WebSocket, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agentic_os.api.git import _clean_paths, _confirm, _events, _jobs, _open, _tracked
from agentic_os.api.projects import get_project_or_404
from agentic_os.api.terminal import serve_terminal
from agentic_os.db.session import get_session
from agentic_os.schemas.changes import Changes
from agentic_os.schemas.git import JobState
from agentic_os.services import changes as change_ops
from agentic_os.services import repos as repo_ops
from agentic_os.services.gitx import (
    clone,
    lfs,
    merge,
    remote,
    remotes,
    settings,
    stash,
    submodules,
    tags,
    trees,
    upkeep,
)
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

router = APIRouter(tags=["git"])
DbSession = Annotated[Session, Depends(get_session)]
Name = Annotated[str, Query(min_length=1, max_length=200)]


# ----------------------------------------------------------------------------- stash
class StashPush(BaseModel):
    message: str | None = Field(default=None, max_length=1000)
    include_untracked: bool = True


class StashRef(BaseModel):
    ref: str = Field(min_length=1, max_length=100)
    drop: bool = False  # apply: and forget it (pop)
    confirm: bool = False  # drop: a dropped stash cannot be recovered


class StashBranch(BaseModel):
    ref: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)


@router.get("/repos/{repo_id}/stashes")
def list_stashes(repo_id: str, db: DbSession) -> list[stash.StashEntry]:
    return stash.entries(_open(db, repo_id)[1])


@router.post("/repos/{repo_id}/stashes")
def push_stash(repo_id: str, body: StashPush, db: DbSession, request: Request) -> dict[str, bool]:
    row, repo = _open(db, repo_id)
    stored = stash.push(repo, body.message, body.include_untracked)
    _events(request).changed(row.id)
    return {"stored": stored}


@router.post("/repos/{repo_id}/stashes/apply")
def apply_stash(repo_id: str, body: StashRef, db: DbSession, request: Request) -> merge.OpResult:
    row, repo = _open(db, repo_id)
    result = stash.apply(repo, body.ref, body.drop)
    _events(request).changed(row.id)
    return result


@router.post("/repos/{repo_id}/stashes/drop", status_code=status.HTTP_204_NO_CONTENT)
def drop_stash(repo_id: str, body: StashRef, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    _confirm(body.confirm, "a dropped stash cannot be recovered")
    stash.drop(repo, body.ref)
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/stashes/branch", status_code=status.HTTP_204_NO_CONTENT)
def stash_to_branch(repo_id: str, body: StashBranch, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    stash.to_branch(repo, body.ref, body.name)
    _events(request).changed(row.id)


@router.get("/repos/{repo_id}/stashes/diff")
def stash_diff(repo_id: str, db: DbSession, ref: Name) -> Changes:
    row, repo = _open(db, repo_id)
    entry = stash.resolve(repo, ref)
    rng = change_ops.commit_range(repo.path, entry.sha, stash.parent_of(repo, entry))
    rng.key, rng.name = row.id, row.name
    return change_ops.combine([rng])


# ----------------------------------------------------------------------------- tags
class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    ref: str | None = Field(default=None, max_length=200)
    message: str | None = Field(default=None, max_length=10_000)


class TagRemote(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    remote: str | None = Field(default=None, max_length=100)
    delete: bool = False


@router.get("/repos/{repo_id}/tags")
def list_tags(repo_id: str, db: DbSession) -> list[tags.TagInfo]:
    return tags.tags(_open(db, repo_id)[1])


@router.post("/repos/{repo_id}/tags", status_code=status.HTTP_204_NO_CONTENT)
def create_tag(repo_id: str, body: TagCreate, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    tags.create(repo, body.name, body.ref, body.message)
    _events(request).changed(row.id)


@router.delete("/repos/{repo_id}/tags/{name:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(repo_id: str, name: str, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    tags.delete(repo, name)
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/tags/remote", status_code=status.HTTP_202_ACCEPTED)
def tag_on_remote(repo_id: str, body: TagRemote, db: DbSession, request: Request) -> JobState:
    """Publishes a tag on the remote, or (`delete`) removes it from there."""
    row, repo = _open(db, repo_id)
    target = body.remote or remote.default_remote(repo)
    args = (
        tags.delete_remote_args(target, body.name)
        if body.delete
        else tags.push_args(target, body.name)
    )
    return _jobs(request).start(repo, row.id, "push", args)


# ----------------------------------------------------------------------------- remotes
class RemoteAdd(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    url: str = Field(min_length=1, max_length=2000)


class RemoteEdit(BaseModel):
    url: str | None = Field(default=None, max_length=2000)
    rename_to: str | None = Field(default=None, max_length=60)


class ForcePush(BaseModel):
    remote: str | None = None
    branch: str | None = None
    confirm: bool = False


@router.post("/repos/{repo_id}/remotes", status_code=status.HTTP_204_NO_CONTENT)
def add_remote(repo_id: str, body: RemoteAdd, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    remotes.add(repo, body.name, body.url)
    _events(request).changed(row.id)


@router.patch("/repos/{repo_id}/remotes/{name}", status_code=status.HTTP_204_NO_CONTENT)
def edit_remote(repo_id: str, name: str, body: RemoteEdit, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    if body.url:
        remotes.set_url(repo, name, body.url)
    if body.rename_to and body.rename_to != name:
        remotes.rename(repo, name, body.rename_to)
    _events(request).changed(row.id)


@router.delete("/repos/{repo_id}/remotes/{name}", status_code=status.HTTP_204_NO_CONTENT)
def remove_remote(repo_id: str, name: str, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    remotes.remove(repo, name)
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/remotes/{name}/test")
def test_remote(repo_id: str, name: str, db: DbSession) -> remotes.Reachability:
    return remotes.test_connection(_open(db, repo_id)[1], name)


@router.get("/repos/{repo_id}/push/overwrites")
def push_overwrites(
    repo_id: str,
    db: DbSession,
    remote_name: str | None = Query(default=None, alias="remote"),
    branch: str | None = None,
) -> list[str]:
    """What a forced push would destroy on the remote: the commits only it has."""
    _row, repo = _open(db, repo_id)
    name = branch or (repo.attempt("branch", "--show-current") or "").strip()
    return remotes.would_overwrite(repo, remote_name or remote.default_remote(repo, name), name)


@router.post("/repos/{repo_id}/push/force", status_code=status.HTTP_202_ACCEPTED)
def force_push(repo_id: str, body: ForcePush, db: DbSession, request: Request) -> JobState:
    """A push that overwrites the remote's branch, `--force-with-lease`: it refuses if someone
    pushed after the last fetch. Needs `confirm`."""
    row, repo = _open(db, repo_id)
    _confirm(body.confirm, "a forced push overwrites commits on the remote")
    return _jobs(request).start(
        repo, row.id, "push", remotes.force_push_args(repo, body.remote, body.branch)
    )


# ----------------------------------------------------------------------------- submodules
class SubmoduleAdd(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    path: str = Field(min_length=1, max_length=500)


class SubmoduleUse(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    rev: str = Field(min_length=1, max_length=200)


class SubmodulePath(BaseModel):
    path: str | None = Field(default=None, max_length=500)


class SubmoduleRemove(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    confirm: bool = False


@router.get("/repos/{repo_id}/submodules")
def list_submodules(repo_id: str, db: DbSession) -> list[submodules.SubmoduleInfo]:
    return submodules.submodules(_open(db, repo_id)[1])


@router.post("/repos/{repo_id}/submodules/update", status_code=status.HTTP_202_ACCEPTED)
def update_submodules(
    repo_id: str, body: SubmodulePath, db: DbSession, request: Request
) -> JobState:
    row, repo = _open(db, repo_id)
    path = _clean_paths([body.path])[0] if body.path else None
    return _jobs(request).start(repo, row.id, "submodule", submodules.update_args(path))


@router.post("/repos/{repo_id}/submodules", status_code=status.HTTP_204_NO_CONTENT)
def add_submodule(repo_id: str, body: SubmoduleAdd, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    submodules.add(repo, body.url, _clean_paths([body.path])[0])
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/submodules/use", status_code=status.HTTP_204_NO_CONTENT)
def use_submodule_commit(repo_id: str, body: SubmoduleUse, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    submodules.use_commit(repo, _clean_paths([body.path])[0], body.rev)
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/submodules/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_submodule(repo_id: str, body: SubmoduleRemove, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    _confirm(body.confirm, "removing a submodule deletes its folder")
    submodules.remove(repo, _clean_paths([body.path])[0])
    _events(request).changed(row.id)


# ----------------------------------------------------------------------------- LFS
class LfsPattern(BaseModel):
    pattern: str = Field(min_length=1, max_length=500)


@router.get("/repos/{repo_id}/lfs")
def lfs_state(repo_id: str, db: DbSession) -> lfs.LfsState:
    return lfs.state(_open(db, repo_id)[1])


@router.post("/repos/{repo_id}/lfs/track", status_code=status.HTTP_204_NO_CONTENT)
def lfs_track(repo_id: str, body: LfsPattern, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    lfs.track(repo, body.pattern)
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/lfs/untrack", status_code=status.HTTP_204_NO_CONTENT)
def lfs_untrack(repo_id: str, body: LfsPattern, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    lfs.untrack(repo, body.pattern)
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/lfs/pull", status_code=status.HTTP_202_ACCEPTED)
def lfs_pull(repo_id: str, db: DbSession, request: Request) -> JobState:
    row, repo = _open(db, repo_id)
    if not lfs.installed(repo):
        raise GitxError("lfs_missing", "Git LFS is not installed", status=409)
    return _jobs(request).start(repo, row.id, "lfs", lfs.pull_args())


# ----------------------------------------------------------------------------- worktrees
class WorktreeRemove(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    force: bool = False


@router.get("/repos/{repo_id}/worktrees")
def list_worktrees(repo_id: str, db: DbSession) -> list[trees.WorktreeInfo]:
    return trees.worktrees(_open(db, repo_id)[1])


@router.post("/repos/{repo_id}/worktrees/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_worktree(repo_id: str, body: WorktreeRemove, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    trees.remove(repo, body.path, body.force)
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/worktrees/prune", status_code=status.HTTP_204_NO_CONTENT)
def prune_worktrees(repo_id: str, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    trees.prune(repo)
    _events(request).changed(row.id)


# ----------------------------------------------------------------------------- upkeep
class CleanBody(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=5000)
    folders: bool = True
    ignored: bool = False
    confirm: bool = False


@router.get("/repos/{repo_id}/clean/preview")
def clean_preview(
    repo_id: str, db: DbSession, folders: bool = True, ignored: bool = False
) -> upkeep.CleanPreview:
    return upkeep.clean_preview(_open(db, repo_id)[1], folders, ignored)


@router.post("/repos/{repo_id}/clean", status_code=status.HTTP_204_NO_CONTENT)
def clean(repo_id: str, body: CleanBody, db: DbSession, request: Request) -> None:
    """Deletes untracked files. A copy of the work tree is kept (ignored files excepted, which
    cannot be brought back)."""
    row, repo = _open(db, repo_id)
    _confirm(body.confirm, "cleaning deletes files that git does not track")
    paths = _clean_paths(body.paths)
    _tracked(
        db,
        request,
        row,
        repo,
        "clean",
        f"Limpiar {len(paths)} elemento(s)",
        lambda: upkeep.clean(repo, paths, body.folders, body.ignored),
        worktree=True,
    )


@router.post("/repos/{repo_id}/gc", status_code=status.HTTP_202_ACCEPTED)
def gc(repo_id: str, db: DbSession, request: Request) -> JobState:
    row, repo = _open(db, repo_id)
    return _jobs(request).start(repo, row.id, "gc", upkeep.gc_args(), exclusive=True)


@router.get("/repos/{repo_id}/verify")
def verify(repo_id: str, db: DbSession) -> upkeep.Verification:
    return upkeep.verify(_open(db, repo_id)[1])


@router.get("/repos/{repo_id}/size")
def size(repo_id: str, db: DbSession) -> upkeep.Size:
    return upkeep.size(_open(db, repo_id)[1])


# ----------------------------------------------------------------------------- settings
class SettingBody(BaseModel):
    scope: Literal["local", "global"]
    key: str = Field(min_length=3, max_length=200)
    value: str | None = Field(default=None, max_length=10_000)


@router.get("/repos/{repo_id}/config")
def repo_config(repo_id: str, db: DbSession) -> dict[str, dict[str, str | None]]:
    """The usual settings with the value each scope gives them."""
    return settings.common(_open(db, repo_id)[1])


@router.get("/repos/{repo_id}/config/all")
def repo_config_all(
    repo_id: str, db: DbSession, scope: Literal["local", "global"] = "local"
) -> list[settings.ConfigEntry]:
    return settings.entries(_open(db, repo_id)[1], scope)


@router.put("/repos/{repo_id}/config", status_code=status.HTTP_204_NO_CONTENT)
def set_repo_config(repo_id: str, body: SettingBody, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    settings.set_value(repo, body.scope, body.key, body.value)
    _events(request).changed(row.id)


@router.get("/git/config")
def global_config() -> dict[str, dict[str, str | None]]:
    return settings.common(None)


@router.put("/git/config", status_code=status.HTTP_204_NO_CONTENT)
def set_global_config(body: SettingBody) -> None:
    settings.set_value(None, "global", body.key, body.value)


# ----------------------------------------------------------------------------- terminal
class ShellOpened(BaseModel):
    shell_id: str


@router.post("/repos/{repo_id}/shell", status_code=status.HTTP_201_CREATED)
def open_shell(repo_id: str, db: DbSession, request: Request) -> ShellOpened:
    """A terminal in the repository's folder, for what the interface does not cover."""
    row, _repo = _open(db, repo_id)
    return ShellOpened(shell_id=request.app.state.git_shells.open(row.id, row.path))


@router.delete("/git/shells/{shell_id}", status_code=status.HTTP_204_NO_CONTENT)
def close_shell(shell_id: str, request: Request) -> None:
    request.app.state.git_shells.close(shell_id)


@router.websocket("/git/shells/{shell_id}/terminal")
async def shell_terminal(websocket: WebSocket, shell_id: str, client_id: str = "") -> None:
    await websocket.accept()
    session = websocket.app.state.git_shells.get(shell_id)
    if session is None:
        await websocket.send_json({"type": "exit", "code": None, "status": "exited"})
        await websocket.close()
        return
    await serve_terminal(websocket, session, client_id or uuid.uuid4().hex)


# ----------------------------------------------------------------------------- clone, init
class CloneBody(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    parent_folder: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=200)


class CloneStarted(BaseModel):
    job: JobState
    path: str  # the folder being created


class InitBody(BaseModel):
    branch: str = Field(default="main", max_length=200)
    path: str | None = Field(default=None, max_length=2000)


@router.post("/git/clone", status_code=status.HTTP_202_ACCEPTED)
def clone_repository(body: CloneBody, request: Request) -> CloneStarted:
    """Clones into `parent_folder/name`. When the job succeeds the client creates the project or
    adds the repository at `path`."""
    destination = clone.target(body.parent_folder, body.name or clone.folder_name(body.url))
    args = clone.clone_args(body.url, destination)
    job = _jobs(request).start(Repo(str(destination.parent)), "", "clone", args)
    return CloneStarted(job=job, path=str(destination))


@router.post("/projects/{project_id}/repos/init")
def init_repository(
    project_id: str, body: InitBody, db: DbSession, request: Request
) -> dict[str, str]:
    """Makes the project's folder (or a subfolder) a repository and adds it to the list."""
    project = get_project_or_404(db, project_id)
    folder = Path(project.path)
    if body.path:
        relative = _clean_paths([body.path])[0]
        folder = folder / relative
    clone.init(str(folder), body.branch)
    repo_ops.sync(db, project)
    db.commit()
    return {"path": str(folder)}
