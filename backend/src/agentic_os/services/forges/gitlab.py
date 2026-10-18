"""GitLab (REST v4), gitlab.com or a self-managed host. Pull requests are merge requests."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

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

STATES = {"open": "opened", "closed": "closed", "all": "all"}
FROM_GITLAB: dict[str, State] = {
    "opened": "open",
    "closed": "closed",
    "locked": "closed",
    "merged": "merged",
}
PIPELINE: dict[str, CheckState] = {
    "success": "success",
    "failed": "failure",
    "canceled": "failure",
    "skipped": "neutral",
    "manual": "neutral",
}


def _when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _pull(data: dict[str, Any]) -> PullRequest:
    status = data.get("detailed_merge_status", "")
    mergeable = {"mergeable": True, "can_be_merged": True, "cannot_be_merged": False}.get(status)
    return PullRequest(
        number=data["iid"],
        title=data["title"].removeprefix("Draft: "),
        state=FROM_GITLAB.get(data["state"], "open"),
        draft=bool(data.get("draft") or data.get("work_in_progress")),
        author=(data.get("author") or {}).get("username", ""),
        head=data["source_branch"],
        base=data["target_branch"],
        url=data["web_url"],
        created_at=_when(data.get("created_at")),
        updated_at=_when(data.get("updated_at")),
        mergeable=mergeable,
    )


class GitLab:
    kind: Kind = "gitlab"

    def __init__(self, client: httpx.Client, host: str, path: str, token: str) -> None:
        self.host = host
        self._api = Api(client, f"https://{host}/api/v4", token)
        self._project = f"/projects/{quote(path, safe='')}/merge_requests"

    def list(self, state: Literal["open", "closed", "all"] = "open") -> list[PullRequest]:
        data = self._api.get(self._project, state=STATES[state], per_page=50)
        return [_pull(item) for item in data]

    def get(self, number: int) -> PullDetail:
        data = self._api.get(f"{self._project}/{number}")
        pipeline = data.get("head_pipeline") or {}
        checks = (
            [
                Check(
                    name="pipeline",
                    state=PIPELINE.get(pipeline.get("status", ""), "pending"),
                    url=pipeline.get("web_url") or "",
                )
            ]
            if pipeline
            else []
        )
        approvals = self._api.get(f"{self._project}/{number}/approvals")
        reviews = [
            Review(author=(a.get("user") or {}).get("username", ""), state="approved")
            for a in approvals.get("approved_by", [])
        ]
        notes = self._api.get(f"{self._project}/{number}/notes", per_page=100)
        comments = [
            Comment(
                author=(n.get("author") or {}).get("username", ""),
                body=n.get("body") or "",
                created_at=_when(n.get("created_at")),
            )
            for n in notes
            if not n.get("system")
        ]
        return PullDetail(
            **_pull(data).model_dump(),
            body=data.get("description") or "",
            checks=checks,
            checks_state=worst(checks),
            reviews=reviews,
            comments=comments,
        )

    def create(self, new: NewPull) -> PullRequest:
        data = self._api.request(
            "POST",
            self._project,
            json={
                "source_branch": new.head,
                "target_branch": new.base,
                "title": f"Draft: {new.title}" if new.draft else new.title,
                "description": new.body,
            },
        )
        return _pull(data)

    def merge(self, number: int, method: MergeMethod = "merge") -> None:
        if method == "rebase":  # GitLab rebases as its own step, then merges
            self.update_branch(number)
        self._api.request(
            "PUT", f"{self._project}/{number}/merge", json={"squash": method == "squash"}
        )

    def describe(self, number: int, body: str) -> None:
        self._api.request("PUT", f"{self._project}/{number}", json={"description": body})

    def close(self, number: int) -> None:
        self._api.request("PUT", f"{self._project}/{number}", json={"state_event": "close"})

    def reopen(self, number: int) -> None:
        self._api.request("PUT", f"{self._project}/{number}", json={"state_event": "reopen"})

    def update_branch(self, number: int) -> None:
        self._api.request("PUT", f"{self._project}/{number}/rebase", json={})
