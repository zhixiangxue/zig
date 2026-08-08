from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from ..models import GraphSchema, Node, QueryResult

from .capabilities import BackendCapabilities
from .uri import ParsedGraphURI

GraphOperation = dict[str, Any]


class AbstractGraphClient(ABC):
    query_language: str
    supported_languages: frozenset[str]
    capabilities: BackendCapabilities

    def __init__(self, uri: ParsedGraphURI) -> None:
        self.uri = uri

    @abstractmethod
    async def connect(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        return None

    @abstractmethod
    async def commit(self, operations: Sequence[GraphOperation]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def query(
        self,
        statement: str,
        *,
        language: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> QueryResult:
        raise NotImplementedError

    @abstractmethod
    async def get_node(self, node_id: str) -> Node | None:
        raise NotImplementedError

    @abstractmethod
    async def schema(self) -> GraphSchema:
        raise NotImplementedError
