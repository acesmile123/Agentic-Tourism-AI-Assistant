from tourism_agent.agent.planner import PlanDecision, PlannedToolCall
from tourism_agent.agent.workflow import AgentWorkflow
from tourism_agent.tools.base import ToolRegistry, ToolResult, ToolSpec


class FakePlanner:
    def plan(self, query, history, tools):
        return PlanDecision(
            goal="Tính ngân sách",
            tool_calls=[PlannedToolCall(name="fake_tool", arguments={"query": query})],
        )


class FakeTool:
    @property
    def spec(self):
        return ToolSpec("fake_tool", "fake", {"query": "string"})

    def run(self, query):
        return ToolResult("fake_tool", "observation")


class FakeGenerator:
    def stream_agent_answer(self, query, history, goal, tool_results):
        assert tool_results[0]["content"] == "observation"
        yield "Kết "
        yield "quả"


def test_langgraph_workflow_executes_tool_and_streams_answer():
    workflow = AgentWorkflow(FakePlanner(), ToolRegistry([FakeTool()]), FakeGenerator())

    assert "".join(workflow.stream("query", [])) == "Kết quả"

