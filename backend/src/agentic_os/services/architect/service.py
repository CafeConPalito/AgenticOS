"""Conversations with the Agent Architect (phase 19, plan §4, ADR 0026).

One interactive CLI per conversation: the first message starts it (or resumes it, after it was
put to sleep), the next ones are pasted into the same process. The end of a turn comes from
the CLI's Stop hook and the reply is read from its transcript, block by block, while the turn
runs. The sheet changes only through the tools (and the person's own edits, which lock those
fields), and nothing outside it changes until a proposal is approved.

Threads: the tools and the hooks arrive on request threads; a ticker reads the transcripts of
the turns in progress and puts idle CLIs to sleep. Live state is in memory, behind a lock; what
must survive a restart (messages, sheet, CLI session) is in the database.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    Agent,
    AgentStatus,
    AgentTemplateRow,
    ArchitectConversation,
    ArchitectMessage,
    ArchitectMode,
    Cli,
    CliAccount,
    ConversationStatus,
    McpConnection,
    MessageRole,
    Project,
    Proposal,
    ProposalKind,
    ProposalOrigin,
    ProposalStatus,
    SessionState,
    Team,
)
from agentic_os.models.agent import Tool
from agentic_os.services import accounts as account_ops
from agentic_os.services import avatars, proposals
from agentic_os.services.architect import config as architect_config
from agentic_os.services.architect import prompts
from agentic_os.services.architect import sheet as sheets
from agentic_os.services.architect.tools import AGENT, TEAM
from agentic_os.services.architect.transcript import TranscriptReader
from agentic_os.services.clis import CliCatalog, CliInfo
from agentic_os.services.gitx.events import GitEvents
from agentic_os.services.hooks import HookEffect
from agentic_os.services.skills.selection import bm25
from agentic_os.services.templates import TEMPLATES
from agentic_os.services.usage import limits as usage_limits

log = structlog.get_logger()

TICK = 0.4  # seconds between two reads of the transcripts of the turns in progress
FINISH_GRACE = 0.8  # after Stop: the last block may still be on its way to the transcript
SEARCH_RESULTS = 8  # spike S4: a search, never a whole catalog
TEAM_MODES = (ArchitectMode.TEAM, ArchitectMode.IMPROVE_TEAM, ArchitectMode.IMPROVE_PIPELINE)
STATE_STARTING, STATE_THINKING, STATE_IDLE, STATE_ASLEEP = "starting", "thinking", "idle", "asleep"


OWL_LOOKS = {
    "beanie": "con gorro de lana",
    "book": "con un libro",
    "bow-tie": "con pajarita",
    "crown": "con corona",
    "glasses": "con gafas",
    "grad-cap": "con birrete de graduado",
    "headphones": "con auriculares",
    "monocle": "con monóculo",
    "plain": "sin nada",
    "scarf": "con bufanda",
    "sunglasses": "con gafas de sol",
    "top-hat": "con chistera",
    "wizard": "con sombrero de mago",
}


class ArchitectEvents(GitEvents):
    """Live events of the conversations; every event carries its conversation's id and each
    WebSocket keeps those of the conversation it shows."""

    def conversation(self, conversation_id: str, event: dict) -> None:
        self.publish({**event, "conversation_id": conversation_id})


@dataclass
class Live:
    """A conversation whose CLI is alive."""

    conversation_id: str
    run_id: str
    cli: Cli
    slot: int
    state: str = STATE_STARTING
    reader: TranscriptReader | None = None
    blocks: list[str] = field(default_factory=list)  # the reply of the turn in progress
    fields: list[str] = field(default_factory=list)  # what the turn changed in the sheet
    finish_at: float = 0.0  # Stop arrived: finish the turn at this moment
    last_activity: float = field(default_factory=time.monotonic)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class ArchitectService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        manager: Any,  # RunManager (typed loosely: it imports this package)
        data_dir: Path,
        clis: CliCatalog,
        registries: Any = None,  # the MCP registries of phase 18, to suggest connections
        installed: Callable[[Cli], bool] | None = None,
    ) -> None:
        self._db = sessions
        self.manager = manager
        self.workdir = Path(data_dir) / "architect"
        self.clis = clis
        self.registries = registries
        self._installed = installed or manager.cli_installed
        self.events = ArchitectEvents()
        self._lock = threading.RLock()
        self._live: dict[str, Live] = {}  # by conversation
        self._reserved: set[int] = set()  # work folders of CLIs being started
        self._by_run: dict[str, str] = {}  # run → conversation
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="architect", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(TICK):
            try:
                self.tick()
            except Exception:
                log.exception("architect tick failed")

    def tick(self, now: float | None = None) -> None:
        """Reads the turns in progress, finishes the ones whose Stop arrived and puts idle CLIs
        to sleep (any thread; the ticker calls it, tests too)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            lives = list(self._live.values())
        idle_after = None
        for live in lives:
            self._read_blocks(live)
            if live.finish_at and now >= live.finish_at:
                self._finish_turn(live)
            if live.state == STATE_IDLE:
                if idle_after is None:
                    with self._db() as db:
                        idle_after = architect_config.load(db).idle_minutes * 60
                if now - live.last_activity > idle_after:
                    self._sleep(live, "idle")

    # ------------------------------------------------------------------ conversations
    def get(self, db: Session, conversation_id: str) -> ArchitectConversation:
        conversation = db.get(ArchitectConversation, conversation_id)
        if conversation is None or conversation.workspace_id != DEFAULT_WORKSPACE:
            raise NotFound("conversation")
        return conversation

    def create(
        self,
        db: Session,
        mode: str,
        *,
        agent_id: str | None = None,
        team_id: str | None = None,
        project_id: str | None = None,
        proposal_id: str | None = None,
    ) -> ArchitectConversation:
        """A new conversation. Improving something starts from it as it is now; a new agent
        may go on from a pending proposal (one an agent made with propose_agent)."""
        sheet = sheets.copy_sheet({})
        title = ""
        source: Proposal | None = None
        if proposal_id:
            source = db.get(Proposal, proposal_id)
            if (
                source is None
                or source.kind != ProposalKind.NEW_AGENT
                or source.status != ProposalStatus.PENDING
            ):
                raise ApiError(
                    422, "proposal_not_pending", "a pending proposal of an agent is required"
                )
            sheet = sheets.copy_sheet(source.payload.get("sheet") or {})
            name = ((sheet.get("agents") or {}).get(sheets.MAIN) or {}).get("name", "")
            title = f"Refinar {name}".strip()
        if mode == ArchitectMode.IMPROVE_AGENT:
            agent = db.get(Agent, agent_id) if agent_id else None
            if agent is None or agent.status != AgentStatus.ACTIVE:
                raise ApiError(422, "agent_required", "an active agent to improve is required")
            current = proposals.agent_sheet(db, agent)
            sheet["agents"] = {sheets.MAIN: current}
            sheet["base"] = {"agents": {sheets.MAIN: current}}
            title = f"Mejorar {agent.name}"
        elif mode == ArchitectMode.IMPROVE_TEAM:
            team = db.get(Team, team_id) if team_id else None
            if team is None:
                raise ApiError(422, "team_required", "a team to improve is required")
            sheet["team"] = {"team_id": team.id, "name": team.name}
            members = db.scalars(
                select(Agent.id).where(
                    Agent.team_id == team.id,
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.archived_at.is_(None),
                )
            )
            sheet["existing_agents"] = list(members)
            sheet["base"] = {
                "team": dict(sheet["team"]),
                "existing_agents": sheet["existing_agents"],
            }
            title = f"Mejorar el equipo {team.name}"
        elif mode == ArchitectMode.IMPROVE_PIPELINE:
            project = db.get(Project, project_id) if project_id else None
            if project is None:
                raise ApiError(422, "project_required", "a project is required")
            sheet["pipeline"] = sheets.pipeline_of(db, project)
            sheet["base"] = {"pipeline": sheet["pipeline"]}
            title = f"Mejorar el pipeline de {project.name}"
        elif mode == ArchitectMode.TEAM and project_id:
            # Phase 24: designing the team and pipeline of one project (from its Pipeline tab).
            project = db.get(Project, project_id)
            if project is None:
                raise ApiError(422, "project_required", "the project does not exist")
            title = f"Equipo y pipeline de {project.name}"
        elif mode not in (ArchitectMode.AGENT, ArchitectMode.TEAM):
            raise ApiError(422, "unknown_mode", f"unknown mode {mode!r}")
        conversation = ArchitectConversation(
            workspace_id=DEFAULT_WORKSPACE,
            mode=mode,
            title=title,
            agent_id=agent_id if mode == ArchitectMode.IMPROVE_AGENT else None,
            team_id=team_id,
            project_id=project_id,
            sheet=sheet,
            locked_fields=[],
        )
        db.add(conversation)
        db.flush()
        if source is not None:  # its banner links here; proposing again replaces it
            source.conversation_id = conversation.id
            conversation.agent_id = source.target_agent_id
        return conversation

    def messages(self, db: Session, conversation_id: str) -> list[ArchitectMessage]:
        return list(
            db.scalars(
                select(ArchitectMessage)
                .where(ArchitectMessage.conversation_id == conversation_id)
                .order_by(ArchitectMessage.created_at)
            )
        )

    def state(self, conversation_id: str) -> str:
        with self._lock:
            live = self._live.get(conversation_id)
        return live.state if live else STATE_ASLEEP

    def summary(self, db: Session, conversation: ArchitectConversation) -> dict:
        """The sheet with what the UI shows next to it: problems, progress and locks."""
        catalog = self.catalog(db)
        issues = sheets.sheet_issues(catalog, conversation.sheet)
        agents = (conversation.sheet or {}).get("agents") or {}
        return {
            "sheet": conversation.sheet,
            "issues": sheets.issues_payload(issues),
            "progress": {ref: sheets.progress(a) for ref, a in agents.items()},
            "ready": not [i for i in issues if i.level == "error"]
            and bool(agents or conversation.sheet.get("pipeline")),
            "locked": list(conversation.locked_fields or []),
            "pipeline_layout": sheets.pipeline_layout(conversation.sheet),
        }

    def _add_message(
        self,
        db: Session,
        conversation: ArchitectConversation,
        role: str,
        text: str,
        events: list | None = None,
    ) -> ArchitectMessage:
        message = ArchitectMessage(
            conversation_id=conversation.id, role=role, text=text, tool_events=events or []
        )
        db.add(message)
        conversation.updated_at = utcnow()
        db.flush()
        return message

    def _publish_message(self, message: ArchitectMessage) -> None:
        self.events.conversation(
            message.conversation_id,
            {
                "type": "message",
                "message": {
                    "id": message.id,
                    "role": message.role,
                    "text": message.text,
                    "tool_events": message.tool_events,
                    "created_at": message.created_at.isoformat() if message.created_at else None,
                },
            },
        )

    def _set_state(self, live: Live, state: str) -> None:
        live.state = state
        self.events.conversation(live.conversation_id, {"type": "state", "state": state})

    # ------------------------------------------------------------------ the CLI
    def _cli_config(
        self, db: Session, conversation: ArchitectConversation
    ) -> tuple[Cli, CliAccount, str]:
        """The CLI, account and model: those of the conversation once it started (a resumed
        session lives in its CLI), else the settings'; or why none can be used."""
        settings = architect_config.load(db)
        if conversation.cli:
            cli = Cli(conversation.cli)
        elif settings.cli:
            cli = Cli(settings.cli)
        else:
            cli = next((c for c in (Cli.CLAUDE, Cli.AGY) if self._installed(c)), Cli.CLAUDE)
        if not self._installed(cli):
            raise ApiError(409, "cli_not_installed", f"{cli.value} no está instalado")
        wanted = conversation.account_id or settings.account_id
        account = db.get(CliAccount, wanted) if wanted else None
        if account is None or account.cli != cli:
            account = account_ops.default_for(db, cli)
        gate = usage_limits.blocked(db, account)
        if gate is not None or account.session_state == SessionState.DOWN:
            reason = {
                "limit": "ha llegado a su límite diario",
                "quota": "se ha quedado sin cuota",
            }.get(gate or "", "no tiene la sesión iniciada")
            raise ApiError(
                409,
                "architect_unavailable",
                f"La cuenta {account_ops.display_name(account)} {reason}.",
                extra={"reason": gate or "session"},
            )
        model = conversation.model or settings.model or architect_config.DEFAULT_MODEL[cli]
        return cli, account, model

    def _free_slot(self) -> int:
        """A work folder no live CLI uses; the oldest idle one is put to sleep if needed."""
        with self._db() as db:
            limit = architect_config.load(db).max_live
        with self._lock:
            used = {live.slot for live in self._live.values()} | self._reserved
            idle = sorted(
                (live for live in self._live.values() if live.state == STATE_IDLE),
                key=lambda live: live.last_activity,
            )
            for slot in range(1, limit + 1):
                if slot not in used:
                    self._reserved.add(slot)
                    return slot
        if not idle:
            raise ApiError(
                409,
                "architect_busy",
                "Todas las conversaciones vivas están trabajando: espera a que termine una.",
            )
        self._sleep(idle[0], "make_room", wait=True)
        with self._lock:
            # Taken only if the old CLI is gone and nobody else got the folder meanwhile.
            gone = self._live.get(idle[0].conversation_id) is not idle[0]
            if not gone or idle[0].slot in self._reserved:
                raise ApiError(
                    409,
                    "architect_busy",
                    "Todas las conversaciones vivas están trabajando: espera a que termine una.",
                )
            self._reserved.add(idle[0].slot)
            return idle[0].slot

    def send(self, db: Session, conversation_id: str, text: str) -> ArchitectMessage:
        """A message of the person: written into the live CLI, or the one that starts it (or
        resumes it). The caller commits."""
        text = text.strip()
        if not text:
            raise ApiError(422, "empty_message", "the message is empty")
        conversation = self.get(db, conversation_id)
        if conversation.status not in (ConversationStatus.OPEN, ConversationStatus.PROPOSED):
            raise ApiError(409, "conversation_closed", "the conversation is closed")
        cli, account, model = self._cli_config(db, conversation)  # before anything is written
        with self._lock:
            live = self._live.get(conversation.id)
        message = self._add_message(db, conversation, MessageRole.USER, text)
        if not conversation.title:
            conversation.title = text.splitlines()[0][:80]
        if live is not None:
            session = self.manager.get(live.run_id)
            if session is not None and session.alive:
                session.deliver(text)
                live.last_activity = time.monotonic()
                db.commit()
                self._publish_message(message)
                return message
        db.commit()
        self._publish_message(message)
        self._launch(db, conversation, cli, account, model, text)
        return message

    def _launch(
        self,
        db: Session,
        conversation: ArchitectConversation,
        cli: Cli,
        account: CliAccount,
        model: str,
        prompt: str,
    ) -> None:
        slot = self._free_slot()
        try:
            self._launch_in(db, conversation, cli, account, model, prompt, slot)
        finally:
            with self._lock:
                self._reserved.discard(slot)

    def _launch_in(
        self,
        db: Session,
        conversation: ArchitectConversation,
        cli: Cli,
        account: CliAccount,
        model: str,
        prompt: str,
        slot: int,
    ) -> None:
        settings = architect_config.load(db)
        target = ""
        if conversation.mode == ArchitectMode.IMPROVE_AGENT:
            target = ((conversation.sheet.get("agents") or {}).get(sheets.MAIN) or {}).get(
                "name", ""
            )
        elif conversation.mode == ArchitectMode.IMPROVE_TEAM:
            target = (conversation.sheet.get("team") or {}).get("name", "")
        elif conversation.mode == ArchitectMode.IMPROVE_PIPELINE:
            target = (conversation.sheet.get("pipeline") or {}).get("project_name", "")
        elif conversation.mode == ArchitectMode.TEAM and conversation.project_id:
            # Phase 24: «Diseñar con el Arquitecto» from a project.
            project = db.get(Project, conversation.project_id)
            target = project.name if project else ""
        instructions = prompts.instructions(
            settings.instructions or None, conversation.mode, target
        )
        resume = conversation.cli_session_id if conversation.cli == cli.value else None
        try:
            run = self.manager.launch_architect(
                db,
                cli=cli,
                account=account,
                model=model,
                prompt=prompt,
                instructions=instructions,
                cwd=str(self.workdir / f"slot-{slot}"),
                toolset=TEAM if conversation.mode in TEAM_MODES else AGENT,
                resume_session=resume,
            )
        except ApiError:
            raise
        except Exception as error:
            log.exception("could not start the Architect", conversation=conversation.id)
            raise ApiError(
                500, "architect_failed", f"No se pudo arrancar el CLI: {error}"
            ) from error
        conversation = self.get(db, conversation.id)
        conversation.cli, conversation.account_id, conversation.model = cli.value, account.id, model
        conversation.run_id = run.id
        if run.cli_session_id:
            conversation.cli_session_id = run.cli_session_id
        if run.status == "failed":
            note = self._add_message(
                db, conversation, MessageRole.SYSTEM, f"No se pudo arrancar el CLI: {run.error}"
            )
            db.commit()
            self._publish_message(note)
            return
        db.commit()
        live = Live(conversation.id, run.id, cli, slot)
        with self._lock:
            self._live[conversation.id] = live
            self._by_run[run.id] = conversation.id
        self._set_state(live, STATE_STARTING)

    def interrupt(self, conversation_id: str) -> bool:
        with self._lock:
            live = self._live.get(conversation_id)
        session = self.manager.get(live.run_id) if live else None
        if session is None or not session.interrupt():
            return False
        live.finish_at = time.monotonic()  # what it said so far is the reply
        return True

    def reset(self, db: Session, conversation_id: str, clear_sheet: bool = False) -> None:
        """A clean CLI: the next message starts one without the earlier context."""
        conversation = self.get(db, conversation_id)
        with self._lock:
            live = self._live.get(conversation_id)
        if live is not None:
            self._sleep(live, "reset", wait=True)
        conversation.cli_session_id = None
        conversation.cli = None
        if clear_sheet:
            base = conversation.sheet.get("base") or {}
            fresh = sheets.copy_sheet(base) if base else sheets.copy_sheet({})
            fresh["base"] = base or None
            conversation.sheet = fresh
            conversation.locked_fields = []
        note = self._add_message(db, conversation, MessageRole.SYSTEM, "Conversación reiniciada.")
        db.commit()
        self._publish_message(note)

    def sleep(self, conversation_id: str) -> None:
        with self._lock:
            live = self._live.get(conversation_id)
        if live is not None:
            self._sleep(live, "user", wait=True)

    def _sleep(self, live: Live, reason: str, wait: bool = False) -> None:
        """Closes the CLI; the conversation is resumed by its next message."""
        log.info("architect asleep", conversation=live.conversation_id, reason=reason)
        session = self.manager.get(live.run_id)
        self.manager.stop(live.run_id)
        if wait and session is not None:
            session.wait(20)

    def delete(self, db: Session, conversation_id: str) -> None:
        conversation = self.get(db, conversation_id)
        self.sleep(conversation_id)
        db.delete(conversation)

    # ------------------------------------------------------------------ hooks and transcript
    def on_hook(self, run_id: str, effect: HookEffect, boundary: bool) -> None:
        """From the RunManager: a hook of an Architect's CLI (any thread)."""
        with self._lock:
            conversation_id = self._by_run.get(run_id)
            live = self._live.get(conversation_id) if conversation_id else None
        if live is None:
            return
        # The reader starts where the transcript is when a turn starts: what comes after is the
        # reply. Only then (a Stop must not move it past blocks not read yet).
        starting = boundary and effect.turn_started
        if effect.transcript_path and (
            live.reader is None or (starting and live.reader.path != Path(effect.transcript_path))
        ):
            live.reader = TranscriptReader(live.cli, effect.transcript_path)
        if effect.session_id:
            self._remember_session(live, effect.session_id)
        if starting:
            live.blocks, live.fields, live.finish_at = [], [], 0.0
            live.last_activity = time.monotonic()
            self._set_state(live, STATE_THINKING)
        if effect.turn_ended:
            live.finish_at = time.monotonic() + FINISH_GRACE

    def _remember_session(self, live: Live, session_id: str) -> None:
        with self._db() as db:
            conversation = db.get(ArchitectConversation, live.conversation_id)
            if conversation is not None and conversation.cli_session_id != session_id:
                conversation.cli_session_id = session_id
                db.commit()

    def _read_blocks(self, live: Live) -> None:
        if live.reader is None or live.state != STATE_THINKING:
            return
        for block in live.reader.read_new():
            live.blocks.append(block)
            self.events.conversation(live.conversation_id, {"type": "block", "text": block})

    def _finish_turn(self, live: Live) -> None:
        self._read_blocks(live)
        live.finish_at = 0.0
        text = "\n\n".join(live.blocks).strip()
        events = [{"fields": sorted(set(live.fields))}] if live.fields else []
        live.blocks, live.fields = [], []
        live.last_activity = time.monotonic()
        if text or events:
            with self._db() as db:
                conversation = db.get(ArchitectConversation, live.conversation_id)
                if conversation is not None:
                    message = self._add_message(
                        db, conversation, MessageRole.ARCHITECT, text or "(sin respuesta)", events
                    )
                    db.commit()
                    self._publish_message(message)
        self._set_state(live, STATE_IDLE)

    def on_run_end(self, run_id: str) -> None:
        """The CLI closed (asleep, reset, crashed or the app closing)."""
        with self._lock:
            conversation_id = self._by_run.pop(run_id, None)
            live = self._live.get(conversation_id) if conversation_id else None
            if live is not None and live.run_id != run_id:
                return  # an old run ending after a newer one took its conversation
            if live is not None:
                del self._live[conversation_id]
        if live is None:
            return
        if live.blocks or live.fields:
            self._finish_turn(live)
        if live.state == STATE_STARTING:
            self._forget_lost_session(live)
        self._set_state(live, STATE_ASLEEP)

    def _forget_lost_session(self, live: Live) -> None:
        """The CLI closed before it started a turn. If it was resuming a conversation, the CLI
        probably no longer has it: the next message starts a clean one instead of failing again
        the same way."""
        try:
            with self._db() as db:
                conversation = db.get(ArchitectConversation, live.conversation_id)
                if conversation is None or not conversation.cli_session_id:
                    return
                conversation.cli_session_id = None
                conversation.cli = None
                note = self._add_message(
                    db,
                    conversation,
                    MessageRole.SYSTEM,
                    "El CLI se cerró al retomar la conversación (puede que ya no tenga la "
                    "sesión). Envía el mensaje otra vez: empezará una sesión limpia.",
                )
                db.commit()
                self._publish_message(note)
        except Exception:
            log.exception("could not clear the lost session", conversation=live.conversation_id)

    def mcp_connected(self, run_id: str) -> None:
        self.manager.mcp_connected(run_id)

    # ------------------------------------------------------------------ the person's edits
    def patch_sheet(
        self, db: Session, conversation_id: str, patch: dict, ref: str = sheets.MAIN
    ) -> dict:
        """An edit by hand: what passes is stored and locked (the Architect cannot change it
        until the person releases it)."""
        conversation = self.get(db, conversation_id)
        catalog = self.catalog(db)
        result = sheets.apply_patch(catalog, conversation.sheet, patch, ref=ref)
        conversation.sheet = result.sheet
        locked = set(conversation.locked_fields or []) | set(result.changed)
        conversation.locked_fields = sorted(locked)
        db.flush()
        self._publish_sheet(db, conversation)
        return {"refused": result.refused, **self.summary(db, conversation)}

    def unlock(self, db: Session, conversation_id: str, fields: list[str]) -> list[str]:
        conversation = self.get(db, conversation_id)
        conversation.locked_fields = sorted(set(conversation.locked_fields or []) - set(fields))
        db.flush()
        self._publish_sheet(db, conversation)
        return conversation.locked_fields

    def _publish_sheet(self, db: Session, conversation: ArchitectConversation) -> None:
        self.events.conversation(
            conversation.id, {"type": "sheet", **self.summary(db, conversation)}
        )

    # ------------------------------------------------------------------ proposals
    def propose(self, db: Session, conversation_id: str):
        """«Crear borrador» / «Crear propuesta»: the sheet becomes a proposal."""
        conversation = self.get(db, conversation_id)
        if conversation.status not in (ConversationStatus.OPEN, ConversationStatus.PROPOSED):
            raise ApiError(409, "already_proposed", "the conversation already made its proposal")
        catalog = self.catalog(db)
        by = proposals.ProposedBy(ProposalOrigin.ARCHITECT, conversation_id=conversation.id)
        lib = self.manager.skill_library
        # Refining after a proposal: the earlier one (and its drafts) is replaced.
        for earlier in db.scalars(
            select(Proposal).where(
                Proposal.conversation_id == conversation.id,
                Proposal.status == ProposalStatus.PENDING,
            )
        ):
            proposals.reject(db, lib, earlier)
        conversation.status = ConversationStatus.OPEN
        if conversation.mode == ArchitectMode.AGENT:
            return proposals.create_new_agent(db, lib, catalog, conversation.sheet, by)
        if conversation.mode == ArchitectMode.IMPROVE_AGENT:
            agent = db.get(Agent, conversation.agent_id) if conversation.agent_id else None
            if agent is None:
                raise NotFound("agent")
            base = (conversation.sheet.get("base") or {}).get("agents", {}).get(sheets.MAIN) or {}
            return proposals.create_agent_changes(
                db, lib, catalog, agent, base, conversation.sheet, by
            )
        kind = {
            ArchitectMode.TEAM: ProposalKind.TEAM,
            ArchitectMode.IMPROVE_TEAM: ProposalKind.TEAM_CHANGES,
            ArchitectMode.IMPROVE_PIPELINE: ProposalKind.PIPELINE_CHANGES,
        }[ArchitectMode(conversation.mode)]
        return proposals.create_team(db, lib, catalog, conversation.sheet, by, kind)

    # ------------------------------------------------------------------ the catalog
    def _cli_infos(self) -> list[CliInfo]:
        return self.clis.list()

    def catalog(self, db: Session) -> sheets.Catalog:
        return sheets.Catalog.load(db, self._cli_infos(), DEFAULT_WORKSPACE)

    # ------------------------------------------------------------------ the tools (MCP)
    def call_tool(self, run_id: str, name: str, args: dict[str, Any]) -> str:
        """A tool of the Architect's MCP server, on behalf of the conversation of `run_id`.
        Never raises: the answer tells the model what went wrong."""
        with self._lock:
            conversation_id = self._by_run.get(run_id)
            live = self._live.get(conversation_id) if conversation_id else None
        if conversation_id is None:
            return _json({"error": "Esta sesión ya no tiene conversación."})
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return _json({"error": f"herramienta desconocida: {name}"})
        try:
            with self._db() as db:
                conversation = self.get(db, conversation_id)
                answer, changed = handler(db, conversation, **args)
                if changed:
                    if live is not None:
                        live.fields += changed
                        live.last_activity = time.monotonic()
                    db.commit()
                    self._publish_sheet(db, conversation)
                return _json(answer)
        except Exception as error:
            log.exception("architect tool failed", tool=name, run_id=run_id)
            return _json({"error": f"No se pudo: {error}"})

    # Each tool returns (answer, changed field paths). -------------------------------------
    def _tool_list_clis(self, db: Session, conversation, **_) -> tuple[Any, list]:
        accounts = account_ops.list_accounts(db)
        result = []
        for info in self._cli_infos():
            if not info.installed:
                continue
            result.append(
                {
                    "cli": info.id,
                    "name": info.name,
                    "models": [m.id for m in info.models] or "(cualquiera: no se pudieron listar)",
                    "accounts": [
                        {"id": a.id, "name": account_ops.display_name(a), "default": a.is_default}
                        for a in accounts
                        if a.cli == info.id
                    ],
                }
            )
        return {"clis": result, "allowed_tools": [t.value for t in Tool]}, []

    def _tool_list_teams(self, db: Session, conversation, **_) -> tuple[Any, list]:
        teams = db.scalars(
            select(Team).where(Team.workspace_id == DEFAULT_WORKSPACE).order_by(Team.position)
        )
        return [{"id": t.id, "name": t.name, "description": t.description} for t in teams], []

    def _tool_list_agents(self, db: Session, conversation, **_) -> tuple[Any, list]:
        agents = db.scalars(
            select(Agent)
            .where(Agent.workspace_id == DEFAULT_WORKSPACE, Agent.archived_at.is_(None))
            .order_by(Agent.name)
        )
        teams = {t.id: t.name for t in db.scalars(select(Team))}
        return [
            {
                "name": a.name,
                "role": a.role,
                "team": teams.get(a.team_id or "", ""),
                "cli": a.cli,
                "model": a.model,
                "status": a.status,
            }
            for a in agents
        ], []

    def _tool_get_agent(self, db: Session, conversation, name: str = "", **_) -> tuple[Any, list]:
        agent = self.catalog(db).agent(name)
        if agent is None:
            return {"error": f"No hay ningún agente {name}"}, []
        values = proposals.agent_sheet(db, agent)
        values.pop("id", None)
        return values, []

    def _tool_search_skills(
        self, db: Session, conversation, query: str = "", **_
    ) -> tuple[Any, list]:
        skills = [s for s in self.catalog(db).skills if s.scope != "agent"]
        ranked = _rank(query, skills, lambda s: f"{s.name.replace('-', ' ')} {s.description}")
        return [
            {"name": s.name, "description": s.description, "level": s.scope} for s in ranked
        ], []

    def _tool_search_knowledge_docs(
        self, db: Session, conversation, query: str = "", **_
    ) -> tuple[Any, list]:
        docs = self.catalog(db).docs
        ranked = _rank(query, docs, lambda d: f"{d.title} {d.description} {d.summary[:400]}")
        projects = {p.id: p.name for p in db.scalars(select(Project))}
        return [
            {
                "id": d.id,
                "title": d.title,
                "level": d.scope,
                "project": projects.get(d.project_id or "", ""),
                "description": d.description[:200],
            }
            for d in ranked
        ], []

    def _tool_list_connections(self, db: Session, conversation, **_) -> tuple[Any, list]:
        return [
            {"name": c.name, "description": c.description, "tools": len(c.tools)}
            for c in self.catalog(db).connections
        ], []

    def _tool_get_connection(
        self, db: Session, conversation, name: str = "", **_
    ) -> tuple[Any, list]:
        connection: McpConnection | None = self.catalog(db).connection(name)
        if connection is None:
            return {"error": f"No hay ninguna conexión {name}"}, []
        tools = [
            {"name": t.get("name"), "description": str(t.get("description", ""))[:200]}
            for t in connection.tools
            if isinstance(t, dict)
        ]
        return {"name": connection.name, "description": connection.description, "tools": tools}, []

    def _tool_search_connection_registry(
        self, db: Session, conversation, query: str = "", **_
    ) -> tuple[Any, list]:
        if self.registries is None:
            return {"error": "Los registros públicos no están disponibles."}, []
        listing = self.registries.search(db, query)
        cards = [
            {
                "registry_ref": f"{c.source}:{c.ref}",
                "name": c.name,
                "description": c.description[:200],
                "verified": c.verified,
                "uses": c.uses,
            }
            for c in listing.cards[:SEARCH_RESULTS]
        ]
        return {"results": cards, "errors": listing.errors}, []

    def _tool_list_owls(self, db: Session, conversation, **_) -> tuple[Any, list]:
        return [{"avatar": f"owl:{owl}", "looks": OWL_LOOKS[owl]} for owl in avatars.OWL_IDS], []

    def _tool_list_templates(self, db: Session, conversation, **_) -> tuple[Any, list]:
        fixed = [
            {"id": t.id, "name": t.name, "role": t.role, "description": t.description}
            for t in TEMPLATES
        ]
        own = db.scalars(
            select(AgentTemplateRow).where(AgentTemplateRow.workspace_id == DEFAULT_WORKSPACE)
        )
        return fixed + [{"id": t.id, "name": t.name, "description": t.description} for t in own], []

    def _tool_get_template(
        self, db: Session, conversation, template: str = "", **_
    ) -> tuple[Any, list]:
        for fixed in TEMPLATES:
            if template in (fixed.id, fixed.name):
                return fixed.model_dump(), []
        for own in db.scalars(select(AgentTemplateRow)):
            if template in (own.id, own.name):
                return {"id": own.id, "name": own.name, **(own.payload.get("agent") or {})}, []
        return {"error": f"No hay ninguna plantilla {template}"}, []

    def _tool_get_pipeline_templates(self, db: Session, conversation, **_) -> tuple[Any, list]:
        """Phase 24: the fixed pipeline templates in the sheet's format, each stage naming the
        agent template of its role."""
        from agentic_os.services import pipelines as pipeline_ops

        result = []
        for key, build in pipeline_ops.TEMPLATES.items():
            payload = build()
            result.append(
                {
                    "template": key.value,
                    "name": payload.name,
                    "stages": [
                        {
                            "name": s.name,
                            "agent_template": s.agent_id,
                            "requires_review": s.requires_review,
                            "reject_to": s.reject_to,
                            "reject_also": s.reject_also,
                            "exit_condition": s.exit_condition,
                        }
                        for s in payload.stages
                    ],
                    "links": [x.model_dump() for x in payload.links or []],
                }
            )
        return result, []

    def _tool_list_projects(self, db: Session, conversation, **_) -> tuple[Any, list]:
        projects = db.scalars(select(Project).where(Project.workspace_id == DEFAULT_WORKSPACE))
        return [{"name": p.name, "pipeline": sheets.pipeline_of(db, p)} for p in projects], []

    def _tool_get_sheet(self, db: Session, conversation, **_) -> tuple[Any, list]:
        return self.summary(db, conversation), []

    def _answer(self, db: Session, conversation, result: sheets.PatchResult) -> tuple[Any, list]:
        conversation.sheet = result.sheet
        summary = self.summary(db, conversation)
        return {
            "refused": result.refused,
            "issues": summary["issues"],
            "progress": summary["progress"],
        }, result.changed

    def _tool_update_sheet(
        self,
        db: Session,
        conversation,
        patch: dict | None = None,
        agent_ref: str = sheets.MAIN,
        **_,
    ) -> tuple[Any, list]:
        if conversation.mode not in TEAM_MODES:
            agent_ref = sheets.MAIN
        result = sheets.apply_patch(
            self.catalog(db),
            conversation.sheet,
            patch or {},
            ref=agent_ref,
            locked=conversation.locked_fields or [],
        )
        return self._answer(db, conversation, result)

    def _tool_draft_skill(
        self,
        db: Session,
        conversation,
        name: str = "",
        description: str = "",
        body: str = "",
        agent_ref: str = sheets.MAIN,
        **_,
    ) -> tuple[Any, list]:
        if conversation.mode not in TEAM_MODES:
            agent_ref = sheets.MAIN
        agent = (conversation.sheet.get("agents") or {}).get(agent_ref) or {}
        drafts = [d for d in agent.get("new_skills") or [] if d.get("name") != name]
        drafts.append({"name": name, "description": description, "body": body})
        result = sheets.apply_patch(
            self.catalog(db), conversation.sheet, {"new_skills": drafts}, ref=agent_ref
        )
        return self._answer(db, conversation, result)

    def _tool_suggest_connection(
        self,
        db: Session,
        conversation,
        registry_ref: str = "",
        reason: str = "",
        agent_ref: str = sheets.MAIN,
        **_,
    ) -> tuple[Any, list]:
        source, _, ref = registry_ref.partition(":")
        if not source or not ref:
            return {"error": "registry_ref es el de search_connection_registry («fuente:id»)"}, []
        sheet = sheets.copy_sheet(conversation.sheet)
        sheet["suggested_connections"] = [
            s for s in sheet["suggested_connections"] if s.get("registry_ref") != registry_ref
        ] + [
            {
                "registry_ref": registry_ref,
                "source": source,
                "ref": ref,
                "reason": reason.strip()[:500],
                "agent_ref": agent_ref,
            }
        ]
        conversation.sheet = sheet
        return {"ok": True, "note": "El usuario la verá en la ficha y decidirá si la instala."}, [
            "suggested_connections"
        ]

    def _tool_request_unlock(
        self, db: Session, conversation, field: str = "", reason: str = "", **_
    ) -> tuple[Any, list]:
        if field not in (conversation.locked_fields or []):
            return {"ok": True, "note": "Ese campo no está fijado: puedes cambiarlo."}, []
        message = self._add_message(
            db,
            conversation,
            MessageRole.SYSTEM,
            reason.strip()[:500] or f"El Arquitecto quiere cambiar {field}.",
            [{"unlock_request": field}],
        )
        db.commit()
        self._publish_message(message)
        return {
            "ok": True,
            "note": "El usuario verá un botón para soltarlo; espera a que lo haga.",
        }, []

    def _tool_set_team(
        self, db: Session, conversation, name: str = "", description: str = "", team: str = "", **_
    ) -> tuple[Any, list]:
        result = sheets.set_team(
            self.catalog(db),
            conversation.sheet,
            {"name": name, "description": description, "team": team},
        )
        return self._answer(db, conversation, result)

    def _tool_use_existing_agent(
        self, db: Session, conversation, name: str = "", **_
    ) -> tuple[Any, list]:
        result = sheets.use_existing_agent(self.catalog(db), conversation.sheet, name)
        return self._answer(db, conversation, result)

    def _tool_remove_agent(
        self, db: Session, conversation, agent_ref: str = "", **_
    ) -> tuple[Any, list]:
        sheet = sheets.copy_sheet(conversation.sheet)
        if agent_ref in sheet["agents"]:
            del sheet["agents"][agent_ref]
        else:
            agent = self.catalog(db).agent(agent_ref)
            if agent is None or agent.id not in sheet["existing_agents"]:
                return {"error": f"{agent_ref} no está en el diseño"}, []
            sheet["existing_agents"].remove(agent.id)
        return self._answer(db, conversation, sheets.PatchResult(sheet, changed=["agents"]))

    def _tool_set_pipeline(
        self,
        db: Session,
        conversation,
        project: str = "",
        stages: list | None = None,
        links: list | None = None,
        max_rejections: int | None = None,
        **_,
    ) -> tuple[Any, list]:
        result = sheets.set_pipeline(
            self.catalog(db),
            conversation.sheet,
            {
                "project": project,
                "stages": stages or [],
                "links": links,
                "max_rejections": max_rejections,
            },
        )
        return self._answer(db, conversation, result)


def _rank(query: str, items: list, text: Callable[[Any], str]) -> list:
    """The SEARCH_RESULTS items that best match `query` (BM25 over their text, like the skills'
    selection without a meaning model); an empty query lists the first ones."""
    if not query.strip():
        return items[:SEARCH_RESULTS]
    scores = bm25(query, [text(item) for item in items])
    ranked = sorted(zip(scores, range(len(items)), strict=True), key=lambda x: (-x[0], x[1]))
    return [items[i] for score, i in ranked if score > 0][:SEARCH_RESULTS]
