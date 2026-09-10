from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from tourism_agent.evaluation.models import RetrievalTarget

STOPWORDS = {
    "và", "là", "có", "của", "cho", "một", "những", "các", "được", "tại", "ở",
    "the", "a", "an", "to", "of", "in", "is", "are", "with",
}


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text).casefold())
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", value)).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in normalize(text).split() if len(token) > 2 and token not in STOPWORDS}


def document_matches(document: dict[str, Any], target: RetrievalTarget) -> bool:
    metadata = document.get("metadata", {}) or {}
    searchable = normalize(
        f"{document.get('content', '')} {json.dumps(metadata, ensure_ascii=False, default=str)}"
    )
    keyword_match = not target.keywords or any(normalize(keyword) in searchable for keyword in target.keywords)
    metadata_match = all(
        normalize(expected) in normalize(metadata.get(key, ""))
        for key, expected in target.metadata.items()
    )
    return keyword_match and metadata_match


def retrieval_metrics(
    documents: list[dict[str, Any]],
    targets: list[RetrievalTarget],
    k: int,
) -> dict[str, float | None]:
    if not targets:
        return {"recall_at_k": None, "mrr": None}
    top_docs = documents[:max(1, k)]
    matched_targets = sum(
        any(document_matches(document, target) for document in top_docs)
        for target in targets
    )
    reciprocal_rank = 0.0
    for rank, document in enumerate(top_docs, 1):
        if any(document_matches(document, target) for target in targets):
            reciprocal_rank = 1.0 / rank
            break
    return {
        "recall_at_k": matched_targets / len(targets),
        "mrr": reciprocal_rank,
    }


def routing_metrics(selected: list[str], expected: list[str]) -> dict[str, float | None]:
    if not expected:
        return {"tool_precision": None, "tool_recall": None, "tool_f1": None}
    selected_set, expected_set = set(selected), set(expected)
    true_positive = len(selected_set & expected_set)
    precision = true_positive / len(selected_set) if selected_set else 0.0
    recall = true_positive / len(expected_set)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tool_precision": precision, "tool_recall": recall, "tool_f1": f1}


def heuristic_generation_scores(
    query: str,
    answer: str,
    context: str,
    reference_answer: str,
) -> tuple[float, float]:
    answer_tokens = _tokens(answer)
    evidence_tokens = _tokens(context)
    target_tokens = _tokens(f"{query} {reference_answer}")
    faithfulness = len(answer_tokens & evidence_tokens) / len(answer_tokens) if answer_tokens else 0.0
    relevance = len(answer_tokens & target_tokens) / len(target_tokens) if target_tokens else 0.0
    return min(faithfulness, 1.0), min(relevance, 1.0)
