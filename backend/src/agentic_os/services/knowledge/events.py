"""Live events of the knowledge library (phase 14): a document's state and progress, the queue,
model downloads and the machine's load. Same hub as the Git tab's; every WebSocket client reads
its own queue."""

from __future__ import annotations

from agentic_os.services.gitx.events import GitEvents


class KnowledgeEvents(GitEvents):
    def doc(self, payload: dict) -> None:
        """A document changed (state, progress, error…): `payload` is its `DocRead`."""
        self.publish({"type": "doc", "doc": payload})

    def doc_removed(self, doc_id: str) -> None:
        self.publish({"type": "doc_removed", "id": doc_id})

    def queue(self, payload: dict) -> None:
        self.publish({"type": "queue", **payload})

    def reindex(self, payload: dict) -> None:
        """The documents are being indexed again with another model: `{done, total, model}`."""
        self.publish({"type": "reindex", **payload})

    def model(self, payload: dict) -> None:
        """A local model's download changed: `{id, state, done, total, error_code…}`."""
        self.publish({"type": "model", **payload})

    def graph(self, version: int) -> None:
        """The links between documents changed: whoever shows the graph reads it again."""
        self.publish({"type": "graph", "version": version})
