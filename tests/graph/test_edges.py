from __future__ import annotations

import pytest

from zig import Graph
from zig.exceptions import GraphOperationError


def test_edge_add_appends_pending_operation() -> None:
    graph = Graph("fake://localhost:1234/programs")

    edge = graph.edge.add("p1", "OFFERED_BY", "a1", properties={"since": 2024, "source": "calhfa"})

    assert edge.source == "p1"
    assert edge.type == "OFFERED_BY"
    assert edge.target == "a1"
    assert edge.properties == {"since": 2024, "source": "calhfa"}
    assert graph._pending_operations[0]["kind"] == "edge.add"


def test_edge_delete_appends_pending_operation() -> None:
    graph = Graph("fake://localhost:1234/programs")

    graph.edge.delete("p1", "OFFERED_BY", "a1")

    assert graph._pending_operations == [
        {"kind": "edge.delete", "source": "p1", "type": "OFFERED_BY", "target": "a1"}
    ]


def test_edge_add_many() -> None:
    graph = Graph("fake://localhost:1234/programs")

    edges = graph.edge.add_many([
        ("p1", "OFFERED_BY", "a1"),
        ("p2", "OFFERED_BY", "a2", {"since": 2024}),
    ])

    assert len(edges) == 2
    assert edges[1].properties == {"since": 2024}
    assert len(graph._pending_operations) == 2


@pytest.mark.parametrize("edge_type", ["Bad Type", "123TYPE", "TYPE-NAME"])
def test_edge_rejects_invalid_type(edge_type: str) -> None:
    graph = Graph("fake://localhost:1234/programs")

    with pytest.raises(GraphOperationError):
        graph.edge.add("p1", edge_type, "a1")


def test_edge_rejects_invalid_property_key() -> None:
    graph = Graph("fake://localhost:1234/programs")

    with pytest.raises(GraphOperationError):
        graph.edge.add("p1", "OFFERED_BY", "a1", properties={"bad-key": "value"})
