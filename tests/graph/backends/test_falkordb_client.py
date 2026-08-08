from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from falkordb.edge import Edge as FalkorEdge
from falkordb.node import Node as FalkorNode
from falkordb.path import Path as FalkorPath

from zig.graph.backends.falkordb.client import FalkorDBClient
from zig.graph.capabilities import PARAMETERIZED_QUERIES, SCHEMA_INTROSPECTION
from zig.graph.uri import ParsedGraphURI
from zig.models import Edge, Node


@dataclass
class DummyResponse:
    result_set: list[Any]
    header: list[Any]


class DummyFalkorGraph:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, Any] | None]] = []

    async def query(self, statement: str, params: dict[str, Any] | None = None) -> DummyResponse:
        self.queries.append((statement, params))
        return DummyResponse(result_set=[["ok"]], header=["result"])


def make_client() -> FalkorDBClient:
    return FalkorDBClient(ParsedGraphURI(backend="falkordb", host="localhost", port=6379, graph="programs"))


def test_falkordb_capabilities() -> None:
    assert FalkorDBClient.query_language == "cypher"
    assert "cypher" in FalkorDBClient.supported_languages
    assert FalkorDBClient.capabilities.supports(PARAMETERIZED_QUERIES)
    assert FalkorDBClient.capabilities.supports(SCHEMA_INTROSPECTION)


async def test_falkordb_query_result_conversion_without_real_server() -> None:
    client = make_client()
    graph = DummyFalkorGraph()
    client._graph = graph

    result = await client.query("RETURN 1", language="cypher")

    assert result.records == [{"result": "ok"}]
    assert result.columns == ["result"]
    assert graph.queries == [("RETURN 1", None)]


def test_falkordb_extracts_alias_from_typed_header() -> None:
    client = make_client()
    response = DummyResponse(
        result_set=[["MyHome", "CalHFA", 2024]],
        header=[("column", "program"), ["column", "agency"], (1, "since")],
    )

    result = client._to_query_result(response)

    assert result.columns == ["program", "agency", "since"]
    assert result.records == [{"program": "MyHome", "agency": "CalHFA", "since": 2024}]


def test_falkordb_serializes_graph_objects_inside_records() -> None:
    client = make_client()
    program = FalkorNode(node_id=1, labels="Program", properties={"id": "p1", "name": "MyHome"})
    requirement = FalkorNode(
        node_id=2,
        labels="Requirement",
        properties={"id": "r1", "name": "First-time buyer"},
    )
    relationship = FalkorEdge(
        program,
        "HAS_REQUIREMENT",
        requirement,
        edge_id=10,
        properties={"priority": 1},
    )
    response = DummyResponse(
        result_set=[[program, relationship, {"nested": [relationship]}]],
        header=["program", "relationship", "payload"],
    )

    result = client._to_query_result(response)

    serialized_program = {"label": "Program", "properties": {"id": "p1", "name": "MyHome"}}
    serialized_requirement = {
        "label": "Requirement",
        "properties": {"id": "r1", "name": "First-time buyer"},
    }
    serialized_relationship = {
        "type": "HAS_REQUIREMENT",
        "properties": {"priority": 1},
        "source": serialized_program,
        "target": serialized_requirement,
    }
    assert result.records == [
        {
            "program": serialized_program,
            "relationship": serialized_relationship,
            "payload": {"nested": [serialized_relationship]},
        }
    ]
    json.dumps(result.records)


def test_falkordb_serializes_path_edges_with_endpoint_nodes() -> None:
    client = make_client()
    program = FalkorNode(node_id=1, labels="Program", properties={"id": "p1"})
    requirement = FalkorNode(node_id=2, labels="Requirement", properties={"id": "r1"})
    path = FalkorPath([program, requirement], [FalkorEdge(1, "HAS_REQUIREMENT", 2)])
    response = DummyResponse(result_set=[[path]], header=["path"])

    result = client._to_query_result(response)

    assert result.records == [
        {
            "path": {
                "nodes": [
                    {"label": "Program", "properties": {"id": "p1"}},
                    {"label": "Requirement", "properties": {"id": "r1"}},
                ],
                "relationships": [
                    {
                        "type": "HAS_REQUIREMENT",
                        "properties": {},
                        "source": {"label": "Program", "properties": {"id": "p1"}},
                        "target": {"label": "Requirement", "properties": {"id": "r1"}},
                    }
                ],
            }
        }
    ]
    json.dumps(result.records)


async def test_falkordb_commit_translates_pending_operations_without_real_server() -> None:
    client = make_client()
    graph = DummyFalkorGraph()
    client._graph = graph

    await client.commit(
        [
            {"kind": "node.upsert", "node": Node(id="p1", label="Program", properties={"name": "MyHome"})},
            {"kind": "edge.add", "edge": Edge(source="p1", type="OFFERED_BY", target="a1", properties={"since": 2024})},
        ]
    )

    assert "MERGE (n:Program" in graph.queries[0][0]
    assert graph.queries[0][1] == {"id": "p1", "properties": {"id": "p1", "name": "MyHome"}}
    assert "MERGE (source)-[r:OFFERED_BY]->(target)" in graph.queries[1][0]
    assert graph.queries[1][1] == {"source": "p1", "target": "a1", "properties": {"since": 2024}}
