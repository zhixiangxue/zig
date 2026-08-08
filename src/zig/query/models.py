from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..models import QueryResult


class GeneratedStatement(BaseModel):
    statement: str = Field(default="", description="Generated read-only backend query statement, such as Cypher")
    language: str = Field(default="cypher", description="Backend query language")
    backend: str = Field(default="falkordb", description="Target graph backend")
    confidence: float | None = Field(default=None, description="Confidence score between 0 and 1")
    explanation: str | None = Field(default=None, description="Brief explanation for debugging")
    refusal_reason: str | None = Field(default=None, description="Why no safe query statement can be generated")


class ValidationResult(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NLQResult(BaseModel):
    answer: str | None = None
    statement: GeneratedStatement | None = None
    result: QueryResult | None = None
    schema_text: str
    debug: dict[str, Any] = Field(default_factory=dict)
