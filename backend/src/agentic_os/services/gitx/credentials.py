"""Tokens for the code hosts, kept by git's own credential helper (phase 12, ADR 0018).

The app stores no secret of its own: `git credential fill` returns what Git Credential Manager
(or any helper) already has for the host, and a token the person pastes goes back into the same
store with `git credential approve`.
"""

from __future__ import annotations

import subprocess

from agentic_os.services import proc
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import environment, executable

USERNAME = "x-access-token"


def _git(args: list[str], text: str, interactive: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        return proc.run([executable(), *args], 60, env=environment(interactive), input=text)
    except subprocess.TimeoutExpired as error:
        raise GitxError("timeout", "the credential helper did not answer in time") from error


def token_for(host: str, interactive: bool = False) -> str | None:
    """The token git has for `host`; None when there is none. With `interactive`, Git Credential
    Manager may open its own sign-in window to get one."""
    result = _git(["credential", "fill"], f"protocol=https\nhost={host}\n\n", interactive)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        if key == "password" and value:
            return value
    return None


def store(host: str, token: str) -> None:
    """Saves a personal token where git keeps its credentials."""
    token = token.strip()
    if not token or any(c in token for c in "\r\n\0"):
        raise GitxError("invalid_token", "that is not a valid token", status=422)
    result = _git(
        ["credential", "approve"],
        f"protocol=https\nhost={host}\nusername={USERNAME}\npassword={token}\n\n",
    )
    if result.returncode != 0:
        raise GitxError("git_failed", "git could not store the token", result.stderr)


def has_token(host: str) -> bool:
    return token_for(host) is not None
