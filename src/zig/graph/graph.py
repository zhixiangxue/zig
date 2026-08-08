from __future__ import annotations

from types import TracebackType

from ..exceptions import UnsupportedCapabilityError, UnsupportedQueryLanguageError
from ..models import QueryResult
from ..query import NLQConfig, NLQResult
from ..query.nlq import NLQ as NaturalLanguageQuery

from .base import AbstractGraphClient, GraphOperation
from .capabilities import BackendCapabilities, NLQ
from .edges import EdgeSet
from .nodes import NodeSet
from .registry import BackendRegistry
from .uri import parse_graph_uri

from typing import Any


class Graph:
    def __init__(
        self,
        uri: str,
        *,
        nlq_config: NLQConfig | None = None,
    ) -> None:
        self.uri = parse_graph_uri(uri)
        client_cls = BackendRegistry.get(self.uri.backend)
        self._client: AbstractGraphClient = client_cls(self.uri)
        self._connected = False
        self._pending_operations: list[GraphOperation] = []
        self._nlq_config = nlq_config
        self.node = NodeSet(self)
        self.edge = EdgeSet(self)

    @property
    def capabilities(self) -> BackendCapabilities:
        return self._client.capabilities

    def supports(self, name: str) -> bool:
        if name == NLQ:
            has_schema = bool(self._nlq_config and self._nlq_config.schema and self._nlq_config.schema.strip())
            has_llm = bool(self._nlq_config and self._nlq_config.model_uri)
            return has_schema and has_llm
        return self.capabilities.supports(name)

    async def __aenter__(self) -> Graph:
        await self._ensure_connected()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is None:
            await self.commit()
        else:
            self._pending_operations.clear()
        await self._client.close()
        self._connected = False

    def rollback(self) -> None:
        """Discard pending graph operations that have not been committed."""
        self._pending_operations.clear()

    async def commit(self) -> None:
        if not self._pending_operations:
            return None
        await self._ensure_connected()
        operations = list(self._pending_operations)
        await self._client.commit(operations)
        self._pending_operations.clear()
        return None

    async def execute(
        self,
        statement: str,
        *,
        language: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Execute a raw query statement against the backend.

        Args:
            statement: The query statement (e.g. Cypher) to execute.
            language: Optional query language override.
            params: Optional parameter bindings for parameterized queries.
        """
        if language is not None and language not in self._client.supported_languages:
            raise UnsupportedQueryLanguageError(
                f"Backend {self.uri.backend!r} does not support query language {language!r}"
            )
        await self._ensure_connected()
        return await self._client.query(statement, language=language, params=params)

    async def query(
        self,
        prompt: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> NLQResult:
        """Run a natural language query with optional Cypher parameter bindings.

        Args:
            prompt: Natural language question.
            params: Optional dict of Cypher parameter bindings passed to the DB
                    execution layer (e.g. {"allowed_docs": ["id1", "id2"]}).
        """
        if not (self._nlq_config and self._nlq_config.schema and self._nlq_config.schema.strip()):
            raise UnsupportedCapabilityError("Natural language query requires nlq_config.schema")
        if not (self._nlq_config and self._nlq_config.model_uri):
            raise UnsupportedCapabilityError("Natural language query requires nlq_config.model_uri")
        await self._ensure_connected()
        nlq = NaturalLanguageQuery(
            self._client,
            config=self._nlq_config,
        )
        return await nlq.query(prompt, params=params)

    def _append_operation(self, operation: GraphOperation) -> None:
        self._pending_operations.append(operation)

    async def _ensure_connected(self) -> None:
        if not self._connected:
            await self._client.connect()
            self._connected = True


from .backends import falkordb as _falkordb  # noqa: E402,F401
