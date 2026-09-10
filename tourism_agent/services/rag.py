from __future__ import annotations

from collections.abc import Iterator

from tourism_agent.domain.models import ChatMessage
from tourism_agent.services.generation import GeminiGenerationService
from tourism_agent.services.retrieval import HybridRetriever
from tourism_agent.tools.tourism_search import TourismKnowledgeTool


class RAGService:
    """Standalone RAG capability that can later be registered as an agent tool."""

    def __init__(self, retriever: HybridRetriever, generator: GeminiGenerationService, context_max_chars: int):
        self.retriever = retriever
        self.generator = generator
        self.search_tool = TourismKnowledgeTool(retriever, context_max_chars)

    def stream(self, query: str, history: list[ChatMessage]) -> Iterator[str]:
        standalone = self.retriever.condense(query, history)
        result = self.search_tool.run(standalone)
        yield from self.generator.stream_answer(query, result.content, history)
