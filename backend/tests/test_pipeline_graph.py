"""The shape of a pipeline (phase 13): forks, joins, lanes and where a rejection may go."""

from __future__ import annotations

from agentic_os.services.pipeline_graph import Edge, Graph, GraphErrorCode

Code = GraphErrorCode


def graph(
    links: list[tuple[str, str]], rejects: dict[str, str] | None = None, nodes: str | None = None
) -> Graph:
    names = list(nodes) if nodes else sorted({n for link in links for n in link})
    edges = [Edge(f"{a}{b}", a, b, position=i) for i, (a, b) in enumerate(links)]
    return Graph(names, edges, rejects)


def codes(g: Graph) -> list[str]:
    return [e.code for e in g.validate()]


# A → B → C
LINEAR = [("A", "B"), ("B", "C")]
# A → (B | C) → D
DIAMOND = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
# A → (B → B2 | C) → D → E
LONG = [("A", "B"), ("B", "B2"), ("A", "C"), ("B2", "D"), ("C", "D"), ("D", "E")]


def test_a_chain_is_valid_and_has_no_forks():
    g = graph(LINEAR)
    assert g.validate() == []
    assert g.start() == "A" and g.next_of("A") == "B" and g.next_of("C") is None
    assert not g.is_fork("B")


def test_a_fork_closes_in_its_join_and_knows_its_lanes():
    g = graph(DIAMOND, {"D": "B"})
    assert g.validate() == []
    assert g.is_fork("A") and g.next_of("A") is None
    assert g.join_of("A") == "D"
    assert g.lane_stages("A", 0) == ["B"] and g.lane_stages("A", 1) == ["C"]
    assert g.path_of("A") == () and g.path_of("B") == (("A", 0),) and g.path_of("D") == ()


def test_lanes_can_be_longer_than_one_stage():
    g = graph(LONG)
    assert g.validate() == []
    assert g.lane_stages("A", 0) == ["B", "B2"]
    assert g.path_of("B2") == (("A", 0),)


def test_branches_that_never_meet_end_in_final_stages():
    g = graph([("A", "B"), ("A", "C")])
    assert g.validate() == []
    assert g.join_of("A") is None
    assert g.lane_stages("A", 1) == ["C"]


def test_forks_nest_inside_a_branch():
    # A → (B → (X | Y) → Z | C) → D
    g = graph(
        [
            ("A", "B"),
            ("A", "C"),
            ("B", "X"),
            ("B", "Y"),
            ("X", "Z"),
            ("Y", "Z"),
            ("Z", "D"),
            ("C", "D"),
        ]
    )
    assert g.validate() == []
    assert g.join_of("A") == "D" and g.join_of("B") == "Z"
    assert g.lane_stages("A", 0) == ["B", "X", "Y", "Z"]
    assert g.path_of("X") == (("A", 0), ("B", 0))
    assert g.path_of("Z") == (("A", 0),)


def test_a_graph_needs_exactly_one_start():
    assert Code.MANY_STARTS in codes(graph([("A", "C"), ("B", "C")]))
    assert Code.NO_START in codes(graph([], nodes=""))
    assert Code.CYCLE in codes(graph([("A", "B"), ("B", "C"), ("C", "B")]))


def test_a_cycle_without_start_is_reported_too():
    found = codes(graph([("A", "B"), ("B", "A")]))
    assert Code.NO_START in found and Code.CYCLE in found


def test_a_fork_branch_without_condition_is_valid():
    # Phase 21: a branch without a condition is always taken, nothing to report.
    edges = [Edge("ab", "A", "B", 0), Edge("ac", "A", "C", 1), Edge("bd", "B", "D", 0)]
    edges.append(Edge("cd", "C", "D", 0))
    assert Graph(list("ABCD"), edges).validate() == []


def test_lanes_must_not_cross():
    # B can go on to C, which belongs to the other branch
    crossing = [("A", "B"), ("A", "C"), ("B", "D"), ("B", "C"), ("C", "D")]
    assert Code.UNSTRUCTURED in codes(graph(crossing))


def test_a_branch_cannot_be_empty():
    g = graph([("A", "B"), ("A", "C"), ("B", "C")])  # one branch is the join itself
    assert Code.EMPTY_BRANCH in codes(g)


def test_a_nested_fork_cannot_close_on_the_outer_join():
    # A → (B → (X | Y) | C) → D, with X and Y going straight to D
    nested = [("A", "B"), ("A", "C"), ("B", "X"), ("B", "Y"), ("X", "D"), ("Y", "D"), ("C", "D")]
    assert Code.UNSTRUCTURED in codes(graph(nested))


def test_a_rejection_goes_back_to_an_earlier_stage_of_the_path():
    assert graph(LINEAR, {"C": "A"}).validate() == []
    assert codes(graph(LINEAR, {"A": "C"})) == [Code.REJECT_NOT_BACKWARDS]
    assert codes(graph(LINEAR, {"B": "B"})) == [Code.REJECT_NOT_BACKWARDS]


def test_after_a_join_a_stage_can_reject_to_any_branch_or_before_the_fork():
    for target in ("A", "B", "C"):
        assert graph(DIAMOND, {"D": target}).validate() == [], target
    longer = graph([*LONG, ("E", "F")], {"F": "B"})
    assert longer.validate() == []


def test_inside_a_branch_a_stage_only_rejects_within_that_branch():
    assert graph(LONG, {"B2": "B"}).validate() == []
    # back to the stage before the fork would stop the sibling branch
    assert codes(graph(LONG, {"B2": "A"})) == [Code.REJECT_OUTSIDE_PATH]
    # the sibling branch is not an earlier stage at all
    assert codes(graph(LONG, {"B2": "C"})) == [Code.REJECT_NOT_BACKWARDS]


def test_the_default_layout_puts_each_depth_in_a_column():
    spots = graph(DIAMOND).layout()
    assert spots["A"][0] < spots["B"][0] == spots["C"][0] < spots["D"][0]
    assert spots["B"][1] != spots["C"][1]
