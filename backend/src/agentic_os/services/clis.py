"""Catalog of the agent CLIs Agentic OS can drive: installation, version, models and whether
a session is logged in (phase 08).

Probing runs the CLIs as subprocesses, which is slow (agy needs a few seconds to list models),
so results are cached for a while; callers can force a refresh.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel

from agentic_os.db.base import utcnow
from agentic_os.models.agent import Cli
from agentic_os.services import cli_paths, proc

CACHE_TTL = 600.0
VERSION_TIMEOUT = 15
AUTH_TIMEOUT = 20
MODELS_TIMEOUT = 45


class ModelOption(BaseModel):
    id: str
    # Label given by the CLI itself; None for well-known aliases the UI names (i18n).
    label: str | None = None


class CliInfo(BaseModel):
    id: Cli
    name: str
    installed: bool
    path: str | None = None
    version: str | None = None
    models: list[ModelOption] = []
    models_error: str | None = None
    # True / False when the CLI says so; None when it cannot be told (not installed, error).
    logged_in: bool | None = None
    checked_at: datetime | None = None


Runner = Callable[[list[str], int], subprocess.CompletedProcess[str]]


def run_command(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return proc.run(argv, timeout)


def _claude_models(_path: str, _run: Runner) -> list[ModelOption]:
    # Claude Code accepts stable aliases that always point to the latest model of each tier.
    return [
        ModelOption(id="sonnet"),
        ModelOption(id="opus"),
        ModelOption(id="haiku"),
    ]


def _agy_models(path: str, run: Runner) -> list[ModelOption]:
    result = run([path, "models"], MODELS_TIMEOUT)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip()[:200] or "agy models failed")
    models = []
    for line in result.stdout.splitlines():
        if "\t" in line:
            model_id, label = line.split("\t", 1)
            models.append(ModelOption(id=model_id.strip(), label=label.strip()))
    if not models:
        raise RuntimeError("agy returned no models (is the session logged in?)")
    return models


def _claude_logged_in(path: str, run: Runner, info: CliInfo) -> bool | None:
    """`claude auth status` prints JSON with `loggedIn` (Claude Code 2.1)."""
    try:
        result = run([path, "auth", "status"], AUTH_TIMEOUT)
        data = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    logged_in = data.get("loggedIn") if isinstance(data, dict) else None
    return logged_in if isinstance(logged_in, bool) else None


def _agy_logged_in(path: str, run: Runner, info: CliInfo) -> bool | None:
    """agy has no status command: without a session it cannot list its models."""
    return info.models_error is None


@dataclass(frozen=True)
class CliSpec:
    id: Cli
    name: str
    executable: str
    list_models: Callable[[str, Runner], list[ModelOption]]
    logged_in: Callable[[str, Runner, CliInfo], bool | None]


SPECS = [
    CliSpec(Cli.CLAUDE, "Claude Code", "claude", _claude_models, _claude_logged_in),
    CliSpec(Cli.AGY, "Antigravity CLI", "agy", _agy_models, _agy_logged_in),
]


@dataclass
class CliCatalog:
    which: Callable[[str], str | None] = cli_paths.which
    run: Runner = run_command
    ttl: float = CACHE_TTL
    _cache: list[CliInfo] | None = None
    _cached_at: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def probe(self, spec: CliSpec) -> CliInfo:
        path = self.which(spec.executable)
        if not path:
            return CliInfo(id=spec.id, name=spec.name, installed=False, checked_at=utcnow())
        info = CliInfo(id=spec.id, name=spec.name, installed=True, path=path, checked_at=utcnow())
        try:
            info.version = parse_version(self.run([path, "--version"], VERSION_TIMEOUT))
        except (OSError, subprocess.TimeoutExpired):
            info.version = None
        try:
            info.models = spec.list_models(path, self.run)
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as error:
            info.models_error = str(error) or type(error).__name__
        info.logged_in = spec.logged_in(path, self.run, info)
        return info

    def cached_version(self, cli: str) -> str | None:
        """The version of a CLI if it was already probed (never probes: that takes seconds)."""
        for info in self._cache or []:
            if info.id == cli:
                return info.version
        return None

    def list(self, refresh: bool = False) -> list[CliInfo]:
        # The lock makes concurrent callers share one probe instead of starting their own;
        # inside it, the CLIs are probed in parallel (each can take tens of seconds).
        with self._lock:
            fresh = self._cache is not None and time.monotonic() - self._cached_at < self.ttl
            if refresh or not fresh:
                with ThreadPoolExecutor(max_workers=len(SPECS)) as pool:
                    self._cache = list(pool.map(self.probe, SPECS))
                self._cached_at = time.monotonic()
            return list(self._cache or [])


def parse_version(result: subprocess.CompletedProcess[str]) -> str | None:
    """First non-blank stdout line of a successful `--version`, else None."""
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return lines[0] if lines else None
