from __future__ import annotations

import json
import re

from ...models import QueryResult
from ..models import ValidationResult


class FalkorDBCypherTranslator:
    language = "cypher"
    backend = "falkordb"

    _DANGEROUS_RE = re.compile(r"\b(CREATE|MERGE|SET|DELETE|DETACH|DROP|REMOVE|LOAD\s+CSV|FOREACH)\b", re.IGNORECASE)
    _READ_ONLY_START_RE = re.compile(r"^\s*(MATCH|WITH|UNWIND|CALL|RETURN)\b", re.IGNORECASE)

    def system_prompt(self) -> str:
        return (
            "You translate natural language questions into safe read-only FalkorDB Cypher. "
            "Use only the explicit schema provided by the user prompt. "
            "Do not use APOC, Neo4j-only procedures, or write operations."
        )

    def render_query_prompt(self, question: str, schema: str) -> str:
        schema_text = schema.strip()
        return f"""Generate a read-only FalkorDB Cypher query for the question.

Rules:
- Return structured data using the required GeneratedStatement schema.
- Put the generated Cypher string in the statement field.
- Set refusal_reason when the explicit schema is insufficient or no safe read-only query can be generated.
- Use only labels, relationships, and properties listed in the schema.
- Do not invent labels, relationships, or properties.
- Do not use CREATE, MERGE, SET, DELETE, DETACH DELETE, DROP, REMOVE, LOAD CSV, or FOREACH.
- Do not use APOC or Neo4j-only procedures.
- Prefer clear aliases in RETURN columns.

Schema:
{schema_text}

Question:
{question}
"""

    def clean_statement(self, statement: str) -> str:
        cleaned = statement.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:cypher)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        prefixes = ("cypher query:", "cypher:", "query:", "generated query:", "generated cypher:")
        while True:
            lowered = cleaned.lower().lstrip()
            matched = next((prefix for prefix in prefixes if lowered.startswith(prefix)), None)
            if matched is None:
                break
            cleaned = cleaned.lstrip()[len(matched):].strip()
        return cleaned.strip().strip('"').strip("'").strip()

    def validate(self, statement: str) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        stripped = statement.strip()
        if not stripped:
            errors.append("Generated statement is empty")
            return ValidationResult(ok=False, errors=errors, warnings=warnings)
        if ";" in stripped:
            errors.append("Generated statement must not contain semicolons or multiple statements")
        if "--" in stripped or "/*" in stripped or "*/" in stripped or "//" in stripped:
            errors.append("Generated statement must not contain comments")
        if self._DANGEROUS_RE.search(stripped):
            errors.append("Generated statement contains write or dangerous operations")
        if not self._READ_ONLY_START_RE.search(stripped):
            errors.append("Generated statement must start with MATCH, WITH, UNWIND, CALL, or RETURN")
        if "return" not in stripped.lower():
            warnings.append("Generated statement does not contain a RETURN clause")
        if not self._balanced(stripped, "(", ")"):
            errors.append("Generated statement has unbalanced parentheses")
        if not self._balanced(stripped, "[", "]"):
            errors.append("Generated statement has unbalanced brackets")
        return ValidationResult(ok=not errors, errors=errors, warnings=warnings)

    def render_answer_prompt(self, question: str, statement: str, result: QueryResult) -> str:
        records = json.dumps(result.records, ensure_ascii=False, default=str)
        return f"""Answer the question using only the query result.

Rules:
- The query result is authoritative.
- First, check each requested criterion one by one and record every check into
  condition_checks with one of three statuses: met, not_met, or unknown.
- A criterion may be marked met or not_met ONLY when the Cypher statement
  filters on it or the records contain a field value for it; record the
  compared values.
- A requested criterion that is neither filtered in the Cypher statement nor
  present as a field in the records MUST be recorded as unknown with the note
  "not validated by the query". Never treat the absence of a restriction in
  the query as the criterion being met.
- Every distinct entity (e.g. product, program) appearing in the records MUST
  receive an explicit entry in entity_verdicts with a one-sentence reason. Do
  not silently skip entities and do not converge on a single best entity.
- Base the verdict only on met/not_met checks; unknown checks never count as
  satisfied. When any check is unknown, the verdict must be qualified (e.g.
  "meets X of Y validated criteria; Z not validated by the query") and must
  not state an unreserved eligible/allowed conclusion.
- If the result is empty, state that no records match the criteria the Cypher
  statement actually enforces and name those criteria; record any requested
  criteria the statement does not enforce as unknown. Do not answer with a
  bare "I don't know".
- Write the human-readable answer grouped by entity: present each entity's
  checks and verdict first, then end with a single overall summary listing
  which entities qualify. It must restate the verdict and must not contradict
  it.
- Give exactly one conclusion. Do not open with a verdict and then reverse it,
  and do not include self-correcting remarks.
- Do not mention that you used provided information.

Question:
{question}

Cypher statement:
{statement}

Query result:
{records}
"""

    @staticmethod
    def _balanced(value: str, left: str, right: str) -> bool:
        count = 0
        for char in value:
            if char == left:
                count += 1
            elif char == right:
                count -= 1
                if count < 0:
                    return False
        return count == 0
