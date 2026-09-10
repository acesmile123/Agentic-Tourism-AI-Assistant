from __future__ import annotations

from statistics import mean
from typing import Any

from tourism_agent.evaluation.models import CaseResult


THRESHOLDS = {
    "recall_at_k": 0.8,
    "mrr": 0.5,
    "faithfulness": 0.75,
    "relevance": 0.75,
    "tool_f1": 0.8,
}


def analyze_case(metrics: dict[str, float | None]) -> list[str]:
    return [
        f"{name}={value:.3f} < {THRESHOLDS[name]:.3f}"
        for name, value in metrics.items()
        if name in THRESHOLDS and value is not None and value < THRESHOLDS[name]
    ]


def summarize(results: list[CaseResult]) -> dict[str, float | int | None]:
    names = sorted({name for result in results for name in result.metrics})
    summary: dict[str, float | int | None] = {"case_count": len(results)}
    for name in names:
        values = [result.metrics[name] for result in results if result.metrics.get(name) is not None]
        summary[name] = mean(values) if values else None
    summary["failed_case_count"] = sum(bool(result.failures) for result in results)
    return summary


def recommendations(summary: dict[str, Any]) -> list[str]:
    output: list[str] = []
    if _below(summary, "recall_at_k"):
        output.append("Recall thấp: kiểm tra metadata/province routing, tăng retrieval_k hoặc bổ sung query expansion.")
    if _below(summary, "mrr"):
        output.append("MRR thấp: rà lại Cohere rerank model/prompt và hard negatives trong dataset.")
    if _below(summary, "faithfulness"):
        output.append("Faithfulness thấp: giảm context nhiễu, buộc citation và siết prompt không suy đoán.")
    if _below(summary, "relevance"):
        output.append("Relevance thấp: cải thiện decomposition, answer rubric và prompt tổng hợp theo subtask.")
    if _below(summary, "tool_f1"):
        output.append("Tool routing thấp: làm rõ tool descriptions và thêm few-shot routing cases vào planner.")
    return output or ["Không có metric tổng hợp nào dưới threshold hiện tại; tiếp tục mở rộng edge cases."]


def compare_baseline(summary: dict[str, Any], baseline: dict[str, Any], tolerance: float = 0.02) -> dict[str, Any]:
    previous = baseline.get("summary", baseline)
    deltas = {}
    regressions = []
    for name in THRESHOLDS:
        current_value, previous_value = summary.get(name), previous.get(name)
        if isinstance(current_value, (int, float)) and isinstance(previous_value, (int, float)):
            delta = current_value - previous_value
            deltas[name] = delta
            if delta < -abs(tolerance):
                regressions.append(name)
    return {"deltas": deltas, "regressions": regressions, "passed": not regressions}


def _below(summary: dict[str, Any], name: str) -> bool:
    value = summary.get(name)
    return isinstance(value, (int, float)) and value < THRESHOLDS[name]


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# Tourism AI evaluation report", "", "## Summary", ""]
    for name, value in report["summary"].items():
        rendered = f"{value:.3f}" if isinstance(value, float) else str(value)
        lines.append(f"- `{name}`: {rendered}")
    lines.extend(["", "## Failure analysis", ""])
    for result in report["cases"]:
        if result["failures"]:
            lines.append(f"- **{result['id']}**: {'; '.join(result['failures'])}")
    if not any(result["failures"] for result in report["cases"]):
        lines.append("- No failures under current thresholds.")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report["recommendations"])
    if report.get("baseline_comparison"):
        comparison = report["baseline_comparison"]
        lines.extend(["", "## Baseline comparison", "", f"- Passed: `{comparison['passed']}`"])
        lines.extend(f"- `{name}` delta: {value:+.3f}" for name, value in comparison["deltas"].items())
    return "\n".join(lines) + "\n"
