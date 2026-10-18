"""Tags (phase 12, ADR 0017). Pushing and deleting them on a remote are network jobs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

SEP = "\x1f"
END = "\x1e"


class TagInfo(BaseModel):
    name: str
    sha: str  # the commit it points at
    annotated: bool
    message: str = ""
    date: datetime | None = None


def tags(repo: Repo) -> list[TagInfo]:
    fields = [
        "%(refname:short)",
        "%(objecttype)",
        "%(objectname)",
        "%(*objectname)",
        "%(contents:subject)",
        "%(creatordate:iso-strict)",
    ]
    out = repo.run(
        "for-each-ref", "--sort=-creatordate", f"--format={SEP.join(fields)}{END}", "refs/tags"
    )
    found = []
    for record in (r for r in out.split(END) if r.strip()):
        name, kind, own, target, subject, date = record.strip("\n").split(SEP)
        annotated = kind == "tag"
        found.append(
            TagInfo(
                name=name,
                sha=target if annotated else own,
                annotated=annotated,
                message=subject if annotated else "",
                date=datetime.fromisoformat(date) if date else None,
            )
        )
    return found


def create(repo: Repo, name: str, ref: str | None = None, message: str | None = None) -> None:
    """A lightweight tag, or an annotated one when there is a message."""
    clean = name.strip()
    if not clean or repo.attempt("check-ref-format", f"refs/tags/{clean}") is None:
        raise GitxError("invalid_ref", f"{name!r} is not a valid tag name", status=422)
    args = ["tag"]
    if message and message.strip():
        args += ["-a", clean, "-m", message.strip()]
    else:
        args.append(clean)
    if ref:
        args.append(ref)
    with repo.write():
        try:
            repo.run(*args)
        except GitxError as error:
            if "already exists" in error.output:
                raise GitxError("tag_exists", f"the tag {clean} already exists") from error
            raise


def delete(repo: Repo, name: str) -> None:
    with repo.write():
        repo.run("tag", "-d", name)


def push_args(remote: str, name: str) -> list[str]:
    return ["push", "--progress", remote, f"refs/tags/{name}"]


def delete_remote_args(remote: str, name: str) -> list[str]:
    return ["push", "--progress", remote, f":refs/tags/{name}"]
