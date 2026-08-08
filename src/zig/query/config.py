from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NLQConfig:
    schema: str | None = None
    model_uri: str | None = None
    api_key: str | None = None
    timeout: int | None = 60
    summarize: bool = True
    # Decoding parameters passed through to the LLM conversation. Default to
    # deterministic decoding (temperature=0.0) so that answer synthesis is
    # stable across repeated runs and does not flip its conclusion. top_p/seed
    # are optional and only forwarded when explicitly set.
    temperature: float | None = 0.0
    top_p: float | None = None
    seed: int | None = None
