"""git's configuration, for one repository or for the user (phase 12, ADR 0017)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

Scope = Literal["local", "global"]
KEY = re.compile(r"^[A-Za-z][A-Za-z0-9-]*\.([^\s=]+\.)?[A-Za-z][A-Za-z0-9-]*$")

# What the screen edits by name; any other key goes through the generic editor.
COMMON = (
    "user.name",
    "user.email",
    "commit.gpgsign",
    "gpg.format",
    "user.signingkey",
    "init.defaultBranch",
    "pull.rebase",
    "fetch.prune",
)
# Keys whose value is run as a command: the app never sets them.
FORBIDDEN = re.compile(
    r"(^|\.)(editor|pager|sshcommand|askpass|fsmonitor|hookspath|textconv|program|helper|external)$"
    r"|^(alias|include|includeif|url|filter)\.",
    re.I,
)


class ConfigEntry(BaseModel):
    key: str
    value: str
    scope: str
    origin: str = ""


def _check(key: str) -> str:
    clean = key.strip()
    if not KEY.match(clean):
        raise GitxError("invalid_key", f"{key!r} is not a valid setting name", status=422)
    if FORBIDDEN.search(clean):
        raise GitxError(
            "forbidden_key", f"{key} can run commands: set it from a terminal", status=422
        )
    return clean


def entries(repo: Repo | None, scope: Scope) -> list[ConfigEntry]:
    """Every setting of one scope, as `git config --list` shows them."""
    runner = repo or Repo(".")
    args = ["config", f"--{scope}", "--list", "--show-origin", "--null"]
    try:
        out = runner.run(*args)
    except GitxError:  # no such file yet (no global config)
        return []
    found = []
    for record in out.split("\0\0") if False else _records(out):
        origin, key, value = record
        found.append(ConfigEntry(key=key, value=value, scope=scope, origin=origin))
    return found


def _records(out: str) -> list[tuple[str, str, str]]:
    """`--null --show-origin` prints `origin NUL key \\n value NUL`."""
    parts = out.split("\0")
    records = []
    for index in range(0, len(parts) - 1, 2):
        origin, pair = parts[index], parts[index + 1]
        key, _, value = pair.partition("\n")
        records.append((origin, key, value))
    return records


def common(repo: Repo | None) -> dict[str, dict[str, str | None]]:
    """The usual settings with the value each scope gives them (None: not set there)."""
    result: dict[str, dict[str, str | None]] = {}
    for key in COMMON:
        row: dict[str, str | None] = {}
        for scope in ("global", "local"):
            if scope == "local" and repo is None:
                continue
            runner = repo or Repo(".")
            value = runner.attempt("config", f"--{scope}", "--get", key)
            row[scope] = value.strip() if value is not None else None
        result[key] = row
    return result


def set_value(repo: Repo | None, scope: Scope, key: str, value: str | None) -> None:
    """Sets (or, with None, unsets) one setting. `local` needs a repository."""
    clean = _check(key)
    if scope == "local" and repo is None:
        raise GitxError("no_repo", "a repository is needed for a local setting", status=422)
    runner = repo or Repo(".")
    with runner.write() if repo else _nothing():
        if value is None:
            runner.run("config", f"--{scope}", "--unset-all", clean, ok=(0, 5))
        else:
            if "\0" in value:
                raise GitxError("invalid_value", "that value is not valid", status=422)
            runner.run("config", f"--{scope}", clean, value)


class _nothing:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: object) -> None:
        return None
