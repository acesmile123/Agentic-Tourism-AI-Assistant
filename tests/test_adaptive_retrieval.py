import json

from langchain_core.documents import Document

from tourism_agent.services.retrieval import RetrievalResult
from tourism_agent.tools.base import ToolResult, ToolSpec
from tourism_agent.tools.tourism_search import TourismKnowledgeTool


class FakeRetriever:
    def __init__(self, confidence: float):
        self.confidence = confidence

    def retrieve_with_confidence(self, query):
        document = Document(
            page_content="Nội dung nội bộ",
            metadata={"source": "https://internal.example", "_qdrant_score": self.confidence},
        )
        return RetrievalResult([document], self.confidence, route=None, cache_hit=False)


class FakeWebSearch:
    calls = 0

    @property
    def spec(self):
        return ToolSpec("web_search", "web", {}, available=True)

    def run(self, **kwargs):
        self.calls += 1
        return ToolResult(
            "web_search",
            json.dumps([{"title": "Nguồn mới", "url": "https://web.example", "content": "Mới"}]),
            sources=["https://web.example"],
        )


def test_low_score_triggers_structured_web_fallback():
    web = FakeWebSearch()
    tool = TourismKnowledgeTool(FakeRetriever(0.2), web_search=web, confidence_threshold=0.3)

    result = tool.run("địa điểm này có gì?")
    payload = json.loads(result.content)

    assert web.calls == 1
    assert payload["web_fallback"]["used"] is True
    assert "low_internal_score" in payload["web_fallback"]["reasons"]
    assert "https://web.example" in result.sources


def test_fresh_query_falls_back_even_when_internal_score_is_high():
    web = FakeWebSearch()
    tool = TourismKnowledgeTool(FakeRetriever(0.8), web_search=web, confidence_threshold=0.3)

    payload = json.loads(tool.run("giá vé hôm nay là bao nhiêu?").content)

    assert web.calls == 1
    assert payload["web_fallback"]["reasons"] == ["freshness_sensitive_query"]


def test_high_score_stable_query_uses_internal_knowledge_only():
    web = FakeWebSearch()
    tool = TourismKnowledgeTool(FakeRetriever(0.8), web_search=web, confidence_threshold=0.3)

    payload = json.loads(tool.run("lịch sử phố cổ Hội An").content)

    assert web.calls == 0
    assert payload["web_fallback"]["used"] is False
