"""The shape of a pipeline (phase 13, ADR 0020): stages joined by links, with forks and joins.

Pure code on plain ids, no database: the editor's rules live here and are mirrored in the
frontend (`validate.ts`), and the engine asks it where a task goes next.

A pipeline is a *structured* graph: a stage with several outgoing links is a fork, each of its
links is a branch, and all the branches meet again in a single stage, the join (or all end in
final stages). Forks nest inside a branch. Rejection arrows are not links: they go back to an
earlier stage of the same path and are checked here too.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class GraphErrorCode(StrEnum):
    NO_START = "no_start"
    MANY_STARTS = "many_starts"
    UNREACHABLE = "unreachable"
    CYCLE = "cycle"
    UNSTRUCTURED = "unstructured"
    EMPTY_BRANCH = "empty_branch"
    BRANCH_WITHOUT_CONDITION = "branch_without_condition"
    REJECT_NOT_BACKWARDS = "reject_not_backwards"
    REJECT_OUTSIDE_PATH = "reject_outside_path"


@dataclass(frozen=True)
class GraphError:
    code: GraphErrorCode
    stage: str | None = None
    link: str | None = None


@dataclass(frozen=True)
class Edge:
    id: str
    src: str
    dst: str
    position: int = 0  # order among the links leaving the same stage
    labelled: bool = True  # has a condition, or is «always»: required in a fork's branches


# A position inside the forks: ((fork, branch index), …) from the outermost one.
Path = tuple[tuple[str, int], ...]


class Graph:
    """`nodes` are stage ids in editor order, `rejects` maps a stage to the stage (or stages) it
    can send tasks back to. Call `validate()` before trusting the structure queries."""

    def __init__(
        self,
        nodes: list[str],
        edges: list[Edge],
        rejects: Mapping[str, str | list[str]] | None = None,
    ) -> None:
        self.nodes = list(nodes)
        self.rejects: dict[str, list[str]] = {
            stage: [targets] if isinstance(targets, str) else list(targets)
            for stage, targets in (rejects or {}).items()
        }
        self.out: dict[str, list[Edge]] = {n: [] for n in self.nodes}
        self.inc: dict[str, list[Edge]] = {n: [] for n in self.nodes}
        for edge in sorted(edges, key=lambda e: e.position):
            self.out[edge.src].append(edge)
            self.inc[edge.dst].append(edge)
        self._forward: dict[str, frozenset[str]] = {}
        self._order: list[str] = []
        self._paths: dict[str, Path] = {}
        self._joins: dict[str, str | None] = {}
        self._lanes: dict[str, list[list[str]]] = {}
        self._structure_ok = False

    # ----------------------------------------------------------------------- validation
    def validate(self) -> list[GraphError]:
        errors: list[GraphError] = []
        starts = [n for n in self.nodes if not self.inc[n]]
        if not starts:
            errors.append(GraphError(GraphErrorCode.NO_START))
        errors += [GraphError(GraphErrorCode.MANY_STARTS, s) for s in starts[1:]]

        cyclic = self._topological_order()
        errors += [GraphError(GraphErrorCode.CYCLE, n) for n in cyclic]

        for node in self.nodes:
            outs = self.out[node]
            if len(outs) > 1:
                errors += [
                    GraphError(GraphErrorCode.BRANCH_WITHOUT_CONDITION, node, e.id)
                    for e in outs
                    if not e.labelled
                ]

        if not cyclic and len(starts) == 1:
            structure = self._analyse(starts[0])
            errors += structure
            self._structure_ok = not structure
            reached = set(self._paths)
            errors += [
                GraphError(GraphErrorCode.UNREACHABLE, n)
                for n in self.nodes
                if n not in reached and not structure
            ]
        errors += self._reject_errors()
        return errors

    def _topological_order(self) -> list[str]:
        """Fills the topological order; returns the stages left in cycles."""
        degree = {n: len(self.inc[n]) for n in self.nodes}
        ready = [n for n in self.nodes if degree[n] == 0]
        order: list[str] = []
        while ready:
            node = ready.pop(0)
            order.append(node)
            for edge in self.out[node]:
                degree[edge.dst] -= 1
                if degree[edge.dst] == 0:
                    ready.append(edge.dst)
        self._order = order
        return [n for n in self.nodes if n not in set(order)]

    def forward(self, node: str) -> frozenset[str]:
        """Every stage reachable from `node` through links (not counting itself)."""
        cached = self._forward.get(node)
        if cached is not None:
            return cached
        self._forward[node] = frozenset()  # guards against cycles
        found: set[str] = set()
        for edge in self.out[node]:
            found.add(edge.dst)
            found |= self.forward(edge.dst)
        self._forward[node] = frozenset(found)
        return self._forward[node]

    def _join_of_fork(self, fork: str) -> str | None:
        """The first stage every branch reaches (None when they never meet)."""
        reaches = [{e.dst} | self.forward(e.dst) for e in self.out[fork]]
        common = set.intersection(*reaches)
        for node in self._order:
            if node in common:
                return node
        return None

    def _analyse(self, start: str) -> list[GraphError]:
        self._paths, self._joins, self._lanes = {}, {}, {}
        errors: list[GraphError] = []
        self._walk(start, (), None, errors)
        return errors

    def _walk(self, node: str | None, path: Path, stop: str | None, errors: list[GraphError]):
        while node is not None and node != stop:
            if node in self._paths:  # reached from two places that are not a join
                errors.append(GraphError(GraphErrorCode.UNSTRUCTURED, node))
                return
            self._paths[node] = path
            outs = self.out[node]
            if not outs:
                return
            if len(outs) == 1:
                node = outs[0].dst
                continue
            join = self._join_of_fork(node)
            self._joins[node] = join
            if join is not None and join == stop:  # two levels of forks closing on one stage
                errors.append(GraphError(GraphErrorCode.UNSTRUCTURED, node))
                return
            lanes: list[list[str]] = []
            for index, edge in enumerate(outs):
                if edge.dst == join:
                    errors.append(GraphError(GraphErrorCode.EMPTY_BRANCH, node, edge.id))
                    lanes.append([])
                    continue
                before = set(self._paths)
                self._walk(edge.dst, (*path, (node, index)), join, errors)
                lanes.append([n for n in self._paths if n not in before])
            self._lanes[node] = lanes
            node = join

    def _reject_errors(self) -> list[GraphError]:
        errors: list[GraphError] = []
        for stage, targets in self.rejects.items():
            for target in targets:
                if stage == target or stage not in self.forward(target):
                    errors.append(GraphError(GraphErrorCode.REJECT_NOT_BACKWARDS, stage))
                elif self._structure_ok:
                    mine, theirs = self._paths[stage], self._paths[target]
                    # Inside a branch a stage can only send tasks back within that branch:
                    # going further back would stop the sibling branches.
                    if theirs[: len(mine)] != mine:
                        errors.append(GraphError(GraphErrorCode.REJECT_OUTSIDE_PATH, stage))
        return errors

    # ------------------------------------------------------------------------- queries
    def start(self) -> str | None:
        starts = [n for n in self.nodes if not self.inc[n]]
        return starts[0] if len(starts) == 1 else None

    def is_fork(self, stage: str) -> bool:
        return len(self.out[stage]) > 1

    def next_of(self, stage: str) -> str | None:
        """The stage after one that does not fork (None at a final stage)."""
        outs = self.out[stage]
        return outs[0].dst if len(outs) == 1 else None

    def join_of(self, fork: str) -> str | None:
        return self._joins.get(fork)

    def lane_stages(self, fork: str, branch: int) -> list[str]:
        """The stages of one branch of a fork (nested forks included), join excluded."""
        return self._lanes[fork][branch]

    def path_of(self, stage: str) -> Path:
        return self._paths[stage]

    def layout(self) -> dict[str, tuple[int, int]]:
        """A readable default place for every stage: columns by depth, rows in editor order."""
        depth: dict[str, int] = {}
        for node in self._order or self.nodes:
            depth[node] = max(
                (depth[e.src] + 1 for e in self.inc[node] if e.src in depth), default=0
            )
        rows: dict[int, int] = {}
        placed: dict[str, tuple[int, int]] = {}
        for node in self.nodes:
            column = depth.get(node, 0)
            row = rows.get(column, 0)
            rows[column] = row + 1
            placed[node] = (column * 280, row * 150)
        return placed
