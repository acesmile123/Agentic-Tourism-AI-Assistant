import json

from tourism_agent.agent.planner import AgentPlanner
from tourism_agent.tools.base import ToolSpec


class FakeLLM:
    def complete(self, prompt, json_output=False):
        return json.dumps({
            "goal": "Kiểm tra thời tiết và ngân sách",
            "subtasks": ["Kiểm tra thời tiết", "Tính ngân sách"],
            "tool_calls": [
                {"id": "step_1", "task": "Thời tiết", "name": "weather", "arguments": {"location": "Đà Nẵng", "forecast": True}},
                {"id": "step_2", "task": "Ngân sách", "name": "budget_calculator", "arguments": {"destination": "Đà Nẵng", "days": 3}, "depends_on": ["step_1"]},
            ],
        })

    @staticmethod
    def extract_json(value):
        return json.loads(value)


def test_planner_can_choose_multiple_available_tools():
    tools = [
        ToolSpec("weather", "weather", {}, available=True),
        ToolSpec("budget_calculator", "budget", {}, available=True),
    ]
    decision = AgentPlanner(FakeLLM()).plan("Lên kế hoạch", [], tools)

    assert [call.name for call in decision.tool_calls] == ["weather", "budget_calculator"]
    assert decision.tool_calls[1].depends_on == ["step_1"]
    assert decision.subtasks == ["Kiểm tra thời tiết", "Tính ngân sách"]
    assert decision.answer_directly is False


def test_planner_removes_unavailable_tools():
    tools = [ToolSpec("weather", "weather", {}, available=False)]
    decision = AgentPlanner(FakeLLM()).plan("Thời tiết?", [], tools)

    assert decision.tool_calls == []
    assert decision.answer_directly is True
