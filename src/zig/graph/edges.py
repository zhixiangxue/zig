from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TYPE_CHECKING

from ..models import Edge

from .validation import validate_identifier, validate_node_id, validate_properties

if TYPE_CHECKING:
    from .graph import Graph


class EdgeSet:
    def __init__(self, graph: Graph) -> None:
        self._graph = graph

    def add(
        self,
        source_id: str,
        relationship_type: str,
        target_id: str,
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        validate_node_id(source_id, field_name="source")
        validate_identifier(relationship_type, field_name="relationship type")
        validate_node_id(target_id, field_name="target")
        edge_properties = properties or {}
        validate_properties(edge_properties)
        edge = Edge(source=source_id, type=relationship_type, target=target_id, properties=edge_properties)
        self._graph._append_operation({"kind": "edge.add", "edge": edge})
        return edge

    def delete(self, source_id: str, relationship_type: str, target_id: str) -> None:
        validate_node_id(source_id, field_name="source")
        validate_identifier(relationship_type, field_name="relationship type")
        validate_node_id(target_id, field_name="target")
        self._graph._append_operation(
            {"kind": "edge.delete", "source": source_id, "type": relationship_type, "target": target_id}
        )

    def add_many(self, edges: Iterable[tuple[str, str, str] | tuple[str, str, str, dict[str, Any]]]) -> list[Edge]:
        added: list[Edge] = []
        for edge in edges:
            if len(edge) == 3:
                source, edge_type, target = edge
                properties: dict[str, Any] = {}
            elif len(edge) == 4:
                source, edge_type, target, properties = edge
            else:
                raise ValueError("edge tuples must be (source, type, target) or (source, type, target, properties)")
            added.append(self.add(source, edge_type, target, properties=properties))
        return added
