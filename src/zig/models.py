from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Node(BaseModel):
    id: str
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    source: str
    type: str
    target: str
    properties: dict[str, Any] = Field(default_factory=dict)


class QueryResult(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    raw: Any | None = None


class GraphSchema(BaseModel):
    labels: list[str] = Field(default_factory=list)
    relationship_types: list[str] = Field(default_factory=list)
    properties: dict[str, list[str]] = Field(default_factory=dict)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
