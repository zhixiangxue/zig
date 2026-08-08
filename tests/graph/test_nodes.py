from __future__ import annotations

import pytest

from zig import Graph
from zig.exceptions import GraphOperationError

from tests.conftest import FakeGraphClient


def test_node_add_appends_pending_operation() -> None:
    graph = Graph("fake://localhost:1234/programs")

    node = graph.node.add("Program", id="p1", properties={"name": "MyHome", "amount": 50000})

    assert node.id == "p1"
    assert node.label == "Program"
    assert node.properties == {"name": "MyHome", "amount": 50000}
    assert graph._pending_operations[0]["kind"] == "node.add"


def test_node_update_delete_upsert_append_operations() -> None:
    graph = Graph("fake://localhost:1234/programs")

    graph.node.update("p1", properties={"amount": 60000})
    graph.node.upsert("Program", id="p1", properties={"name": "MyHome"})
    graph.node.delete("p1")

    assert [operation["kind"] for operation in graph._pending_operations] == [
        "node.update",
        "node.upsert",
        "node.delete",
    ]


def test_node_add_many() -> None:
    graph = Graph("fake://localhost:1234/programs")

    nodes = graph.node.add_many([
        ("Program", {"id": "p1", "name": "MyHome"}),
        ("Agency", {"id": "a1", "name": "CalHFA"}),
    ])

    assert [node.id for node in nodes] == ["p1", "a1"]
    assert len(graph._pending_operations) == 2


def test_node_add_allows_label_property() -> None:
    graph = Graph("fake://localhost:1234/programs")

    node = graph.node.add("Fact", id="fact:property.city", properties={"label": "City"})

    assert node.label == "Fact"
    assert node.properties == {"label": "City"}


@pytest.mark.parametrize("label", ["Bad Label", "123Label", "Program-Name"])
def test_node_rejects_invalid_label(label: str) -> None:
    graph = Graph("fake://localhost:1234/programs")

    with pytest.raises(GraphOperationError):
        graph.node.add(label, id="p1")


def test_node_rejects_invalid_property_key() -> None:
    graph = Graph("fake://localhost:1234/programs")

    with pytest.raises(GraphOperationError):
        graph.node.add("Program", id="p1", properties={"bad-key": "value"})


async def test_node_get_delegates_to_backend() -> None:
    graph = Graph("fake://localhost:1234/programs")

    node = await graph.node.get("p1")

    assert node is not None
    assert node.id == "p1"
    assert FakeGraphClient.instances[-1].connected
