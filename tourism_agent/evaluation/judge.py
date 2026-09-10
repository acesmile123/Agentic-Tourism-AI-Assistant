from __future__ import annotations

import json

from tourism_agent.evaluation.metrics import heuristic_generation_scores
from tourism_agent.evaluation.models import GenerationScore


class GenerationJudge:
    def __init__(self, llm=None, use_llm: bool = True):
        self.llm = llm
        self.use_llm = bool(use_llm and llm is not None)

    def score(self, query: str, answer: str, context: str, reference_answer: str) -> GenerationScore:
        if self.use_llm:
            try:
                return self._llm_score(query, answer, context, reference_answer)
            except Exception:
                pass
        faithfulness, relevance = heuristic_generation_scores(query, answer, context, reference_answer)
        return GenerationScore(
            faithfulness=faithfulness,
            relevance=relevance,
            rationale="Lexical fallback; use LLM judge for semantic production evaluation.",
            method="heuristic",
        )

    def _llm_score(self, query: str, answer: str, context: str, reference_answer: str) -> GenerationScore:
        prompt = f"""Bạn là evaluator độc lập cho AI du lịch. Chấm từ 0.0 đến 1.0.

FAITHFULNESS: mọi khẳng định thực tế trong ANSWER có được hỗ trợ bởi CONTEXT không?
RELEVANCE: ANSWER có trả lời đúng QUERY và bao phủ nội dung mong đợi không?
Không chấm kiến thức bên ngoài CONTEXT. Reference chỉ là rubric, không phải nguồn sự thật.

QUERY: {query}
REFERENCE/RUBRIC: {reference_answer}
CONTEXT: {context[:12000]}
ANSWER: {answer[:8000]}

Trả JSON duy nhất: {{"faithfulness":0.0,"relevance":0.0,"rationale":"..."}}"""
        raw = self.llm.extract_json(self.llm.complete(prompt, json_output=True))
        faithfulness = max(0.0, min(float(raw["faithfulness"]), 1.0))
        relevance = max(0.0, min(float(raw["relevance"]), 1.0))
        return GenerationScore(
            faithfulness=faithfulness,
            relevance=relevance,
            rationale=str(raw.get("rationale", "")),
            method="llm_judge",
        )
