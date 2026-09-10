from __future__ import annotations

from collections.abc import Iterator

from tourism_agent.domain.models import ChatMessage
from tourism_agent.mcp.client import MCPToolRegistry
from tourism_agent.services.generation import GeminiGenerationService


class MCPRAGService:
    """Compatibility facade for callers that still use the Phase 1 RAG API."""

    def __init__(self, tools: MCPToolRegistry, generator: GeminiGenerationService):
        self.tools = tools
        self.generator = generator

    def stream(self, query: str, history: list[ChatMessage]) -> Iterator[str]:
        result = self.tools.execute("search_tourism_knowledge", {"query": query})
        yield from self.generator.stream_answer(query, result.content, history)
