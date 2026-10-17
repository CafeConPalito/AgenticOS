"""How the app runs git (phase 12, ADR 0017).

Every command runs with no terminal to ask anything on, and in English, so its failures can be
classified. Writes to one repository go one at a time (its lock is shared by all its worktrees).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import threading
from collections.abc import Iterator, Mapping
from functools import cache
from pathlib import Path

from agentic_os.services import proc
from agentic_os.services.gitx.errors import GitxError, from_output

# Never wait for a person at a prompt: a missing credential or an editor would hang the command
# and, with it, the request. Git Credential Manager may still open its own window when the
# person asked for the operation (`interactive`).
BASE_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_SSH_COMMAND": "ssh -o BatchMode=yes",
    "GIT_EDITOR": "true",
    "GIT_PAGER": "cat",
    "LC_ALL": "C",
    "LANG": "C",
}
# `core.quotepath=false`: non-ASCII file names come out as they are.
BASE_CONFIG = ("core.quotepath=false", "core.editor=true")
TIMEOUT = 60


@cache
def executable() -> str:
    found = shutil.which("git")
    if found is None:
        raise GitxError("git_missing", "git is not installed", status=503)
    return found


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _common_dir(path: str) -> str:
    """The repository's shared git dir, the same for it and all its worktrees."""
    try:
        out = proc.run(
            [executable(), "-C", path, "rev-parse", "--git-common-dir"], 10, env=_env(False)
        )
    except (OSError, subprocess.TimeoutExpired):
        return path
    if out.returncode != 0:
        return path
    raw = out.stdout.strip()
    folder = Path(raw) if Path(raw).is_absolute() else Path(path) / raw
    return os.path.normcase(str(folder.resolve()))


def _env(interactive: bool, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = {**os.environ, **BASE_ENV, "GCM_INTERACTIVE": "auto" if interactive else "never"}
    if extra:
        env.update(extra)
    return env


class Repo:
    """One repository, or one of its worktrees, to run git in."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._key: str | None = None

    @property
    def key(self) -> str:
        if self._key is None:
            self._key = _common_dir(self.path)
        return self._key

    @contextlib.contextmanager
    def write(self) -> Iterator[None]:
        """Exclusive use of the repository for a command that changes it."""
        with _LOCKS_GUARD:
            lock = _LOCKS.setdefault(self.key, threading.RLock())
        with lock:
            yield

    def command(self, *args: str, config: tuple[str, ...] = ()) -> list[str]:
        pairs = [x for item in (*BASE_CONFIG, *config) for x in ("-c", item)]
        return [executable(), *pairs, "-C", self.path, *args]

    def run(
        self,
        *args: str,
        timeout: float = TIMEOUT,
        input: str | None = None,
        env: Mapping[str, str] | None = None,
        config: tuple[str, ...] = (),
        interactive: bool = False,
        ok: tuple[int, ...] = (0,),
        literal: bool = False,
    ) -> str:
        """Runs `git <args>` and returns its stdout. Fails with a classified `GitxError`.
        `ok`: exit codes that are not failures (`diff --no-index` exits 1 when files differ).
        `literal`: paths in `args` are never globs or pathspec magic."""
        extra = dict(env or {})
        if literal:
            extra["GIT_LITERAL_PATHSPECS"] = "1"
        try:
            result = proc.run(
                self.command(*args, config=config),
                timeout,
                env=_env(interactive, extra),
                input=input,
            )
        except subprocess.TimeoutExpired as error:
            raise GitxError("timeout", f"git {args[0]}: timed out after {timeout:.0f}s") from error
        except OSError as error:
            raise GitxError("git_missing", str(error), status=503) from error
        if result.returncode not in ok:
            raise from_output(args, result.returncode, result.stdout, result.stderr)
        return result.stdout

    def run_raw(
        self,
        *args: str,
        input: bytes | None = None,
        timeout: float = TIMEOUT,
        literal: bool = False,
        ok: tuple[int, ...] = (0,),
    ) -> bytes:
        """Like `run`, but bytes in and out: patches must keep their line endings, which the
        text mode of `subprocess` would translate."""
        extra = {"GIT_LITERAL_PATHSPECS": "1"} if literal else None
        try:
            result = subprocess.run(
                self.command(*args),
                capture_output=True,
                input=input,
                timeout=timeout,
                env=_env(False, extra),
                stdin=None if input is not None else subprocess.DEVNULL,
                creationflags=proc.NO_WINDOW,
            )
        except subprocess.TimeoutExpired as error:
            raise GitxError("timeout", f"git {args[0]}: timed out after {timeout:.0f}s") from error
        except OSError as error:
            raise GitxError("git_missing", str(error), status=503) from error
        if result.returncode not in ok:
            stdout = result.stdout.decode("utf-8", "replace")
            raise from_output(
                args, result.returncode, stdout, result.stderr.decode("utf-8", "replace")
            )
        return result.stdout

    def attempt(self, *args: str, **kwargs) -> str | None:
        """Like `run`, but None instead of an error (for questions: does this ref exist?)."""
        try:
            return self.run(*args, **kwargs)
        except GitxError:
            return None
