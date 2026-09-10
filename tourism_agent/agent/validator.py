from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    retryable: bool
    issues: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentValidator:
    """Deterministic guardrail: predictable and free of an extra LLM call."""

    def validate(
        self,
        tool_calls: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
        draft_answer: str,
    ) -> ValidationReport:
        issues: list[str] = []
        expected = {call.get("id") for call in tool_calls}
        observed = {result.get("step_id") for result in tool_results}
        missing = sorted(str(step) for step in expected - observed if step)
        if missing:
            issues.append(f"Thiếu kết quả cho bước: {', '.join(missing)}")

        for result in tool_results:
            if not result.get("success", False):
                issues.append(
                    f"Bước {result.get('step_id', '?')} ({result.get('tool_name', '?')}) thất bại."
                )
            if result.get("success", False) and not str(result.get("content", "")).strip():
                issues.append(f"Bước {result.get('step_id', '?')} trả về nội dung rỗng.")

        if not draft_answer.strip():
            issues.append("Bản nháp câu trả lời rỗng.")

        return ValidationReport(valid=not issues, retryable=bool(issues), issues=issues)
