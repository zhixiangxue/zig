from __future__ import annotations

import pytest

from zig import Graph, NLQConfig
from zig.exceptions import NLQValidationError, UnsupportedCapabilityError
from zig.graph.capabilities import NLQ as NLQ_CAPABILITY
from zig.query import GeneratedStatement
from zig.query.nlq import NLQ
from zig.query.translators import FalkorDBCypherTranslator

from tests.conftest import FakeGraphClient


def dpa_like_schema() -> str:
    return """
    Nodes:
    - Agency(name): organization that offers DPA programs.
    - Program(name, program_id): down payment assistance program.

    Relationships:
    - (:Agency)-[:OFFERS]->(:Program): agency offers a program.
    """.strip()


class FakeConversation:
    def __init__(self, statement: str = "MATCH (a:Agency)-[:OFFERS]->(p:Program) RETURN p.name AS program_name") -> None:
        self.statement = statement
        self.prompts: list[str] = []

    async def asend(self, prompt: str, *, returns, timeout=None):
        self.prompts.append(prompt)
        if returns is GeneratedStatement:
            return GeneratedStatement(statement=self.statement, confidence=0.9)
        if returns.__name__ == "_Answer":
            return returns(answer="CalHFA 提供了 MyHome。")
        return None


class _FakeNLQ(NLQ):
    def __init__(self, *args, conversations: list[FakeConversation], statement: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._conversations = conversations
        self._statement = statement

    def _new_conversation(self) -> FakeConversation:
        conversation = FakeConversation(self._statement or "MATCH (a:Agency)-[:OFFERS]->(p:Program) RETURN p.name AS program_name")
        self._conversations.append(conversation)
        return conversation


async def test_nlq_generates_validates_executes_and_summarizes() -> None:
    client = FakeGraphClient.instances[-1] if FakeGraphClient.instances else FakeGraphClient(None)
    conversations: list[FakeConversation] = []

    nlq = _FakeNLQ(
        client,
        config=NLQConfig(schema=dpa_like_schema(), timeout=15),
        conversations=conversations,
    )

    result = await nlq.query("CalHFA 提供了哪些 Program？")

    assert result.answer == "CalHFA 提供了 MyHome。"
    assert result.statement is not None
    assert result.statement.statement.startswith("MATCH")
    assert result.result is not None
    assert result.result.records == [{"statement": result.statement.statement}]
    assert len(conversations) == 2


async def test_nlq_rejects_dangerous_generated_statement() -> None:
    client = FakeGraphClient.instances[-1] if FakeGraphClient.instances else FakeGraphClient(None)

    conversations: list[FakeConversation] = []
    nlq = _FakeNLQ(
        client,
        config=NLQConfig(schema=dpa_like_schema(), summarize=False),
        conversations=conversations,
        statement="MATCH (n) DETACH DELETE n",
    )

    with pytest.raises(NLQValidationError):
        await nlq.query("删除所有节点")


async def test_graph_query_requires_explicit_schema() -> None:
    graph = Graph("fake://localhost:1234/programs")

    with pytest.raises(UnsupportedCapabilityError):
        await graph.query("有哪些 Program？")


async def test_graph_query_supports_nlq_when_schema_and_config_are_set() -> None:
    graph = Graph(
        "fake://localhost:1234/programs",
        nlq_config=NLQConfig(schema=dpa_like_schema(), model_uri="fake/model", api_key="fake-key"),
    )

    assert graph.supports(NLQ_CAPABILITY)


def test_falkordb_translator_cleans_common_llm_wrapping() -> None:
    translator = FalkorDBCypherTranslator()

    statement = translator.clean_statement("```cypher\nCypher: MATCH (n) RETURN n\n```")

    assert statement == "MATCH (n) RETURN n"
