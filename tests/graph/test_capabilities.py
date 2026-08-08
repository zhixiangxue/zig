from __future__ import annotations

from zig.graph.capabilities import BackendCapabilities, PARAMETERIZED_QUERIES, SCHEMA_INTROSPECTION


def test_backend_capabilities_supports_membership() -> None:
    capabilities = BackendCapabilities(frozenset({PARAMETERIZED_QUERIES, SCHEMA_INTROSPECTION}))

    assert capabilities.supports(PARAMETERIZED_QUERIES)
    assert SCHEMA_INTROSPECTION in capabilities
    assert not capabilities.supports("nlq")
    assert set(capabilities) == {PARAMETERIZED_QUERIES, SCHEMA_INTROSPECTION}
