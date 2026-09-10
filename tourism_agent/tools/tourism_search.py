from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from tourism_agent.services.retrieval import HybridRetriever
from tourism_agent.tools.base import ToolResult, ToolSpec
from tourism_agent.tools.web_search import TavilyWebSearchTool


class TourismKnowledgeTool:
    name = "search_tourism_knowledge"
    description = "Tìm kiếm tri thức du lịch Việt Nam bằng dense+sparse hybrid retrieval và reranking."

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters={"query": "string, câu hỏi du lịch Việt Nam cần tra cứu"},
        )

    FRESHNESS_PATTERN = re.compile(
        r"hôm nay|hiện tại|hiện nay|mới nhất|mới mở|sắp tới|sự kiện|lễ hội|"
        r"giờ mở cửa|giá vé|vé máy bay|chuyến bay",
        re.IGNORECASE,
    )

    def __init__(
        self,
        retriever: HybridRetriever,
        max_context_chars: int = 4500,
        web_search: TavilyWebSearchTool | None = None,
        confidence_threshold: float = 0.3,
    ):
        self.retriever = retriever
        self.max_context_chars = max_context_chars
        self.web_search = web_search
        self.confidence_threshold = confidence_threshold

    def run(self, query: str) -> ToolResult:
        retrieval = self.retriever.retrieve_with_confidence(query)
        chunks: list[dict] = []
        total = 0
        sources: list[str] = []
        for index, doc in enumerate(retrieval.documents, 1):
            if total + len(doc.page_content) > self.max_context_chars:
                break
            source = doc.metadata.get("source")
            if source and source not in sources:
                sources.append(str(source))
            chunks.append({
                "rank": index,
                "content": doc.page_content,
                "source": source,
                "qdrant_score": doc.metadata.get("_qdrant_score"),
                "rerank_score": doc.metadata.get("_rerank_score"),
            })
            total += len(doc.page_content)

        reasons = []
        if retrieval.confidence < self.confidence_threshold:
            reasons.append("low_internal_score")
        if self.FRESHNESS_PATTERN.search(query):
            reasons.append("freshness_sensitive_query")

        web_payload = None
        web_attempted = False
        if reasons and self.web_search is not None and self.web_search.spec.available:
            web_attempted = True
            web_query = query
            if "freshness_sensitive_query" in reasons:
                today = datetime.now(timezone.utc).date().isoformat()
                web_query = f"{query} Việt Nam cập nhật {today} nguồn chính thức"
            web_result = self.web_search.run(query=web_query, topic="general", max_results=5)
            if web_result.success:
                try:
                    web_payload = json.loads(web_result.content)
                except json.JSONDecodeError:
                    web_payload = web_result.content
                sources.extend(source for source in web_result.sources if source not in sources)

        payload = {
            "query": query,
            "internal_retrieval": {
                "confidence": retrieval.confidence,
                "threshold": self.confidence_threshold,
                "cache_hit": retrieval.cache_hit,
                "chunks": chunks,
            },
            "web_fallback": {
                "used": web_payload is not None,
                "attempted": web_attempted,
                "reasons": reasons,
                "results": web_payload,
            },
            "answer_guidance": (
                "Ưu tiên dữ liệu nội bộ khi phù hợp. Nếu có web fallback, dùng để bổ sung/cập nhật, "
                "đối chiếu nhiều nguồn và luôn gắn URL. Nói rõ khi dữ liệu chưa được xác minh."
            ),
        }
        return ToolResult(self.name, json.dumps(payload, ensure_ascii=False), sources=sources)
