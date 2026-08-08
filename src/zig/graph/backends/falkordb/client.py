from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from falkordb.asyncio import FalkorDB
from falkordb.edge import Edge as FalkorEdge
from falkordb.node import Node as FalkorNode
from falkordb.path import Path as FalkorPath

from ....exceptions import GraphOperationError, UnsupportedQueryLanguageError
from ....models import GraphSchema, Node, QueryResult
from ...base import AbstractGraphClient, GraphOperation
from ...capabilities import BackendCapabilities, INDEXES, PARAMETERIZED_QUERIES, SCHEMA_INTROSPECTION


class FalkorDBClient(AbstractGraphClient):
    query_language = "cypher"
    supported_languages = frozenset({"cypher"})
    capabilities = BackendCapabilities(
        frozenset(
            {
                PARAMETERIZED_QUERIES,
                SCHEMA_INTROSPECTION,
                INDEXES,
            }
        )
    )

    def __init__(self, uri) -> None:
        super().__init__(uri)
        self._db: FalkorDB | None = None
        self._graph: Any | None = None

    async def connect(self) -> None:
        if self._graph is not None:
            return None

        kwargs: dict[str, Any] = {
            "host": self.uri.host,
            "port": self.uri.port or 6379,
        }
        if self.uri.username:
            kwargs["username"] = self.uri.username
        if self.uri.password:
            kwargs["password"] = self.uri.password

        self._db = FalkorDB(**kwargs)
        self._graph = self._db.select_graph(self.uri.graph)
        return None

    async def close(self) -> None:
        if self._db is None:
            return None
        close = getattr(self._db, "aclose", None) or getattr(self._db, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
        self._db = None
        self._graph = None
        return None

    async def commit(self, operations: Sequence[GraphOperation]) -> None:
        for operation in operations:
            await self._apply_operation(operation)
        return None

    async def query(
        self,
        statement: str,
        *,
        language: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Execute a Cypher statement with optional parameterized query bindings."""
        query_language = language or self.query_language
        if query_language not in self.supported_languages:
            raise UnsupportedQueryLanguageError(f"FalkorDB does not support query language {query_language!r}")
        response = await self._run(statement, params)
        return self._to_query_result(response)

    async def get_node(self, node_id: str) -> Node | None:
        response = await self._run(
            "MATCH (n {id: $id}) RETURN labels(n) AS labels, properties(n) AS properties LIMIT 1",
            {"id": node_id},
        )
        rows = getattr(response, "result_set", [])
        if not rows:
            return None
        row = rows[0]
        labels = row[0] if row else []
        properties = row[1] if len(row) > 1 else {}
        label = labels[0] if labels else "Node"
        properties = dict(properties or {})
        node_id = str(properties.pop("id", node_id))
        return Node(id=node_id, label=label, properties=properties)

    async def schema(self) -> GraphSchema:
        labels_result = await self._run("MATCH (n) UNWIND labels(n) AS label RETURN DISTINCT label")
        rels_result = await self._run("MATCH ()-[r]->() RETURN DISTINCT type(r)")
        labels = [row[0] for row in getattr(labels_result, "result_set", [])]
        relationship_types = [row[0] for row in getattr(rels_result, "result_set", [])]
        return GraphSchema(labels=labels, relationship_types=relationship_types)

    async def _apply_operation(self, operation: GraphOperation) -> None:
        kind = operation["kind"]
        if kind == "node.add":
            node = operation["node"]
            await self._merge_node(node)
            return None
        if kind == "node.upsert":
            node = operation["node"]
            await self._merge_node(node)
            return None
        if kind == "node.update":
            await self._run(
                "MATCH (n {id: $id}) SET n += $properties",
                {"id": operation["id"], "properties": operation["properties"]},
            )
            return None
        if kind == "node.delete":
            await self._run("MATCH (n {id: $id}) DETACH DELETE n", {"id": operation["id"]})
            return None
        if kind == "edge.add":
            edge = operation["edge"]
            await self._run(
                f"MATCH (source {{id: $source}}), (target {{id: $target}}) "
                f"MERGE (source)-[r:{edge.type}]->(target) SET r += $properties",
                {"source": edge.source, "target": edge.target, "properties": edge.properties},
            )
            return None
        if kind == "edge.delete":
            await self._run(
                f"MATCH (source {{id: $source}})-[r:{operation['type']}]->(target {{id: $target}}) DELETE r",
                {"source": operation["source"], "target": operation["target"]},
            )
            return None
        raise GraphOperationError(f"Unknown graph operation kind: {kind!r}")

    async def _merge_node(self, node: Node) -> None:
        properties = {"id": node.id, **node.properties}
        await self._run(
            f"MERGE (n:{node.label} {{id: $id}}) SET n += $properties",
            {"id": node.id, "properties": properties},
        )

    async def _run(self, statement: str, params: dict[str, Any] | None = None) -> Any:
        await self.connect()
        if self._graph is None:
            raise GraphOperationError("FalkorDB graph is not connected")
        if params is None:
            return await self._graph.query(statement)
        try:
            return await self._graph.query(statement, params=params)
        except TypeError:
            return await self._graph.query(statement, params)

    def _to_query_result(self, response: Any) -> QueryResult:
        rows = list(getattr(response, "result_set", []) or [])
        columns = self._extract_columns(response)
        records = self._rows_to_records(rows, columns)
        return QueryResult(records=records, columns=columns, raw=response)

    def _extract_columns(self, response: Any) -> list[str]:
        header = getattr(response, "header", None) or []
        columns: list[str] = []
        for item in header:
            if isinstance(item, str):
                columns.append(item)
            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                columns.append(str(item[1]))
            elif isinstance(item, (tuple, list)) and item:
                columns.append(str(item[0]))
            else:
                columns.append(str(item))
        return columns

    def _rows_to_records(self, rows: list[Any], columns: list[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for row in rows:
            if columns and isinstance(row, (list, tuple)):
                record = {
                    column: self._serialize_value(row[index])
                    for index, column in enumerate(columns)
                    if index < len(row)
                }
                records.append(record)
            else:
                records.append({"value": self._serialize_value(row)})
        return records

    def _serialize_value(self, value: Any) -> Any:
        """Convert FalkorDB graph values in query records to JSON-friendly structures."""
        if isinstance(value, FalkorNode):
            return self._serialize_node(value)
        if isinstance(value, FalkorEdge):
            return self._serialize_edge(value)
        if isinstance(value, FalkorPath):
            return self._serialize_path(value)
        if isinstance(value, dict):
            return {str(key): self._serialize_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._serialize_value(item) for item in value]
        if hasattr(value, "model_dump"):
            return self._serialize_value(value.model_dump())
        return value

    def _serialize_node(self, node: FalkorNode) -> dict[str, Any]:
        labels = list(node.labels or [])
        label = labels[0] if labels else "Node"
        return {
            "label": label,
            "properties": self._serialize_value(dict(node.properties or {})),
        }

    def _serialize_edge(
        self,
        edge: FalkorEdge,
        nodes_by_id: dict[Any, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": edge.relation,
            "properties": self._serialize_value(dict(edge.properties or {})),
            "source": self._serialize_edge_endpoint(edge.src_node, nodes_by_id),
            "target": self._serialize_edge_endpoint(edge.dest_node, nodes_by_id),
        }

    def _serialize_edge_endpoint(
        self,
        endpoint: Any,
        nodes_by_id: dict[Any, dict[str, Any]] | None = None,
    ) -> Any:
        if isinstance(endpoint, FalkorNode):
            return self._serialize_node(endpoint)
        if nodes_by_id is not None and endpoint in nodes_by_id:
            return nodes_by_id[endpoint]
        if isinstance(endpoint, (str, int)):
            return {"id": endpoint}
        return self._serialize_value(endpoint)

    def _serialize_path(self, path: FalkorPath) -> dict[str, Any]:
        nodes = [self._serialize_node(node) for node in path.nodes()]
        nodes_by_id = {
            node.id: serialized
            for node, serialized in zip(path.nodes(), nodes)
            if node.id is not None
        }
        return {
            "nodes": nodes,
            "relationships": [self._serialize_edge(edge, nodes_by_id) for edge in path.edges()],
        }
