from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from zig.graph.base import AbstractGraphClient, GraphOperation
from zig.graph.capabilities import BackendCapabilities, PARAMETERIZED_QUERIES
from zig.graph.registry import BackendRegistry
from zig.models import GraphSchema, Node, QueryResult


class FakeGraphClient(AbstractGraphClient):
    query_language = "cypher"
    supported_languages = frozenset({"cypher"})
    capabilities = BackendCapabilities(frozenset({PARAMETERIZED_QUERIES}))
    instances: list[FakeGraphClient] = []

    def __init__(self, uri) -> None:
        super().__init__(uri)
        self.connected = False
        self.closed = False
        self.committed_operations: list[GraphOperation] = []
        self.executed: list[tuple[str, str | None, dict[str, Any] | None]] = []
        FakeGraphClient.instances.append(self)

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True

    async def commit(self, operations: Sequence[GraphOperation]) -> None:
        self.committed_operations.extend(operations)

    async def query(
        self,
        statement: str,
        *,
        language: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Record the executed statement along with language and params."""
        self.executed.append((statement, language, params))
        return QueryResult(records=[{"statement": statement}], columns=["statement"])

    async def get_node(self, node_id: str) -> Node | None:
        return Node(id=node_id, label="Fake", properties={"name": "fake"})

    async def schema(self) -> GraphSchema:
        return GraphSchema(labels=["Fake"], relationship_types=["RELATED_TO"])


BackendRegistry.register("fake", FakeGraphClient)
