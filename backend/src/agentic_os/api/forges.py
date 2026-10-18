"""Pull requests, SSH keys and tokens for the code hosts (phase 12, block 6)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agentic_os.api.git import _open
from agentic_os.api.integration import _project
from agentic_os.api.tasks import _get
from agentic_os.db.session import get_session
from agentic_os.services import pulls
from agentic_os.services.forges import forge_for, remote_of, remoteurl
from agentic_os.services.forges.base import MergeMethod, NewPull, PullDetail, PullRequest
from agentic_os.services.gitx import credentials, remote, ssh

router = APIRouter(tags=["forges"])
DbSession = Annotated[Session, Depends(get_session)]


class PullCreate(NewPull):
    # Push the branch first (a pull request needs it on the remote).
    push: bool = True


class MergeBody(BaseModel):
    method: MergeMethod = "merge"


class TaskPulls(BaseModel):
    draft: bool = False
    push: bool = True


class KeyBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: str = Field(min_length=1, max_length=200)
    passphrase: str = Field(default="", max_length=500)


class ConnectionBody(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    user: str = Field(default="git", max_length=60)


class TokenBody(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    token: str = Field(min_length=1, max_length=2000)


class ForgeInfo(BaseModel):
    kind: str | None
    host: str | None
    remote: str | None
    has_token: bool


# ----------------------------------------------------------------------------- pull requests
@router.get("/repos/{repo_id}/forge")
def forge_info(repo_id: str, db: DbSession) -> ForgeInfo:
    """Which code host the repository's remote is on and whether git has a token for it."""
    row, repo = _open(db, repo_id)
    try:
        name, url = remote_of(repo)
    except Exception:
        return ForgeInfo(kind=None, host=None, remote=None, has_token=False)
    parsed = remoteurl.parse(url)
    if parsed is None:
        return ForgeInfo(kind=None, host=None, remote=name, has_token=False)
    return ForgeInfo(
        kind=remoteurl.kind_of(parsed.host, row.forge),
        host=parsed.host,
        remote=name,
        has_token=credentials.has_token(parsed.host),
    )


@router.get("/repos/{repo_id}/pulls")
def list_pulls(
    repo_id: str, db: DbSession, state: Literal["open", "closed", "all"] = "open"
) -> list[PullRequest]:
    row, repo = _open(db, repo_id)
    return forge_for(row, repo).list(state)


@router.get("/repos/{repo_id}/pulls/{number}")
def get_pull(repo_id: str, number: int, db: DbSession) -> PullDetail:
    row, repo = _open(db, repo_id)
    return forge_for(row, repo).get(number)


@router.post("/repos/{repo_id}/pulls", status_code=status.HTTP_201_CREATED)
def create_pull(repo_id: str, body: PullCreate, db: DbSession, request: Request) -> PullRequest:
    row, repo = _open(db, repo_id)
    forge = forge_for(row, repo, interactive=True)
    if body.push:
        name = remote.default_remote(repo, body.head)
        repo.run("push", "-u", name, body.head, timeout=300, interactive=True)
        request.app.state.git_events.changed(row.id)
    return forge.create(NewPull(**body.model_dump(exclude={"push"})))


@router.post("/repos/{repo_id}/pulls/{number}/merge", status_code=status.HTTP_204_NO_CONTENT)
def merge_pull(repo_id: str, number: int, body: MergeBody, db: DbSession) -> None:
    row, repo = _open(db, repo_id)
    forge_for(row, repo).merge(number, body.method)


@router.post("/repos/{repo_id}/pulls/{number}/close", status_code=status.HTTP_204_NO_CONTENT)
def close_pull(repo_id: str, number: int, db: DbSession) -> None:
    row, repo = _open(db, repo_id)
    forge_for(row, repo).close(number)


@router.post("/repos/{repo_id}/pulls/{number}/reopen", status_code=status.HTTP_204_NO_CONTENT)
def reopen_pull(repo_id: str, number: int, db: DbSession) -> None:
    row, repo = _open(db, repo_id)
    forge_for(row, repo).reopen(number)


@router.post(
    "/repos/{repo_id}/pulls/{number}/update-branch", status_code=status.HTTP_204_NO_CONTENT
)
def update_pull_branch(repo_id: str, number: int, db: DbSession) -> None:
    row, repo = _open(db, repo_id)
    forge_for(row, repo).update_branch(number)


@router.post("/tasks/{task_id}/pulls")
def task_pulls(
    task_id: str, body: TaskPulls, db: DbSession, request: Request
) -> list[pulls.RepoPull]:
    """One pull request per repository where the task left work."""
    task = _get(db, task_id)
    results = pulls.create_for_task(db, task, _project(db, task), draft=body.draft, push=body.push)
    db.commit()
    events = request.app.state.git_events
    for item in results:
        events.changed(item.repo_id)
    return results


# ----------------------------------------------------------------------------- keys and tokens
@router.get("/git/ssh-keys")
def list_keys() -> list[ssh.SshKey]:
    return ssh.keys()


@router.post("/git/ssh-keys", status_code=status.HTTP_201_CREATED)
def generate_key(body: KeyBody) -> ssh.SshKey:
    return ssh.generate(body.name, body.email, body.passphrase)


@router.post("/git/test-connection")
def test_connection(body: ConnectionBody) -> ssh.Connection:
    return ssh.test(body.host, body.user)


@router.get("/git/forge-token")
def token_state(host: Annotated[str, Query(min_length=1, max_length=253)]) -> dict[str, bool]:
    return {"has_token": credentials.has_token(host)}


@router.post("/git/forge-token", status_code=status.HTTP_204_NO_CONTENT)
def save_token(body: TokenBody) -> None:
    """Saves a personal token where git keeps its credentials (the app keeps none)."""
    credentials.store(body.host, body.token)
