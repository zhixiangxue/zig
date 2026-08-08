from __future__ import annotations

from dataclasses import dataclass, field

TRANSACTIONS = "transactions"
SCHEMA_INTROSPECTION = "schema_introspection"
PARAMETERIZED_QUERIES = "parameterized_queries"
CONSTRAINTS = "constraints"
INDEXES = "indexes"
MULTI_EDGES = "multi_edges"
NLQ = "nlq"
VECTOR_SEARCH = "vector_search"


@dataclass(frozen=True)
class BackendCapabilities:
    values: frozenset[str] = field(default_factory=frozenset)

    def supports(self, name: str) -> bool:
        return name in self.values

    def __contains__(self, name: str) -> bool:
        return self.supports(name)

    def __iter__(self):
        return iter(self.values)
