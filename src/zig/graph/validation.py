from __future__ import annotations

import re

from ..exceptions import GraphOperationError

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise GraphOperationError(f"{field_name} must be a non-empty string")
    if not _IDENTIFIER_RE.fullmatch(value):
        raise GraphOperationError(f"{field_name} contains invalid characters: {value!r}")
    return value


def validate_node_id(value: str, *, field_name: str = "id") -> str:
    if not isinstance(value, str) or not value:
        raise GraphOperationError(f"{field_name} must be a non-empty string")
    return value


def validate_properties(properties: dict[str, object]) -> dict[str, object]:
    for key in properties:
        validate_identifier(key, field_name="property key")
    return properties
