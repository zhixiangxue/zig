from __future__ import annotations

from typing import Protocol

from ...models import QueryResult
from ..models import ValidationResult


class TextToQueryTranslator(Protocol):
    language: str
    backend: str

    def system_prompt(self) -> str:
        raise NotImplementedError

    def render_query_prompt(self, question: str, schema: str) -> str:
        raise NotImplementedError

    def clean_statement(self, statement: str) -> str:
        raise NotImplementedError

    def validate(self, statement: str) -> ValidationResult:
        raise NotImplementedError

    def render_answer_prompt(self, question: str, statement: str, result: QueryResult) -> str:
        raise NotImplementedError
