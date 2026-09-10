from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict

from tourism_agent.domain.models import ChatMessage


class AgentState(TypedDict, total=False):
    query: str
    history: list[ChatMessage]
    goal: str
    subtasks: list[str]
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    answer_directly: bool
    draft_answer: str
    draft_tokens: list[str]
    validation: dict[str, Any]
    retry_count: int
    max_retries: int
    final_answer: str
