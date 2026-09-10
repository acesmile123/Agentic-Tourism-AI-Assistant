from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    available: bool = True


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    content: str
    success: bool = True
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentTool(Protocol):
    @property
    def spec(self) -> ToolSpec: ...

    def run(self, **kwargs: Any) -> ToolResult | str: ...


class ToolRegistry:
    def __init__(self, tools: list[AgentTool], observer=None):
        from tourism_agent.observability import NoOpObservability

        self._tools = {tool.spec.name: tool for tool in tools}
        self.observer = observer or NoOpObservability()

    def specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        with self.observer.span(
            f"tool.{name}", as_type="tool", input=arguments,
        ) as span:
            result = self._execute(name, arguments)
            span.update(
                output=result.to_dict(),
                level="DEFAULT" if result.success else "ERROR",
                status_message=None if result.success else result.content,
            )
            return result

    def _execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(name, f"Tool không tồn tại: {name}", success=False)
        if not tool.spec.available:
            return ToolResult(name, f"Tool {name} chưa được cấu hình API key.", success=False)
        try:
            result = tool.run(**arguments)
            if isinstance(result, ToolResult):
                return result
            return ToolResult(name, str(result))
        except Exception as exc:
            logger.warning("Tool %s failed: %s", name, exc)
            return ToolResult(name, f"Tool {name} tạm thời không khả dụng.", success=False)

    def execute_many(self, calls: list[dict[str, Any]]) -> list[ToolResult]:
        return [
            self.execute(call["name"], call.get("arguments", {}))
            for call in calls
        ]
