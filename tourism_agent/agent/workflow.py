from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from tourism_agent.agent.planner import AgentPlanner, PlanDecision
from tourism_agent.agent.state import AgentState
from tourism_agent.agent.validator import AgentValidator
from tourism_agent.domain.models import ChatMessage
from tourism_agent.observability import NoOpObservability
from tourism_agent.services.generation import GeminiGenerationService
from tourism_agent.tools.base import ToolRegistry, ToolResult


class AgentWorkflow:
    ACTIVITY_LABELS = {
        "search_tourism_knowledge": "Tìm thông tin du lịch",
        "weather": "Kiểm tra thời tiết",
        "map_location": "Tra cứu địa điểm và bản đồ",
        "budget_calculator": "Ước tính ngân sách",
        "web_search": "Tìm thông tin cập nhật trên web",
    }

    def __init__(
        self,
        planner: AgentPlanner,
        tools: ToolRegistry,
        generator: GeminiGenerationService,
        validator: AgentValidator | None = None,
        max_retries: int = 1,
        observer=None,
    ):
        self.planner = planner
        self.tools = tools
        self.generator = generator
        self.validator = validator or AgentValidator()
        self.max_retries = max(0, min(int(max_retries), 2))
        self.observer = observer or NoOpObservability()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("planner", self._planner_node)
        graph.add_node("tools", self._tools_node)
        graph.add_node("draft", self._draft_node)
        graph.add_node("validator", self._validator_node)
        graph.add_node("correction", self._correction_node)
        graph.add_node("finalize", self._finalize_node)
        graph.add_edge(START, "planner")
        graph.add_conditional_edges(
            "planner",
            self._route_after_plan,
            {"tools": "tools", "draft": "draft"},
        )
        graph.add_edge("tools", "draft")
        graph.add_edge("draft", "validator")
        graph.add_conditional_edges(
            "validator",
            self._route_after_validation,
            {"correction": "correction", "finalize": "finalize"},
        )
        graph.add_conditional_edges(
            "correction",
            self._route_after_plan,
            {"tools": "tools", "draft": "draft"},
        )
        graph.add_edge("finalize", END)
        return graph.compile()

    def _planner_node(self, state: AgentState) -> dict[str, Any]:
        writer = get_stream_writer()
        writer({
            "type": "activity",
            "id": "planning",
            "label": "Phân tích yêu cầu",
            "status": "running",
        })
        with self.observer.span(
            "agent.planner", as_type="agent", input={"query": state["query"]},
        ) as span:
            decision = self.planner.plan(state["query"], state.get("history", []), self.tools.specs())
            update = self._decision_update(decision)
            writer({
                "type": "activity",
                "id": "planning",
                "label": "Phân tích yêu cầu",
                "status": "completed",
            })
            span.update(output={
                "goal": update["goal"],
                "subtasks": update["subtasks"],
                "tool_calls": update["tool_calls"],
            })
            return update

    @staticmethod
    def _decision_update(decision: PlanDecision) -> dict[str, Any]:
        calls = [call.model_dump() for call in decision.tool_calls]
        used: set[str] = set()
        for index, call in enumerate(calls, 1):
            step_id = str(call.get("id", "")).strip() or f"step_{index}"
            if step_id in used:
                step_id = f"step_{index}"
            call["id"] = step_id
            call["task"] = str(call.get("task", "")).strip() or call["name"]
            call["depends_on"] = list(call.get("depends_on", []))
            used.add(step_id)
        return {
            "goal": decision.goal,
            "subtasks": decision.subtasks,
            "tool_calls": calls,
            "answer_directly": decision.answer_directly,
            "tool_results": [],
            "draft_answer": "",
            "draft_tokens": [],
        }

    @staticmethod
    def _route_after_plan(state: AgentState) -> str:
        return "tools" if state.get("tool_calls") else "draft"

    def _tools_node(self, state: AgentState) -> dict[str, Any]:
        """Run a small DAG: ready steps run first; failed parents block their children."""
        writer = get_stream_writer()
        for call in state.get("tool_calls", []):
            writer({
                "type": "activity",
                "id": call["id"],
                "label": self.ACTIVITY_LABELS.get(call["name"], "Đang dùng công cụ"),
                "status": "pending",
            })
        with self.observer.span(
            "agent.tool_execution",
            as_type="chain",
            input=state.get("tool_calls", []),
        ) as span:
            observations = self._execute_tool_plan(state.get("tool_calls", []), writer=writer)
            for observation in observations:
                writer({
                    "type": "activity",
                    "id": observation["step_id"],
                    "label": self.ACTIVITY_LABELS.get(
                        observation["tool_name"], "Đang dùng công cụ"
                    ),
                    "status": "completed" if observation["success"] else "failed",
                })
            span.update(output=observations)
            return {"tool_results": observations}

    def _execute_tool_plan(self, tool_calls: list[dict[str, Any]], writer=None) -> list[dict[str, Any]]:
        pending = {call["id"]: call for call in tool_calls}
        completed: dict[str, dict[str, Any]] = {}
        observations: list[dict[str, Any]] = []

        while pending:
            ready = [
                call for call in pending.values()
                if set(call.get("depends_on", [])).issubset(completed)
            ]
            if not ready:
                for call in pending.values():
                    result = ToolResult(
                        call["name"],
                        "Dependency không hợp lệ hoặc tạo thành vòng lặp.",
                        success=False,
                    )
                    observation = self._observation(call, result)
                    observations.append(observation)
                    completed[call["id"]] = observation
                break

            runnable: list[dict[str, Any]] = []
            for call in ready:
                dependencies = [completed[item] for item in call.get("depends_on", [])]
                if any(not item["success"] for item in dependencies):
                    result = ToolResult(
                        call["name"],
                        "Không chạy vì một bước dependency đã thất bại.",
                        success=False,
                    )
                    observation = self._observation(call, result)
                    observations.append(observation)
                    completed[call["id"]] = observation
                else:
                    runnable.append(call)

            if runnable:
                if writer is not None:
                    for call in runnable:
                        writer({
                            "type": "activity",
                            "id": call["id"],
                            "label": self.ACTIVITY_LABELS.get(call["name"], "Đang dùng công cụ"),
                            "status": "running",
                        })
                results = self.tools.execute_many(runnable)
                for call, result in zip(runnable, results, strict=False):
                    observation = self._observation(call, result)
                    observations.append(observation)
                    completed[call["id"]] = observation

            for call in ready:
                pending.pop(call["id"], None)

        return observations

    @staticmethod
    def _observation(call: dict[str, Any], result: ToolResult) -> dict[str, Any]:
        return {
            **result.to_dict(),
            "step_id": call["id"],
            "task": call.get("task", call["name"]),
            "depends_on": call.get("depends_on", []),
        }

    def _draft_node(self, state: AgentState) -> dict[str, Any]:
        writer = get_stream_writer()
        writer({
            "type": "activity",
            "id": "synthesis",
            "label": "Xây dựng câu trả lời",
            "status": "running",
        })
        tokens: list[str] = []
        try:
            tokens = list(self.generator.stream_agent_answer(
                query=state["query"],
                history=state.get("history", []),
                goal=state.get("goal", ""),
                tool_results=state.get("tool_results", []),
            ))
        except Exception:
            tokens = []
        writer({
            "type": "activity",
            "id": "synthesis",
            "label": "Xây dựng câu trả lời",
            "status": "completed" if tokens else "failed",
        })
        return {"draft_tokens": tokens, "draft_answer": "".join(tokens)}

    def _validator_node(self, state: AgentState) -> dict[str, Any]:
        writer = get_stream_writer()
        writer({
            "type": "activity",
            "id": "validation",
            "label": "Kiểm tra câu trả lời",
            "status": "running",
        })
        with self.observer.span(
            "agent.validator", as_type="evaluator", input={
                "tool_results": state.get("tool_results", []),
                "draft_answer": state.get("draft_answer", ""),
            },
        ) as span:
            report = self.validator.validate(
                state.get("tool_calls", []),
                state.get("tool_results", []),
                state.get("draft_answer", ""),
            )
            output = report.to_dict()
            writer({
                "type": "activity",
                "id": "validation",
                "label": "Kiểm tra câu trả lời",
                "status": "completed" if report.valid else "failed",
            })
            span.update(
                output=output,
                level="DEFAULT" if report.valid else "WARNING",
            )
            return {"validation": output}

    @staticmethod
    def _route_after_validation(state: AgentState) -> str:
        validation = state.get("validation", {})
        can_retry = (
            not validation.get("valid", False)
            and validation.get("retryable", False)
            and state.get("retry_count", 0) < state.get("max_retries", 1)
        )
        return "correction" if can_retry else "finalize"

    def _correction_node(self, state: AgentState) -> dict[str, Any]:
        with self.observer.span(
            "agent.self_correction", as_type="agent", input=state.get("validation", {}),
        ) as span:
            if hasattr(self.planner, "revise"):
                decision = self.planner.revise(
                    query=state["query"],
                    history=state.get("history", []),
                    tools=self.tools.specs(),
                    previous_plan=state.get("tool_calls", []),
                    tool_results=state.get("tool_results", []),
                    issues=state.get("validation", {}).get("issues", []),
                )
                update = self._decision_update(decision)
            else:
                update = {
                    "tool_calls": state.get("tool_calls", []),
                    "tool_results": [],
                    "draft_answer": "",
                    "draft_tokens": [],
                }
            update["retry_count"] = state.get("retry_count", 0) + 1
            span.update(output={
                "retry_count": update["retry_count"],
                "tool_calls": update["tool_calls"],
            })
            return update

    @staticmethod
    def _finalize_node(state: AgentState) -> dict[str, Any]:
        writer = get_stream_writer()
        tokens = state.get("draft_tokens", [])
        answer = state.get("draft_answer", "")
        if not answer:
            answer = "Tôi chưa thể thu thập đủ dữ liệu đáng tin cậy để trả lời yêu cầu này."
            tokens = [answer]
        for token in tokens:
            writer({"type": "token", "token": token})
        return {"final_answer": answer}

    def _initial_state(self, query: str, history: list[ChatMessage]) -> AgentState:
        return {
            "query": query,
            "history": history,
            "subtasks": [],
            "tool_calls": [],
            "tool_results": [],
            "answer_directly": False,
            "draft_answer": "",
            "draft_tokens": [],
            "validation": {},
            "retry_count": 0,
            "max_retries": self.max_retries,
        }

    def run(self, query: str, history: list[ChatMessage]) -> AgentState:
        with self.observer.span(
            "tourism.agent.workflow", as_type="agent", input={"query": query},
        ) as span:
            result = self.graph.invoke(self._initial_state(query, history))
            span.update(output={
                "answer": result.get("final_answer", ""),
                "tool_results": result.get("tool_results", []),
                "validation": result.get("validation", {}),
                "retry_count": result.get("retry_count", 0),
            })
            return result

    def stream(
        self,
        query: str,
        history: list[ChatMessage],
        session_id: str | None = None,
    ) -> Iterator[str]:
        for event in self.stream_events(query, history, session_id=session_id):
            if event.get("type") == "token":
                yield str(event["token"])

    def stream_events(
        self,
        query: str,
        history: list[ChatMessage],
        session_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        parts: list[str] = []
        with self.observer.span(
            "tourism.agent.workflow",
            as_type="agent",
            input={"query": query},
            metadata={"session_id": session_id} if session_id else None,
        ) as span:
            for event in self.graph.stream(self._initial_state(query, history), stream_mode="custom"):
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "token":
                    parts.append(str(event["token"]))
                if event.get("type") in {"token", "activity"}:
                    yield event
            span.update(output="".join(parts))
