from tourism_agent.agent.planner import PlanDecision, PlannedToolCall
from tourism_agent.agent.workflow import AgentWorkflow
from tourism_agent.tools.base import ToolResult, ToolSpec


class RecordingTools:
    def __init__(self, failures: set[str] | None = None):
        self.failures = failures or set()
        self.batches: list[list[str]] = []

    def specs(self):
        return [
            ToolSpec("knowledge", "knowledge", {}),
            ToolSpec("budget", "budget", {}),
            ToolSpec("broken", "broken", {}),
        ]

    def execute_many(self, calls):
        self.batches.append([call["name"] for call in calls])
        return [
            ToolResult(
                call["name"],
                f"result:{call['name']}",
                success=call["name"] not in self.failures,
            )
            for call in calls
        ]


class StaticPlanner:
    def __init__(self, decision):
        self.decision = decision

    def plan(self, query, history, tools):
        return self.decision


class SimpleGenerator:
    def __init__(self):
        self.seen_results = []

    def stream_agent_answer(self, query, history, goal, tool_results):
        self.seen_results.append(tool_results)
        yield "Câu trả lời hợp lệ"


def test_dependency_steps_execute_in_topological_order():
    decision = PlanDecision(
        goal="Lập kế hoạch và tính ngân sách",
        subtasks=["Tìm thông tin", "Tính ngân sách"],
        tool_calls=[
            PlannedToolCall(id="step_1", task="Tìm thông tin", name="knowledge"),
            PlannedToolCall(id="step_2", task="Tính tiền", name="budget", depends_on=["step_1"]),
        ],
    )
    tools = RecordingTools()
    generator = SimpleGenerator()
    workflow = AgentWorkflow(StaticPlanner(decision), tools, generator)

    assert "".join(workflow.stream("trip", [])) == "Câu trả lời hợp lệ"
    assert tools.batches == [["knowledge"], ["budget"]]
    assert [item["step_id"] for item in generator.seen_results[-1]] == ["step_1", "step_2"]


class CorrectingPlanner:
    def __init__(self):
        self.revisions = 0

    def plan(self, query, history, tools):
        return PlanDecision(tool_calls=[
            PlannedToolCall(id="step_1", task="Thử tool", name="broken")
        ])

    def revise(self, **kwargs):
        self.revisions += 1
        assert kwargs["issues"]
        return PlanDecision(tool_calls=[
            PlannedToolCall(id="step_retry", task="Dùng nguồn khác", name="knowledge")
        ])


def test_validator_triggers_one_self_correction_before_streaming():
    planner = CorrectingPlanner()
    tools = RecordingTools(failures={"broken"})
    generator = SimpleGenerator()
    workflow = AgentWorkflow(planner, tools, generator, max_retries=1)

    answer = "".join(workflow.stream("trip", []))

    assert answer == "Câu trả lời hợp lệ"
    assert planner.revisions == 1
    assert tools.batches == [["broken"], ["knowledge"]]
    assert len(generator.seen_results) == 2
    assert generator.seen_results[-1][0]["tool_name"] == "knowledge"


def test_failed_dependency_blocks_child_tool():
    decision = PlanDecision(tool_calls=[
        PlannedToolCall(id="step_1", name="broken"),
        PlannedToolCall(id="step_2", name="budget", depends_on=["step_1"]),
    ])
    tools = RecordingTools(failures={"broken"})
    generator = SimpleGenerator()
    workflow = AgentWorkflow(StaticPlanner(decision), tools, generator, max_retries=0)

    assert "".join(workflow.stream("trip", [])) == "Câu trả lời hợp lệ"
    assert tools.batches == [["broken"]]
    assert generator.seen_results[-1][1]["success"] is False
    assert "dependency" in generator.seen_results[-1][1]["content"]


def test_non_stream_run_exposes_final_state_for_evaluation():
    decision = PlanDecision(tool_calls=[PlannedToolCall(id="step_1", name="knowledge")])
    workflow = AgentWorkflow(StaticPlanner(decision), RecordingTools(), SimpleGenerator())

    state = workflow.run("trip", [])

    assert state["final_answer"] == "Câu trả lời hợp lệ"
    assert state["tool_results"][0]["step_id"] == "step_1"


def test_stream_events_expose_only_safe_activity_and_answer_tokens():
    decision = PlanDecision(tool_calls=[
        PlannedToolCall(id="step_1", name="knowledge")
    ])
    workflow = AgentWorkflow(StaticPlanner(decision), RecordingTools(), SimpleGenerator())

    events = list(workflow.stream_events("trip", []))
    activities = [event for event in events if event.get("type") == "activity"]

    assert any(event["id"] == "planning" and event["status"] == "completed" for event in activities)
    assert any(event["id"] == "step_1" and event["status"] == "completed" for event in activities)
    assert any(event["id"] == "synthesis" for event in activities)
    assert "".join(event["token"] for event in events if event.get("type") == "token") == "Câu trả lời hợp lệ"
    assert all(set(event) <= {"type", "id", "label", "status"} for event in activities)
