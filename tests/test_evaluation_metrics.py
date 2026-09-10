import json
from pathlib import Path

from tourism_agent.evaluation.analysis import compare_baseline, summarize
from tourism_agent.evaluation.metrics import retrieval_metrics, routing_metrics
from tourism_agent.evaluation.models import CaseResult, RetrievalTarget
from tourism_agent.evaluation.runner import load_dataset


def test_recall_at_k_and_mrr_use_ranked_relevance_targets():
    documents = [
        {"content": "Nội dung không liên quan", "metadata": {}},
        {"content": "Chùa Cầu nằm trong phố cổ Hội An", "metadata": {"province": "QuangNam"}},
    ]
    targets = [
        RetrievalTarget(keywords=["Chùa Cầu"]),
        RetrievalTarget(keywords=["Vịnh Hạ Long"]),
    ]

    metrics = retrieval_metrics(documents, targets, k=2)

    assert metrics["recall_at_k"] == 0.5
    assert metrics["mrr"] == 0.5


def test_tool_routing_f1_penalizes_missing_and_extra_tools():
    metrics = routing_metrics(
        ["weather", "web_search"],
        ["weather", "budget_calculator"],
    )

    assert metrics == {"tool_precision": 0.5, "tool_recall": 0.5, "tool_f1": 0.5}


def test_summary_and_baseline_detect_regression():
    result = CaseResult(
        id="case",
        query="q",
        category="knowledge",
        answer="a",
        selected_tools=[],
        metrics={"recall_at_k": 0.7, "mrr": 1.0},
        failures=["low recall"],
    )
    current = summarize([result])
    comparison = compare_baseline(current, {"summary": {"recall_at_k": 0.9}}, tolerance=0.05)

    assert current["failed_case_count"] == 1
    assert comparison["passed"] is False
    assert comparison["regressions"] == ["recall_at_k"]


def test_seed_dataset_has_unique_valid_cases():
    path = Path("evaluation/datasets/tourism_ai_eval.jsonl")
    cases = load_dataset(path)

    assert len(cases) >= 10
    assert len({case.id for case in cases}) == len(cases)
    assert {"knowledge", "complex", "freshness", "direct"}.issubset({case.category for case in cases})
