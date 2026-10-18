"""GitHub (REST v3), github.com or an Enterprise host."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import httpx

from agentic_os.services.forges.base import (
    Check,
    CheckState,
    Comment,
    Kind,
    MergeMethod,
    NewPull,
    PullDetail,
    PullRequest,
    Review,
    State,
    worst,
)
from agentic_os.services.forges.http import Api


def api_base(host: str) -> str:
    return "https://api.github.com" if host == "github.com" else f"https://{host}/api/v3"


def _when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _pull(data: dict[str, Any]) -> PullRequest:
    state: State = "merged" if data.get("merged_at") else data["state"]
    return PullRequest(
        number=data["number"],
        title=data["title"],
        state=state,
        draft=bool(data.get("draft")),
        author=(data.get("user") or {}).get("login", ""),
        head=data["head"]["ref"],
        base=data["base"]["ref"],
        url=data["html_url"],
        created_at=_when(data.get("created_at")),
        updated_at=_when(data.get("updated_at")),
        mergeable=data.get("mergeable"),
    )


def _check(run: dict[str, Any]) -> Check:
    state: CheckState
    if run.get("status") != "completed":
        state = "pending"
    elif run.get("conclusion") == "success":
        state = "success"
    elif run.get("conclusion") in ("neutral", "skipped"):
        state = "neutral"
    else:
        state = "failure"
    return Check(name=run["name"], state=state, url=run.get("html_url") or "")


class GitHub:
    kind: Kind = "github"

    def __init__(self, client: httpx.Client, host: str, path: str, token: str) -> None:
        self.host = host
        self._api = Api(client, api_base(host), token)
        self._repo = f"/repos/{path}"

    def list(self, state: Literal["open", "closed", "all"] = "open") -> list[PullRequest]:
        data = self._api.get(f"{self._repo}/pulls", state=state, per_page=50)
        return [_pull(item) for item in data]

    def get(self, number: int) -> PullDetail:
        data = self._api.get(f"{self._repo}/pulls/{number}")
        runs = self._api.get(f"{self._repo}/commits/{data['head']['sha']}/check-runs", per_page=100)
        checks = [_check(run) for run in runs.get("check_runs", [])]
        reviews = [
            Review(
                author=(r.get("user") or {}).get("login", ""),
                state=str(r.get("state", "")).lower(),
            )
            for r in self._api.get(f"{self._repo}/pulls/{number}/reviews", per_page=100)
        ]
        comments = [
            Comment(
                author=(c.get("user") or {}).get("login", ""),
                body=c.get("body") or "",
                created_at=_when(c.get("created_at")),
            )
            for c in self._api.get(f"{self._repo}/issues/{number}/comments", per_page=100)
        ]
        return PullDetail(
            **_pull(data).model_dump(),
            body=data.get("body") or "",
            checks=checks,
            checks_state=worst(checks),
            reviews=reviews,
            comments=comments,
        )

    def create(self, new: NewPull) -> PullRequest:
        data = self._api.request(
            "POST",
            f"{self._repo}/pulls",
            json={
                "title": new.title,
                "body": new.body,
                "head": new.head,
                "base": new.base,
                "draft": new.draft,
            },
        )
        return _pull(data)

    def merge(self, number: int, method: MergeMethod = "merge") -> None:
        self._api.request(
            "PUT", f"{self._repo}/pulls/{number}/merge", json={"merge_method": method}
        )

    def describe(self, number: int, body: str) -> None:
        self._api.request("PATCH", f"{self._repo}/pulls/{number}", json={"body": body})

    def close(self, number: int) -> None:
        self._api.request("PATCH", f"{self._repo}/pulls/{number}", json={"state": "closed"})

    def reopen(self, number: int) -> None:
        self._api.request("PATCH", f"{self._repo}/pulls/{number}", json={"state": "open"})

    def update_branch(self, number: int) -> None:
        self._api.request("PUT", f"{self._repo}/pulls/{number}/update-branch", json={})
