"""Describing pictures with AI (phase 14, block 7): optional, off by default.

Two ways, chosen in the settings (or per document):
  - a CLI in headless mode (`claude -p` / `agy -p`), with the account and model chosen: the picture
    goes to that provider and the call spends its quota, so each one is recorded as a `Run` of
    kind «describe» (its tokens and cost count like any other) and the daily limit is respected;
  - a local vision model in `llama.cpp`: nothing leaves the machine.
The description goes into the Markdown under the picture, marked as generated.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import structlog
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    CliAccount,
    KnowledgeDoc,
    Project,
    Run,
    RunKind,
    RunStatus,
    SessionState,
    UsageStatus,
)
from agentic_os.models.agent import Cli
from agentic_os.services import accounts as account_ops
from agentic_os.services.decider import CHEAP_MODEL, Usage
from agentic_os.services.knowledge.config import KnowledgeSettings
from agentic_os.services.localmodels import catalog, selection, store
from agentic_os.services.localmodels.catalog import CatalogEntry
from agentic_os.services.localmodels.llama import LlamaError, LlamaServer
from agentic_os.services.proc import run as run_process
from agentic_os.services.runs.launcher import clean_env, resolve_executable, safe_prompt
from agentic_os.services.usage import limits as usage_limits

log = structlog.get_logger()

CALL_TIMEOUT = 120.0
MAX_BUDGET_USD = "0.10"
MAX_CHARS = 2000
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif"}  # fmt: skip
Runner = Callable[..., subprocess.CompletedProcess[str]]

# Notices a document can carry when it could not be described (it is still ready).
MISSING, BLOCKED, FAILED = "describe_missing", "describe_blocked", "describe_failed"


@dataclass
class Description:
    text: str = ""
    error: str | None = None
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    seconds: float = 0.0


class Describer(Protocol):
    name: str  # who described it, e.g. "claude:haiku" or "local:gemma4-e2b"
    account_id: str | None  # the CLI account that paid for it (None: local)

    def describe(self, image: Path, context: str) -> Description: ...


def prompt_for(name: str, context: str, reads_a_file: bool) -> str:
    how = (
        f"Lee la imagen `{name}` de esta carpeta con tu herramienta de lectura y descríbela"
        if reads_a_file
        else "Describe esta imagen"
    )
    return (
        f"{how} en español de forma breve y precisa (máximo 4 frases). Incluye todo el texto, "
        f"los números y los datos que aparezcan. La imagen es de {context}. "
        "Responde solo con la descripción."
    )


def _loads(text: str) -> dict | None:
    try:
        value = json.loads(text.strip().splitlines()[-1] if text.strip() else "")
    except (ValueError, IndexError):
        try:
            value = json.loads(text)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


# ----------------------------------------------------------------------------- the CLI
def parse_claude(stdout: str, model: str) -> Description:
    data = _loads(stdout)
    if data is None:
        return Description(error="Claude Code no devolvió JSON")
    usage = data.get("usage") or {}
    result = Description(
        usage=Usage(
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
            cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
            cost_usd=data.get("total_cost_usd"),
        ),
        model=next(iter(data.get("modelUsage") or {}), model),
    )
    if data.get("is_error"):
        result.error = str(data.get("result") or "Claude Code devolvió un error")[:300]
    else:
        result.text = str(data.get("result") or "").strip()[:MAX_CHARS]
    return result


def parse_agy(stdout: str, model: str) -> Description:
    data = _loads(stdout)
    if data is None:
        return Description(error="agy no devolvió JSON")
    inner = data.get("result") if isinstance(data.get("result"), dict) else data
    usage = inner.get("usage") or {}
    result = Description(
        usage=Usage(
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            thinking_tokens=int(usage.get("thinking_tokens") or 0),
            cache_read_tokens=int(usage.get("cache_read_tokens") or 0),
        ),
        model=model,
    )
    if inner.get("status") not in (None, "SUCCESS"):
        result.error = f"agy terminó con {inner.get('status')}"
    else:
        result.text = str(inner.get("response") or "").strip()[:MAX_CHARS]
    return result


@dataclass(frozen=True)
class CliConfig:
    cli: Cli
    account: CliAccount
    model: str
    prefix: tuple[str, ...]


class CliDescriber:
    account_id: str | None

    def __init__(
        self, config: CliConfig, env: Mapping[str, str], runner: Runner = run_process
    ) -> None:
        self.config = config
        self.env = env
        self._runner = runner
        self.name = f"{config.cli}:{config.model}"
        self.account_id = config.account.id

    def argv(self, prompt: str) -> list[str]:
        c = self.config
        if c.cli == Cli.CLAUDE:
            return [
                *c.prefix, "-p", prompt, "--model", c.model, "--output-format", "json",
                "--tools", "Read", "--allowedTools", "Read", "--strict-mcp-config",
                "--no-session-persistence", "--max-budget-usd", MAX_BUDGET_USD,
            ]  # fmt: skip
        return [*c.prefix, "-p", prompt, "--model", c.model, "--output-format", "json"]

    def describe(self, image: Path, context: str) -> Description:
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="agentic-describe-") as folder:
                name = "imagen" + image.suffix.lower()
                shutil.copyfile(image, Path(folder) / name)
                prompt = safe_prompt(prompt_for(name, context, reads_a_file=True))
                proc = self._runner(self.argv(prompt), CALL_TIMEOUT, cwd=folder, env=self.env)
        except subprocess.TimeoutExpired:
            return Description(error=f"el CLI tardó más de {int(CALL_TIMEOUT)} s")
        except OSError as error:
            return Description(error=f"no se pudo lanzar el CLI: {error}")
        parse = parse_claude if self.config.cli == Cli.CLAUDE else parse_agy
        result = parse(proc.stdout or "", self.config.model)
        if proc.returncode and not result.text and not (proc.stdout or "").strip():
            result.error = (proc.stderr or "").strip()[
                :300
            ] or f"el CLI terminó con {proc.returncode}"
        if result.error is None and not result.text:
            result.error = "el CLI no describió la imagen"
        result.seconds = time.monotonic() - started
        return result


def resolve_cli(
    db: Session, limits: KnowledgeSettings, overrides: Mapping[str, list[str]] | None = None
) -> CliConfig | str:
    """The CLI, account and model to describe with; or why none can be used (like the decider)."""
    wanted = [Cli(limits.describer_cli)] if limits.describer_cli else [Cli.CLAUDE, Cli.AGY]
    problems: list[str] = []
    for cli in wanted:
        try:
            prefix = resolve_executable(cli, overrides)
        except ApiError:
            problems.append(f"{cli} no está instalado")
            continue
        account = db.get(CliAccount, limits.describer_account) if limits.describer_account else None
        if account is None or account.cli != cli:
            account = account_ops.default_for(db, cli)
        gate = usage_limits.blocked(db, account)
        if gate is not None or account.session_state == SessionState.DOWN:
            name = account_ops.display_name(account)
            problems.append(f"la cuenta {name} no está disponible ({gate or 'sesión'})")
            continue
        return CliConfig(cli, account, limits.describer_model or CHEAP_MODEL[cli], tuple(prefix))
    return "; ".join(problems) or "no hay ningún CLI para describir"


def record_run(db: Session, doc: KnowledgeDoc, describer: Describer, result: Description) -> None:
    """The call as a run of kind «describe»: its usage is the project's and the account's, so it
    counts in the consumption panels and the daily limit."""
    if describer.account_id is None:  # a local model costs nothing
        return
    account = db.get(CliAccount, describer.account_id)
    project = db.get(Project, doc.project_id) if doc.project_id else None
    now = utcnow()
    usage = result.usage
    db.add(
        Run(
            workspace_id=project.workspace_id if project else DEFAULT_WORKSPACE,
            kind=RunKind.DESCRIBE,
            agent_id=None,
            project_id=project.id if project else None,
            agent_name="Describir imágenes",
            agent_color="#8a8f98",
            project_name=project.name if project else "",
            cli=str(describer.name.split(":")[0]),
            model=result.model,
            prompt=f"Describir una imagen de «{doc.title}»",
            cwd="",
            status=RunStatus.COMPLETED if result.error is None else RunStatus.FAILED,
            error=result.error,
            started_at=now,
            ended_at=now,
            summary=result.text[:200],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            thinking_tokens=usage.thinking_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_creation_tokens=usage.cache_creation_tokens,
            cost_usd=usage.cost_usd,
            usage_source="describe",
            usage_status=UsageStatus.FINAL,
            account_id=account.id if account else None,
            account_label=account_ops.display_name(account) if account else "",
        )
    )


# --------------------------------------------------------------------------- local model
class LlamaDescriber:
    account_id = None

    def __init__(self, server: LlamaServer) -> None:
        self.server = server
        self.name = f"local:{server.vision.id}"

    def describe(self, image: Path, context: str) -> Description:
        started = time.monotonic()
        mime = MIME.get(image.suffix.lower(), "image/png")
        encoded = base64.b64encode(image.read_bytes()).decode()
        content = [
            {"type": "text", "text": prompt_for(image.name, context, reads_a_file=False)},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
        ]
        try:
            answer = self.server.chat([{"role": "user", "content": content}])
        except LlamaError as error:
            return Description(error=error.message, model=self.name)
        usage = answer.get("usage") or {}
        choices = answer.get("choices") or [{}]
        text = str((choices[0].get("message") or {}).get("content") or "").strip()[:MAX_CHARS]
        return Description(
            text=text,
            error=None if text else "el modelo no describió la imagen",
            usage=Usage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            ),
            model=self.name,
            seconds=time.monotonic() - started,
        )


# ----------------------------------------------------------------------------- choosing
Factory = Callable[[Session, KnowledgeSettings], tuple["Describer | None", "str | None"]]


def default_factory(
    data_dir: Path,
    overrides: Mapping[str, list[str]] | None,
    server_for: Callable[[CatalogEntry, CatalogEntry, int], LlamaServer],
) -> Factory:
    """The factory the pipeline uses: it picks the describer the settings ask for, or says why
    there is none (the notice the document will carry)."""

    def make(db: Session, limits: KnowledgeSettings) -> tuple[Describer | None, str | None]:
        if limits.describer == "local":
            vision = selection.active(db, data_dir, catalog.VISION)
            engine = catalog.entry("llama-cpp")
            if vision is None or engine is None:
                return None, MISSING
            if not store.is_installed(data_dir, engine):
                return None, MISSING
            threads = limits.threads or max(1, (os.cpu_count() or 2) // 2)
            return LlamaDescriber(server_for(engine, vision, threads)), None
        config = resolve_cli(db, limits, overrides)
        if isinstance(config, str):
            log.info("knowledge_describe_unavailable", reason=config)
            return None, BLOCKED
        return CliDescriber(config, {**clean_env(), **account_ops.env_for(config.account)}), None

    return make
