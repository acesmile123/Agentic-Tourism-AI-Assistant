from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from tourism_agent.domain.models import ChatMessage
from tourism_agent.services.generation import GeminiGenerationService
from tourism_agent.tools.base import ToolSpec

logger = logging.getLogger(__name__)


class PlannedToolCall(BaseModel):
    id: str = ""
    task: str = ""
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class PlanDecision(BaseModel):
    goal: str = "Trả lời yêu cầu của người dùng"
    subtasks: list[str] = Field(default_factory=list, max_length=5)
    tool_calls: list[PlannedToolCall] = Field(default_factory=list, max_length=5)
    answer_directly: bool = False


class AgentPlanner:
    def __init__(self, llm: GeminiGenerationService):
        self.llm = llm

    def plan(
        self,
        query: str,
        history: list[ChatMessage],
        tools: list[ToolSpec],
        correction_context: str = "",
    ) -> PlanDecision:
        tool_payload = [{
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "available": tool.available,
        } for tool in tools]
        history_text = "\n".join(f"{item.role}: {item.content[:300]}" for item in history[-6:])
        prompt = f"""Bạn là planner/router cho AI Agent du lịch Việt Nam.
Phân rã yêu cầu phức tạp thành tối đa 5 subtask và chọn tool cần thiết. Chỉ gọi tool available=true.

QUY TẮC:
- Kiến thức du lịch ổn định/nội bộ: search_tourism_knowledge.
- Thời tiết hiện tại hoặc dự báo: weather.
- Địa chỉ, tọa độ hoặc link bản đồ: map_location.
- Tính chi phí: budget_calculator.
- Thông tin mới, sự kiện, giá/giờ mở cửa thay đổi: web_search.
- Có thể gọi nhiều tool cho yêu cầu tổng hợp.
- Mỗi tool call có id duy nhất (step_1...), task ngắn gọn và depends_on là các id phải thành công trước.
- Tool độc lập để depends_on=[]; chỉ tạo dependency khi bước sau thực sự cần bước trước.
- Chào hỏi/trò chuyện không cần dữ liệu: không gọi tool và answer_directly=true.
- arguments phải đúng schema; không tự tạo tên tool.

TOOLS:
{json.dumps(tool_payload, ensure_ascii=False)}

LỊCH SỬ:
{history_text or '(không có)'}

YÊU CẦU:
{query}

PHẢN HỒI SỬA KẾ HOẠCH (nếu có):
{correction_context or '(không có)'}

Trả JSON: {{"goal":"...","subtasks":["..."],"tool_calls":[{{"id":"step_1","task":"...","name":"...","arguments":{{...}},"depends_on":[]}}],"answer_directly":false}}"""
        try:
            raw = self.llm.extract_json(self.llm.complete(prompt, json_output=True))
            decision = PlanDecision.model_validate(raw)
            allowed = {tool.name for tool in tools if tool.available}
            decision.tool_calls = [call for call in decision.tool_calls if call.name in allowed]
            self._normalize_steps(decision)
            decision.answer_directly = not decision.tool_calls
            return decision
        except Exception as exc:
            logger.warning("Agent planning failed; using deterministic fallback: %s", exc)
            return self._fallback(query, tools)

    def revise(
        self,
        query: str,
        history: list[ChatMessage],
        tools: list[ToolSpec],
        previous_plan: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
        issues: list[str],
    ) -> PlanDecision:
        context = json.dumps({
            "previous_plan": previous_plan,
            "tool_results": tool_results,
            "validator_issues": issues,
            "instruction": "Sửa arguments, đổi tool hoặc bỏ dependency lỗi; chỉ lập các bước cần chạy lại.",
        }, ensure_ascii=False, default=str)
        return self.plan(query, history, tools, correction_context=context)

    @staticmethod
    def _normalize_steps(decision: PlanDecision) -> None:
        used: set[str] = set()
        for index, call in enumerate(decision.tool_calls, 1):
            candidate = call.id.strip() or f"step_{index}"
            if candidate in used:
                candidate = f"step_{index}"
            call.id = candidate
            call.task = call.task.strip() or call.name
            used.add(candidate)
        valid_ids = {call.id for call in decision.tool_calls}
        for call in decision.tool_calls:
            call.depends_on = list(dict.fromkeys(
                dependency for dependency in call.depends_on
                if dependency in valid_ids and dependency != call.id
            ))

    @staticmethod
    def _fallback(query: str, tools: list[ToolSpec]) -> PlanDecision:
        available = {tool.name for tool in tools if tool.available}
        normalized = query.casefold()
        calls: list[PlannedToolCall] = []
        if "weather" in available and any(word in normalized for word in ("thời tiết", "nhiệt độ", "mưa", "dự báo")):
            calls.append(PlannedToolCall(
                name="weather",
                arguments={"location": query, "forecast": any(word in normalized for word in ("dự báo", "ngày mai"))},
            ))
        if "map_location" in available and any(word in normalized for word in ("địa chỉ", "bản đồ", "tọa độ", "đường đi", "ở đâu")):
            calls.append(PlannedToolCall(name="map_location", arguments={"query": query, "limit": 1}))
        if "budget_calculator" in available and any(word in normalized for word in ("ngân sách", "chi phí", "bao nhiêu tiền")):
            days_match = re.search(r"(\d+)\s*ngày", normalized)
            people_match = re.search(r"(\d+)\s*(người|khách)", normalized)
            calls.append(PlannedToolCall(name="budget_calculator", arguments={
                "destination": query,
                "days": int(days_match.group(1)) if days_match else 1,
                "travelers": int(people_match.group(1)) if people_match else 1,
                "style": "mid_range",
            }))
        if "web_search" in available and any(word in normalized for word in ("mới nhất", "hiện nay", "hôm nay", "sự kiện")):
            calls.append(PlannedToolCall(name="web_search", arguments={"query": query, "max_results": 5}))
        greetings = ("xin chào", "chào bạn", "hello", "cảm ơn")
        if not calls and "search_tourism_knowledge" in available and not any(word in normalized for word in greetings):
            calls.append(PlannedToolCall(name="search_tourism_knowledge", arguments={"query": query}))
        decision = PlanDecision(
            subtasks=[call.name for call in calls],
            tool_calls=calls,
            answer_directly=not calls,
        )
        AgentPlanner._normalize_steps(decision)
        return decision
