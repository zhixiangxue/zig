from __future__ import annotations

import pytest

from zig import Graph
from zig.exceptions import InvalidGraphURIError, UnsupportedCapabilityError, UnsupportedQueryLanguageError
from zig.graph.capabilities import PARAMETERIZED_QUERIES

from tests.conftest import FakeGraphClient


def test_graph_parses_uri() -> None:
    graph = Graph("fake://user:pass@localhost:1234/programs")

    assert graph.uri.backend == "fake"
    assert graph.uri.username == "user"
    assert graph.uri.password == "pass"
    assert graph.uri.host == "localhost"
    assert graph.uri.port == 1234
    assert graph.uri.graph == "programs"


@pytest.mark.parametrize("uri", ["fake://localhost:1234", "fake:///programs", "localhost:1234/programs"])
def test_graph_rejects_invalid_uri(uri: str) -> None:
    with pytest.raises(InvalidGraphURIError):
        Graph(uri)


def test_graph_supports_capabilities() -> None:
    graph = Graph("fake://localhost:1234/programs")

    assert graph.supports(PARAMETERIZED_QUERIES)
    assert not graph.supports("nlq")


async def test_execute_delegates_to_backend() -> None:
    graph = Graph("fake://localhost:1234/programs")

    result = await graph.execute("MATCH (n) RETURN n", language="cypher")

    assert result.records == [{"statement": "MATCH (n) RETURN n"}]
    assert FakeGraphClient.instances[-1].executed == [("MATCH (n) RETURN n", "cypher", None)]


async def test_execute_rejects_unsupported_language() -> None:
    graph = Graph("fake://localhost:1234/programs")

    with pytest.raises(UnsupportedQueryLanguageError):
        await graph.execute("FOR n IN nodes RETURN n", language="aql")


async def test_query_is_nlq_stub_when_capability_missing() -> None:
    graph = Graph("fake://localhost:1234/programs")

    with pytest.raises(UnsupportedCapabilityError):
        await graph.query("有哪些 Program？")


def test_graph_rollback_discards_pending_operations() -> None:
    graph = Graph("fake://localhost:1234/programs")
    graph.node.add("Program", id="p1", properties={"name": "MyHome"})

    graph.rollback()

    assert graph._pending_operations == []


async def test_async_context_commits_on_success() -> None:
    async with Graph("fake://localhost:1234/programs") as graph:
        graph.node.add("Program", id="p1", properties={"name": "MyHome"})

    client = FakeGraphClient.instances[-1]
    assert client.closed
    assert len(client.committed_operations) == 1


async def test_async_context_discards_pending_operations_on_exception() -> None:
    with pytest.raises(RuntimeError):
        async with Graph("fake://localhost:1234/programs") as graph:
            graph.node.add("Program", id="p1", properties={"name": "MyHome"})
            raise RuntimeError("boom")

    client = FakeGraphClient.instances[-1]
    assert client.closed
    assert client.committed_operations == []
