"""The knowledge queue: documents wait in the database (`status = queued`) and a few threads take
them one by one, each with a worker of its own (phase 14).

Because the queue *is* the database, nothing is lost when the app closes: what was half done
(`converting`…) goes back to `queued` on the next start. Pausing stops taking new documents; the
ones being processed finish.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from pathlib import Path

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import DocStatus, KnowledgeDoc
from agentic_os.schemas.knowledge import read_doc
from agentic_os.services.knowledge import config as knowledge_config
from agentic_os.services.knowledge.docs import IN_PROGRESS
from agentic_os.services.knowledge.events import KnowledgeEvents
from agentic_os.services.knowledge.pipeline import Pipeline
from agentic_os.services.knowledge.worker import InlineWorker, ProcessWorker, Worker
from agentic_os.services.system_stats import Sampler, SamplerThread

log = structlog.get_logger()

POLL_SECONDS = 2.0  # how often an idle thread looks for documents nobody poked it about
MODES = ("subprocess", "inline", "off")


class KnowledgeService:
    """`mode`: «subprocess» (a worker process per thread), «inline» (in the backend's own
    process) or «off» (no threads: the tests call `run_pending` themselves)."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        data_dir: Path,
        events: KnowledgeEvents,
        mode: str = "subprocess",
        worker_factory: Callable[[], Worker] | None = None,
    ) -> None:
        self.sessions = sessions
        self.data_dir = Path(data_dir)
        self.events = events
        self.mode = mode if mode in MODES else "subprocess"
        self._factory = worker_factory or (
            ProcessWorker if self.mode == "subprocess" else InlineWorker
        )
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._paused = False
        self._active: set[str] = set()
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._workers: list[Worker] = []
        self._sampler: Sampler | None = None
        self._sampling: SamplerThread | None = None

    # ------------------------------------------------------------------ life cycle
    def start(self) -> None:
        self.recover()
        if self.mode == "off":
            return
        with self.sessions() as db:
            count = knowledge_config.load(db).concurrency
        # The machine's load, once a second while there is work.
        self._sampling = SamplerThread(self.events.publish, lambda: bool(self._active))
        self._sampling.start()
        for number in range(count):
            worker = self._factory()
            self._workers.append(worker)
            thread = threading.Thread(
                target=self._loop,
                args=(Pipeline(self.sessions, self.data_dir, worker, self.events),),
                name=f"knowledge-{number}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        for worker in self._workers:
            with contextlib.suppress(Exception):
                worker.close()
        for thread in self._threads:
            thread.join(timeout=5)
        self._threads.clear()
        self._workers.clear()
        if self._sampling:
            self._sampling.stop()
            self._sampling = None
        if self._sampler:
            self._sampler.close()
            self._sampler = None

    def recover(self) -> None:
        """What a closed app left half done goes back to the queue."""
        with self.sessions() as db:
            db.execute(
                update(KnowledgeDoc)
                .where(KnowledgeDoc.status.in_(IN_PROGRESS))
                .values(status=DocStatus.QUEUED, progress_done=0, progress_total=0)
            )
            db.commit()

    def poke(self) -> None:
        self._wake.set()

    # ----------------------------------------------------------------------- control
    def pause(self) -> None:
        self._paused = True
        self.events.queue(self.state())

    def resume(self) -> None:
        self._paused = False
        self._wake.set()
        self.events.queue(self.state())

    def state(self) -> dict:
        with self.sessions() as db:
            waiting = db.scalar(
                select(func.count())
                .select_from(KnowledgeDoc)
                .where(
                    KnowledgeDoc.workspace_id == DEFAULT_WORKSPACE,
                    KnowledgeDoc.status == DocStatus.QUEUED,
                )
            )
        with self._lock:
            active = sorted(self._active)
        return {"paused": self._paused, "queued": waiting or 0, "active": active, "mode": self.mode}

    def system(self) -> dict:
        """The machine's load now. The first reading of a rate is 0: ask again a second later."""
        if self._sampler is None:
            self._sampler = Sampler()
        return self._sampler.sample()

    # ------------------------------------------------------------------- the queue
    def claim_next(self) -> str | None:
        """Takes the oldest queued document (compare-and-set: two threads never take one)."""
        with self.sessions() as db:
            candidates = db.scalars(
                select(KnowledgeDoc.id)
                .where(
                    KnowledgeDoc.workspace_id == DEFAULT_WORKSPACE,
                    KnowledgeDoc.status == DocStatus.QUEUED,
                )
                .order_by(KnowledgeDoc.created_at, KnowledgeDoc.id)
                .limit(5)
            ).all()
            for doc_id in candidates:
                taken = db.execute(
                    update(KnowledgeDoc)
                    .where(KnowledgeDoc.id == doc_id, KnowledgeDoc.status == DocStatus.QUEUED)
                    .values(
                        status=DocStatus.CONVERTING,
                        progress_done=0,
                        progress_total=0,
                        error_code=None,
                        error_message=None,
                    )
                )
                if taken.rowcount == 1:
                    db.commit()
                    doc = db.get(KnowledgeDoc, doc_id)
                    db.refresh(doc)
                    self.events.doc(read_doc(doc).model_dump(mode="json"))
                    return doc_id
            db.rollback()
        return None

    def _run(self, pipeline: Pipeline, doc_id: str) -> None:
        with self._lock:
            self._active.add(doc_id)
        self.events.queue(self.state())
        try:
            pipeline.process(doc_id)
        finally:
            with self._lock:
                self._active.discard(doc_id)
            self.events.queue(self.state())

    def _loop(self, pipeline: Pipeline) -> None:
        while not self._stop.is_set():
            doc_id = None if self._paused else self.claim_next()
            if doc_id is None:
                self._wake.wait(POLL_SECONDS)
                self._wake.clear()
                continue
            self._run(pipeline, doc_id)

    def run_pending(self, worker: Worker | None = None) -> int:
        """Processes every queued document here and now (the tests; the threads are not used).
        Returns how many were processed."""
        own = worker or self._factory()
        pipeline = Pipeline(self.sessions, self.data_dir, own, self.events)
        done = 0
        try:
            while not self._paused and (doc_id := self.claim_next()) is not None:
                self._run(pipeline, doc_id)
                done += 1
        finally:
            if worker is None:
                own.close()
        return done
