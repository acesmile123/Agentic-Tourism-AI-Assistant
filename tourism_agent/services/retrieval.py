from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdm

from tourism_agent.infrastructure.redis_store import RedisStore
from tourism_agent.services.generation import GeminiGenerationService
from tourism_agent.services.reranking import Reranker


@dataclass(frozen=True)
class QueryRoute:
    province: str | None
    category: str | None
    qdrant_filter: qdm.Filter | None

    @property
    def cache_key(self) -> str:
        return f"{self.province or '*'}:{self.category or '*'}"


@dataclass(frozen=True)
class RetrievalResult:
    documents: list[Document]
    confidence: float
    route: QueryRoute
    cache_hit: bool = False


class HybridRetriever:
    """Qdrant dense+sparse RRF retrieval followed by Cohere reranking."""

    def __init__(
        self,
        qdrant_url: str,
        qdrant_api_key: str | None,
        collection_name: str,
        embed_model: str,
        reranker: Reranker,
        llm: GeminiGenerationService,
        cache: RedisStore,
        retrieval_k: int = 25,
        top_n: int = 7,
        observer=None,
    ):
        from tourism_agent.observability import NoOpObservability

        self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        self.collection_name = collection_name
        self.llm = llm
        self.cache = cache
        self.retrieval_k = retrieval_k
        self.top_n = top_n
        self.reranker = reranker
        self.observer = observer or NoOpObservability()
        self.embeddings = HuggingFaceEmbeddings(
            model_name=embed_model, encode_kwargs={"normalize_embeddings": True}
        )
        self.vectorstore = QdrantVectorStore(
            client=self.client,
            collection_name=collection_name,
            embedding=self.embeddings,
            sparse_embedding=FastEmbedSparse(model_name="Qdrant/bm25"),
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name="dense",
            sparse_vector_name="sparse",
            content_payload_key="content",
            metadata_payload_key=None,
        )
        self.provinces = self._load_provinces()

    def condense(self, query: str, history: list) -> str:
        if not history:
            return query
        history_text = "\n".join(f"{m.role}: {m.content[:200]}" for m in history[-6:])
        return self.llm.complete(
            "Viết lại câu hỏi cuối thành câu hỏi tiếng Việt độc lập. Chỉ trả về câu hỏi.\n"
            f"Lịch sử:\n{history_text}\nCâu hỏi cuối: {query}"
        )

    def retrieve(self, query: str) -> list[Document]:
        return self.retrieve_with_confidence(query).documents

    def retrieve_with_confidence(self, query: str) -> RetrievalResult:
        with self.observer.span(
            "qdrant.hybrid_retrieval",
            as_type="retriever",
            input={"query": query, "k": self.retrieval_k, "top_n": self.top_n},
        ) as span:
            result = self._retrieve_with_confidence(query)
            span.update(output={
                "confidence": result.confidence,
                "cache_hit": result.cache_hit,
                "route": {
                    "province": result.route.province,
                    "category": result.route.category,
                },
                "documents": [
                    {
                        "content": document.page_content[:1000],
                        "metadata": document.metadata,
                    }
                    for document in result.documents
                ],
            })
            return result

    def _retrieve_with_confidence(self, query: str) -> RetrievalResult:
        route = self._route(query)
        cache_key = f"{route.cache_key}:{self.reranker.cache_namespace}"
        cached = self.cache.get_retrieval(query, cache_key)
        if cached is not None:
            documents = [
                Document(page_content=item["content"], metadata=item.get("metadata", {}))
                for item in cached
            ]
            confidence = max(
                (float(document.metadata.get("_qdrant_score", 0.0)) for document in documents),
                default=0.0,
            )
            return RetrievalResult(documents, confidence, route, cache_hit=True)

        scored_docs = self.vectorstore.similarity_search_with_score(
            query=query, k=self.retrieval_k, filter=route.qdrant_filter
        )
        if len(scored_docs) < 3 and route.qdrant_filter is not None:
            scored_docs = self.vectorstore.similarity_search_with_score(query=query, k=self.retrieval_k)
        docs: list[Document] = []
        scores: list[float] = []
        for document, score in scored_docs:
            value = float(score)
            document.metadata = {**document.metadata, "_qdrant_score": value}
            docs.append(document)
            scores.append(value)
        reranked = self.reranker.rerank(query, docs, self.top_n)
        self.cache.set_retrieval(
            query,
            cache_key,
            [{"content": d.page_content, "metadata": d.metadata} for d in reranked],
        )
        return RetrievalResult(reranked, max(scores, default=0.0), route)

    def _route(self, query: str) -> QueryRoute:
        province = self._detect_province(query)
        prompt = (
            "Phân loại câu hỏi du lịch. Trả JSON với type thuộc một trong: "
            "destination, food, transportation, accommodation, pricing, schedule, general, null.\n"
            f"Câu hỏi: {query}"
        )
        category = self.llm.extract_json(self.llm.complete(prompt, json_output=True)).get("type")
        allowed_categories = {
            "destination", "food", "transportation", "accommodation",
            "pricing", "schedule", "general", "null",
        }
        if category not in allowed_categories:
            category = None
        must = []
        should = []
        if province:
            must.append(qdm.FieldCondition(key="province", match=qdm.MatchValue(value=province)))
        if category not in (None, "null", "general"):
            should.extend([
                qdm.FieldCondition(key="type", match=qdm.MatchValue(value=category)),
                qdm.FieldCondition(key="type", match=qdm.MatchValue(value="general")),
            ])
        query_filter = qdm.Filter(must=must or None, should=should or None) if must or should else None
        return QueryRoute(province, category, query_filter)

    def _load_provinces(self) -> list[str]:
        provinces: set[str] = set()
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=256,
                offset=offset,
                with_payload=["province"],
                with_vectors=False,
            )
            provinces.update(
                point.payload["province"] for point in points if point.payload and point.payload.get("province")
            )
            if offset is None:
                break
        return sorted(provinces, key=len, reverse=True)

    def _detect_province(self, query: str) -> str | None:
        normalized_query = self._normalize(query)
        for province in self.provinces:
            name = self._normalize(province.replace("_", " "))
            if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", normalized_query):
                return province
        return None

    @staticmethod
    def _normalize(text: str) -> str:
        value = unicodedata.normalize("NFD", text.casefold())
        return "".join(char for char in value if unicodedata.category(char) != "Mn")
