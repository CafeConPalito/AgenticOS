"""What every code host (GitHub, GitLab) offers about pull requests, in one shape."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

State = Literal["open", "closed", "merged"]
CheckState = Literal["success", "failure", "pending", "neutral"]
MergeMethod = Literal["merge", "squash", "rebase"]
Kind = Literal["github", "gitlab"]


class PullRequest(BaseModel):
    number: int
    title: str
    state: State
    draft: bool = False
    author: str = ""
    head: str  # the source branch
    base: str  # the target branch
    url: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # None: the host has not worked it out yet.
    mergeable: bool | None = None


class Check(BaseModel):
    name: str
    state: CheckState
    url: str = ""


class Review(BaseModel):
    author: str
    # approved | changes_requested | commented
    state: str


class Comment(BaseModel):
    author: str
    body: str
    created_at: datetime | None = None


class PullDetail(PullRequest):
    body: str = ""
    checks: list[Check] = Field(default_factory=list)
    # The worst of the checks: failure, else pending, else success (None: there are none).
    checks_state: CheckState | None = None
    reviews: list[Review] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)


class NewPull(BaseModel):
    title: str
    body: str = ""
    head: str
    base: str
    draft: bool = False


def worst(checks: list[Check]) -> CheckState | None:
    states = {c.state for c in checks}
    for state in ("failure", "pending", "success"):
        if state in states:
            return state  # type: ignore[return-value]
    return "neutral" if states else None


class Forge(Protocol):
    kind: Kind
    host: str

    def list(self, state: Literal["open", "closed", "all"] = "open") -> list[PullRequest]: ...

    def get(self, number: int) -> PullDetail: ...

    def create(self, new: NewPull) -> PullRequest: ...

    def merge(self, number: int, method: MergeMethod = "merge") -> None: ...

    def describe(self, number: int, body: str) -> None: ...

    def close(self, number: int) -> None: ...

    def reopen(self, number: int) -> None: ...

    def update_branch(self, number: int) -> None: ...
