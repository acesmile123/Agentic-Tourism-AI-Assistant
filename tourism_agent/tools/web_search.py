from __future__ import annotations

import json
from typing import Any

import httpx

from tourism_agent.tools.base import ToolResult, ToolSpec


class TavilyWebSearchTool:
    def __init__(self, api_key: str, timeout_seconds: float = 15.0, client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="web_search",
            description="Tìm thông tin mới/có thể thay đổi trên web và trả về nguồn URL.",
            parameters={
                "query": "string, truy vấn tìm kiếm đầy đủ",
                "topic": "general hoặc news",
                "max_results": "integer từ 1 đến 5",
            },
            available=bool(self.api_key),
        )

    def run(self, query: str, topic: str = "general", max_results: int = 5, **_: Any) -> ToolResult:
        response = self.client.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "query": query,
                "topic": topic if topic in {"general", "news"} else "general",
                "search_depth": "basic",
                "max_results": max(1, min(int(max_results), 5)),
                "include_answer": False,
                "include_raw_content": False,
                "language": "vi",
            },
        )
        response.raise_for_status()
        results = [{
            "title": item.get("title"),
            "url": item.get("url"),
            "content": item.get("content"),
            "score": item.get("score"),
        } for item in response.json().get("results", [])]
        sources = [item["url"] for item in results if item.get("url")]
        return ToolResult(self.spec.name, json.dumps(results, ensure_ascii=False), sources=sources)

