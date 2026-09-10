from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RetrievalTarget(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class EvaluationCase(BaseModel):
    id: str
    query: str
    category: str
    expected_tools: list[str] = Field(default_factory=list)
    relevant_targets: list[RetrievalTarget] = Field(default_factory=list)
    reference_answer: str = ""
    notes: str = ""


class GenerationScore(BaseModel):
    faithfulness: float
    relevance: float
    rationale: str = ""
    method: str = "heuristic"


class CaseResult(BaseModel):
    id: str
    query: str
    category: str
    answer: str
    selected_tools: list[str]
    metrics: dict[str, float | None]
    failures: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
