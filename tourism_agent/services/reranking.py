from __future__ import annotations

import logging
from typing import Protocol

import cohere
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    @property
    def cache_namespace(self) -> str: ...

    def rerank(self, query: str, documents: list[Document], top_n: int) -> list[Document]: ...


class CohereReranker:
    """Cohere Rerank V2 adapter with RRF-order fallback on API failure."""

    def __init__(
        self,
        api_key: str,
        model: str = "rerank-v4.0-pro",
        timeout_seconds: float = 10.0,
        client=None,
    ):
        if not api_key and client is None:
            raise ValueError("COHERE_API_KEY is required")
        self.model = model
        self.client = client or cohere.ClientV2(api_key=api_key, timeout=timeout_seconds)

    @property
    def cache_namespace(self) -> str:
        return f"cohere:{self.model}"

    def rerank(self, query: str, documents: list[Document], top_n: int) -> list[Document]:
        if not documents:
            return []
        try:
            response = self.client.rerank(
                model=self.model,
                query=query,
                documents=[document.page_content for document in documents],
                top_n=min(top_n, len(documents)),
            )
            reranked = []
            for result in response.results:
                document = documents[result.index]
                document.metadata = {
                    **document.metadata,
                    "_rerank_score": float(result.relevance_score),
                }
                reranked.append(document)
            return reranked
        except Exception as exc:
            # Retrieval remains available when Cohere is rate-limited or temporarily down.
            logger.warning("Cohere rerank failed; using Qdrant RRF order: %s", exc)
            return documents[:top_n]
