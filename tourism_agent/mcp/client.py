from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from mcp import Client

from tourism_agent.tools.base import ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class MCPToolRegistry:
    """Adapter that gives LangGraph the same registry interface over MCP."""

    def __init__(self, server: Any, read_timeout_seconds: float = 45.0, discovery_ttl_seconds: int = 300, observer=None):
        from tourism_agent.observability import NoOpObservability

        self.server = server
        self.read_timeout_seconds = read_timeout_seconds
        self.discovery_ttl_seconds = discovery_ttl_seconds
        self._spec_cache: list[ToolSpec] = []
        self._spec_cache_until = 0.0
        self.observer = observer or NoOpObservability()

    def specs(self) -> list[ToolSpec]:
        if self._spec_cache and time.monotonic() < self._spec_cache_until:
            return self._spec_cache
        self._spec_cache = asyncio.run(self._discover())
        self._spec_cache_until = time.monotonic() + self.discovery_ttl_seconds
        return self._spec_cache

    async def _discover(self) -> list[ToolSpec]:
        async with Client(self.server, read_timeout_seconds=self.read_timeout_seconds) as client:
            response = await client.list_tools()
        return [
            ToolSpec(
                name=tool.name,
                description=tool.description or "",
                parameters=tool.input_schema,
            )
            for tool in response.tools
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        return self.execute_many([{"name": name, "arguments": arguments}])[0]

    def execute_many(self, calls: list[dict[str, Any]]) -> list[ToolResult]:
        if not calls:
            return []
        return asyncio.run(self._execute_many(calls))

    async def _execute_many(self, calls: list[dict[str, Any]]) -> list[ToolResult]:
        results: list[ToolResult] = []
        try:
            async with Client(self.server, read_timeout_seconds=self.read_timeout_seconds) as client:
                for call in calls:
                    name = call["name"]
                    with self.observer.span(
                        f"mcp.tool.{name}", as_type="tool", input=call.get("arguments", {}),
                    ) as span:
                        try:
                            response = await client.call_tool(name, call.get("arguments", {}))
                            text = "\n".join(
                                block.text for block in response.content
                                if getattr(block, "type", None) == "text"
                            )
                            result = self._decode_result(name, text, bool(response.is_error))
                        except Exception as exc:
                            logger.warning("MCP tool %s failed: %s", name, exc)
                            result = ToolResult(name, f"MCP tool {name} tạm thời không khả dụng.", False)
                        span.update(
                            output=result.to_dict(),
                            level="DEFAULT" if result.success else "ERROR",
                        )
                        results.append(result)
        except Exception as exc:
            logger.warning("MCP connection failed: %s", exc)
            return [
                ToolResult(call["name"], "Không thể kết nối tới MCP tourism service.", False)
                for call in calls
            ]
        return results

    @staticmethod
    def _decode_result(name: str, text: str, is_error: bool) -> ToolResult:
        try:
            payload = json.loads(text)
            if isinstance(payload, dict) and "tool_name" in payload and "content" in payload:
                return ToolResult(
                    tool_name=str(payload["tool_name"]),
                    content=str(payload["content"]),
                    success=bool(payload.get("success", True)) and not is_error,
                    sources=list(payload.get("sources", [])),
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return ToolResult(name, text, success=not is_error)

    def ping(self) -> bool:
        try:
            self.specs()
            return True
        except Exception:
            return False
