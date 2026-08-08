from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TYPE_CHECKING

from ..models import Node

from .validation import validate_identifier, validate_node_id, validate_properties

if TYPE_CHECKING:
    from .graph import Graph


class NodeSet:
    def __init__(self, graph: Graph) -> None:
        self._graph = graph

    def add(self, label: str, *, id: str, properties: dict[str, Any] | None = None) -> Node:
        validate_identifier(label, field_name="label")
        validate_node_id(id)
        node_properties = properties or {}
        validate_properties(node_properties)
        node = Node(id=id, label=label, properties=node_properties)
        self._graph._append_operation({"kind": "node.add", "node": node})
        return node

    def update(self, id: str, properties: dict[str, Any]) -> None:
        validate_node_id(id)
        validate_properties(properties)
        self._graph._append_operation({"kind": "node.update", "id": id, "properties": properties})

    def upsert(self, label: str, *, id: str, properties: dict[str, Any] | None = None) -> Node:
        validate_identifier(label, field_name="label")
        validate_node_id(id)
        node_properties = properties or {}
        validate_properties(node_properties)
        node = Node(id=id, label=label, properties=node_properties)
        self._graph._append_operation({"kind": "node.upsert", "node": node})
        return node

    def delete(self, id: str) -> None:
        validate_node_id(id)
        self._graph._append_operation({"kind": "node.delete", "id": id})

    async def get(self, id: str) -> Node | None:
        validate_node_id(id)
        await self._graph._ensure_connected()
        return await self._graph._client.get_node(id)

    def add_many(self, nodes: Iterable[tuple[str, dict[str, Any]]]) -> list[Node]:
        added: list[Node] = []
        for label, properties in nodes:
            node_id = validate_node_id(properties.get("id"), field_name="id")
            node_properties = {key: value for key, value in properties.items() if key != "id"}
            added.append(self.add(label, id=node_id, properties=node_properties))
        return added
