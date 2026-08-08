from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..exceptions import NLQConfigurationError, NLQValidationError
from ..graph.base import AbstractGraphClient
from .config import NLQConfig
from .models import GeneratedStatement, NLQResult
from .translators import FalkorDBCypherTranslator, TextToQueryTranslator

class _ConditionCheck(BaseModel):
    # Structured check entry: the Literal status forces the model to pick one
    # of three values, so an unvalidated criterion cannot silently become "met".
    criterion: str = Field(
        default="",
        description="The requested criterion being checked (e.g. 'LTV <= 85%').",
    )
    subject: str = Field(
        default="",
        description=(
            "Entity the check applies to (e.g. a product name). Empty when the "
            "check applies to the whole result."
        ),
    )
    status: Literal["met", "not_met", "unknown"] = Field(
        default="unknown",
        description=(
            "'met' or 'not_met' ONLY when the Cypher statement filters on the "
            "criterion or the records contain a field value for it. 'unknown' "
            "when the criterion is neither filtered in the statement nor present "
            "in the records, i.e. not validated by the query."
        ),
    )
    detail: str = Field(
        default="",
        description=(
            "Compared values for met/not_met (e.g. '80% cap < 85% requested'), "
            "or 'not validated by the query' for unknown."
        ),
    )


class _EntityVerdict(BaseModel):
    # Per-entity response contract: every distinct entity in the records must
    # get one entry, so the model cannot converge on a single "best" entity.
    entity: str = Field(
        default="",
        description="Identifier of the entity as it appears in the records.",
    )
    status: Literal["met", "not_met", "unknown"] = Field(
        default="unknown",
        description=(
            "'met' only when every validated criterion is met for this entity; "
            "'not_met' when any validated criterion fails; 'unknown' when no "
            "criterion could be validated for it."
        ),
    )
    reason: str = Field(
        default="",
        description=(
            "One-sentence justification, mentioning any requested criteria that "
            "were not validated by the query."
        ),
    )


class _Answer(BaseModel):
    # Fields are declared (and therefore generated) in reasoning-first order:
    # the model must complete the per-condition checks and per-entity verdicts
    # before it commits to an overall verdict, which prevents both the
    # "conclusion-first, then self-reversal" answers and silently dropped
    # entities.
    condition_checks: list[_ConditionCheck] = Field(
        default_factory=list,
        description=(
            "Per-condition check results. One entry per requested criterion, "
            "per entity when the records contain multiple entities."
        ),
    )
    entity_verdicts: list[_EntityVerdict] = Field(
        default_factory=list,
        description=(
            "Exactly one entry for every distinct entity appearing in the query "
            "result records. No entity may be silently skipped."
        ),
    )
    verdict: str = Field(
        default="",
        description=(
            "Final overall conclusion, generated after condition_checks and "
            "entity_verdicts, and consistent with both. It must be based only "
            "on met/not_met checks; unknown checks never count as satisfied. "
            "When unknown checks exist the verdict must be qualified (e.g. "
            "'meets X of Y validated criteria; Z not validated by the query')."
        ),
    )
    answer: str = Field(
        default="",
        description=(
            "Human-readable answer grouped by entity: per-condition checks and "
            "per-entity verdicts first, single overall conclusion last. It must "
            "restate and must not contradict the verdict."
        ),
    )


class NLQ:
    def __init__(
        self,
        client: AbstractGraphClient,
        *,
        config: NLQConfig,
        translator: TextToQueryTranslator | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._translator = translator or FalkorDBCypherTranslator()

    async def query(self, question: str, *, params: dict[str, Any] | None = None) -> NLQResult:
        """Run the full NLQ pipeline: generate Cypher → execute with params → summarize.

        Args:
            question: Natural language question from the user.
            params: Optional Cypher parameter bindings (e.g. {"allowed_docs": [...]})
                    passed through to the DB execution layer.
        """
        schema_text = (self._config.schema or "").strip()
        if not schema_text:
            raise NLQConfigurationError("Natural language query requires nlq_config.schema")

        prompt = self._translator.render_query_prompt(question, schema_text)
        generated = await self._structured(prompt, GeneratedStatement)
        if generated is None:
            raise NLQConfigurationError("LLM did not return a valid GeneratedStatement")

        cleaned_statement = self._translator.clean_statement(generated.statement)
        generated = generated.model_copy(update={"statement": cleaned_statement})
        if generated.refusal_reason or not cleaned_statement:
            return NLQResult(
                answer=generated.refusal_reason or generated.explanation,
                statement=generated,
                schema_text=schema_text,
                debug={"query_prompt": prompt},
            )

        validation = self._translator.validate(cleaned_statement)
        if not validation.ok:
            raise NLQValidationError("; ".join(validation.errors))

        query_result = await self._client.query(
            cleaned_statement, language=generated.language, params=params
        )
        answer = None
        answer_prompt = None
        if self._config.summarize:
            answer_prompt = self._translator.render_answer_prompt(question, cleaned_statement, query_result)
            answer_result = await self._structured(answer_prompt, _Answer)
            answer = answer_result.answer if answer_result is not None else None

        return NLQResult(
            answer=answer,
            statement=generated,
            result=query_result,
            schema_text=schema_text,
            debug={
                "query_prompt": prompt,
                "answer_prompt": answer_prompt,
                "validation": validation.model_dump(),
            },
        )

    async def _structured[T: BaseModel](self, prompt: str, returns: type[T]) -> T | None:
        conversation = self._new_conversation()
        return await conversation.asend(prompt, returns=returns, timeout=self._config.timeout)

    def _new_conversation(self) -> Any:
        if not self._config.model_uri:
            raise NLQConfigurationError("Natural language query requires nlq_config.model_uri")
        from chak import Conversation

        # Forward decoding parameters only when set, so provider defaults are
        # kept for anything left as None. temperature defaults to 0.0 for stable
        # answer synthesis.
        decoding: dict[str, Any] = {}
        if self._config.temperature is not None:
            decoding["temperature"] = self._config.temperature
        if self._config.top_p is not None:
            decoding["top_p"] = self._config.top_p
        if self._config.seed is not None:
            decoding["seed"] = self._config.seed

        return Conversation(
            self._config.model_uri,
            api_key=self._config.api_key,
            system_prompt=self._translator.system_prompt(),
            **decoding,
        )
