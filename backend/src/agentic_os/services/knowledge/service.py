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

import numpy as np
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import DocStatus, KnowledgeDoc, Review
from agentic_os.schemas.knowledge import read_doc
from agentic_os.services.knowledge import config as knowledge_config
from agentic_os.services.knowledge import context as knowledge_context
from agentic_os.services.knowledge import describe, embeddings, graph, search
from agentic_os.services.knowledge.docs import IN_PROGRESS
from agentic_os.services.knowledge.errors import KnowledgeError
from agentic_os.services.knowledge.events import KnowledgeEvents
from agentic_os.services.knowledge.graph_search import Adjacency
from agentic_os.services.knowledge.pipeline import Pipeline, model_spec
from agentic_os.services.knowledge.worker import InlineWorker, ProcessWorker, Worker
from agentic_os.services.localmodels import catalog, selection
from agentic_os.services.localmodels.catalog import CatalogEntry
from agentic_os.services.localmodels.llama import LlamaServer
from agentic_os.services.system_stats import Sampler, SamplerThread

log = structlog.get_logger()

GRAPH_DEBOUNCE = 0.4  # seconds to wait for more changes before recomputing the links
POLL_SECONDS = 2.0  # how often an idle thread looks for documents nobody poked it about
MODES = ("subprocess", "inline", "off")
QUERY_IDLE_SECONDS = 300.0  # the worker that embeds questions stays ready for this long


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
        cli_overrides: dict[str, list[str]] | None = None,
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
        self._query_worker: Worker | None = None
        self._llama: LlamaServer | None = None
        # Picks the describer for the pictures; tests put a fake one here.
        self.describers: describe.Factory = describe.default_factory(
            self.data_dir, cli_overrides, self._llama_for
        )
        self._query_lock = threading.Lock()
        self._reindexing = False
        self._reindex_again = False
        self._graph_dirty = threading.Event()
        self._graph_lock = threading.Lock()  # one recompute at a time
        self._graph_announce = False  # something other than the links changed too
        self._graph_thread: threading.Thread | None = None
        self.graph_version = 0

    def _llama_for(self, engine: CatalogEntry, vision: CatalogEntry, threads: int) -> LlamaServer:
        """The `llama-server` for this vision model: one at a time, kept between documents."""
        with self._lock:
            if self._llama is None or self._llama.vision.id != vision.id:
                if self._llama is not None:
                    self._llama.stop()
                self._llama = LlamaServer(self.data_dir, engine, vision, threads)
            return self._llama

    def _make_describer(self, db: Session, limits):
        return self.describers(db, limits)

    def pipeline(self, worker: Worker) -> Pipeline:
        return Pipeline(
            self.sessions, self.data_dir, worker, self.events, describers=self._make_describer
        )

    # ------------------------------------------------------------------ life cycle
    def start(self) -> None:
        self.recover()
        knowledge_context.clean_all(self.data_dir)  # no run is alive yet
        if self.mode == "off":
            return
        with self.sessions() as db:
            count = knowledge_config.load(db).concurrency
        self.reindex()  # documents indexed with another model (or none) than the chosen one
        self._graph_thread = threading.Thread(
            target=self._graph_loop, name="knowledge-graph", daemon=True
        )
        self._graph_thread.start()
        self.mark_graph_dirty()
        # The machine's load, once a second while there is work.
        self._sampling = SamplerThread(self.events.publish, lambda: bool(self._active))
        self._sampling.start()
        for number in range(count):
            worker = self._factory()
            self._workers.append(worker)
            thread = threading.Thread(
                target=self._loop,
                args=(self.pipeline(worker),),
                name=f"knowledge-{number}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._graph_dirty.set()
        for worker in self._workers:
            with contextlib.suppress(Exception):
                worker.close()
        for thread in self._threads:
            thread.join(timeout=5)
        if self._graph_thread is not None:
            self._graph_thread.join(timeout=5)
            self._graph_thread = None
        self._threads.clear()
        self._workers.clear()
        with self._query_lock:
            if self._query_worker is not None:
                with contextlib.suppress(Exception):
                    self._query_worker.close()
                self._query_worker = None
        if self._llama is not None:
            self._llama.stop()
            self._llama = None
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
        return {
            "paused": self._paused,
            "queued": waiting or 0,
            "active": active,
            "mode": self.mode,
            "reindexing": self._reindexing,
        }

    # ------------------------------------------------------------------- search
    def embedding_model(self) -> CatalogEntry | None:
        """The model of embeddings in use: the chosen one, if it is downloaded."""
        with self.sessions() as db:
            return selection.active(db, self.data_dir, catalog.EMBEDDING)

    def embed_query(self, query: str) -> np.ndarray | None:
        """The vector of a question, or None when there is no model (or it fails). Runs in a
        worker of its own, so it never waits for a long indexing."""
        entry = self.embedding_model()
        if entry is None:
            return None
        with self._query_lock:
            if self._query_worker is None:
                self._query_worker = (
                    ProcessWorker(idle_seconds=QUERY_IDLE_SECONDS)
                    if self.mode == "subprocess"
                    else self._factory()
                )
            try:
                vectors = embeddings.embed(
                    self._query_worker, model_spec(self.data_dir, entry), [query], "query"
                )
            except KnowledgeError as error:
                log.warning("knowledge_query_embedding_failed", message=error.message)
                return None
        return vectors[0]

    def embed_passages(self, texts: list[str]) -> np.ndarray | None:
        """The vectors of some passages (a proposal's chunks), or None without a model. Uses the
        worker that embeds questions, so it never waits behind a long indexing."""
        entry = self.embedding_model()
        if entry is None or not texts:
            return None
        with self._query_lock:
            if self._query_worker is None:
                self._query_worker = (
                    ProcessWorker(idle_seconds=QUERY_IDLE_SECONDS)
                    if self.mode == "subprocess"
                    else self._factory()
                )
            try:
                return embeddings.embed(
                    self._query_worker, model_spec(self.data_dir, entry), texts, "passage"
                )
            except KnowledgeError as error:
                log.warning("knowledge_passage_embedding_failed", message=error.message)
                return None

    def search(
        self,
        db: Session,
        query: str,
        project_id: str | None,
        agent_ids: list[str],
        limit: int = search.DEFAULT_LIMIT,
        use_graph: bool = True,
        docs: list[KnowledgeDoc] | None = None,
        adjacency: Adjacency | None = None,
    ) -> list[search.Hit]:
        """What an agent of `project_id` (and `agent_ids`) finds for `query`. With `use_graph`,
        neighbours of the best results that also fit the question are added after them."""
        entry = self.embedding_model()
        if docs is None:  # the caller may already have them (and the links) from a view
            docs = search.visible_docs(db, project_id, agent_ids)
        expand = knowledge_config.load(db).graph_expand if use_graph else 0
        return search.search(
            db,
            query,
            docs,
            limit=limit,
            embed_query=self.embed_query if entry else None,
            model=entry.id if entry else None,
            graph=(adjacency or Adjacency.build(db, docs)) if expand and entry else None,
            expand=expand,
        )

    # ----------------------------------------------------------------------- reindex
    def stale_docs(self) -> list[str]:
        """Ready documents whose vectors are not the chosen model's (or that have none)."""
        entry = self.embedding_model()
        if entry is None:
            return []
        with self.sessions() as db:
            return list(
                db.scalars(
                    select(KnowledgeDoc.id).where(
                        KnowledgeDoc.workspace_id == DEFAULT_WORKSPACE,
                        KnowledgeDoc.status == DocStatus.READY,
                        KnowledgeDoc.review == Review.NONE,  # a proposal has no index yet
                        KnowledgeDoc.markdown != "",
                        KnowledgeDoc.embed_model != entry.id,
                    )
                )
            )

    def reindex_now(self, worker: Worker | None = None) -> int:
        """Indexes again, here and now, every document that is not indexed with the chosen model.
        The documents stay ready (searchable by words) meanwhile. Returns how many were done."""
        entry = self.embedding_model()
        ids = self.stale_docs()
        if entry is None or not ids:
            return 0
        own = worker or self._factory()
        pipeline = self.pipeline(own)
        done = 0
        try:
            for position, doc_id in enumerate(ids, 1):
                if self._stop.is_set():
                    break
                if pipeline.reindex(doc_id):
                    done += 1
                self.events.reindex({"done": position, "total": len(ids), "model": entry.id})
        finally:
            if worker is None:
                own.close()
        if done:
            self.refresh_graph_now()
        return done

    def reindex(self) -> None:
        """Starts re-indexing in the background (if already running, it checks again when it
        ends, in case the model changed meanwhile). Nothing runs by itself in mode «off»."""
        if self.mode == "off":
            return
        with self._lock:
            if self._reindexing:
                self._reindex_again = True
                return
            self._reindexing = True
        threading.Thread(target=self._reindex_loop, name="knowledge-reindex", daemon=True).start()

    def _reindex_loop(self) -> None:
        try:
            while True:
                self.reindex_now()
                with self._lock:
                    if not self._reindex_again:
                        self._reindexing = False
                        break
                    self._reindex_again = False
        except Exception:
            log.exception("knowledge_reindex_crashed")
            with self._lock:
                self._reindexing = False
        self.events.queue(self.state())
        self.mark_graph_dirty(announce=False)

    def system(self) -> dict:
        """The machine's load now. The first reading of a rate is 0: ask again a second later."""
        if self._sampler is None:
            self._sampler = Sampler()
        return self._sampler.sample()

    # ------------------------------------------------------------------------- the graph
    def mark_graph_dirty(self, *, announce: bool = True) -> None:
        """Something changed that the links between documents depend on (a document was indexed,
        removed, proposed…): they are recomputed soon, once for a burst of changes. `announce`:
        the screens must read the graph again even if no link moved (a document appeared or was
        removed); without it they are told only when a link changed."""
        if announce:
            self._graph_announce = True
        self._graph_dirty.set()

    def refresh_graph_now(self) -> None:
        """Recomputes the «related» links and tells the screens (the tests call this directly)."""
        with self._graph_lock:
            entry = self.embedding_model()
            announce, self._graph_announce = self._graph_announce, False
            with self.sessions() as db:
                limits = knowledge_config.load(db)
                raw = float(entry.usage.get("related_raw", 0.9)) if entry else 0.9
                changed = graph.recompute(
                    db,
                    entry.id if entry else None,
                    threshold=limits.graph_threshold,
                    max_neighbors=limits.graph_max_neighbors,
                    raw_threshold=raw,
                )
                db.commit()
            if changed or announce:
                graph.VERSION += 1
                self.graph_version = graph.VERSION
                self.events.graph(self.graph_version)

    def _graph_loop(self) -> None:
        while not self._stop.is_set():
            self._graph_dirty.wait()
            if self._stop.is_set():
                break
            self._stop.wait(GRAPH_DEBOUNCE)
            self._graph_dirty.clear()
            try:
                self.refresh_graph_now()
            except Exception:
                log.exception("knowledge_graph_failed")

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
            self.mark_graph_dirty()

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
        pipeline = self.pipeline(own)
        done = 0
        try:
            while not self._paused and (doc_id := self.claim_next()) is not None:
                self._run(pipeline, doc_id)
                done += 1
        finally:
            if worker is None:
                own.close()
        if done:
            self.refresh_graph_now()
        return done
