# Phase 1 — Modular production foundation

## Architecture

```text
HTTP/SSE (tourism_agent/api)
        |
Application container + session orchestration
        |-- PostgreSQL repository (durable sessions/messages)
        |-- Redis (short-term history + retrieval cache)
        `-- RAG service
              |-- TourismKnowledgeTool
              |     `-- Qdrant hybrid RRF -> Cohere Rerank API
              `-- Gemini generation + complexity model router
```

PostgreSQL and your existing Qdrant Cloud collection are sources of truth. Redis is best-effort: a Redis failure falls back to PostgreSQL for chat history and to Qdrant Cloud for retrieval.

## Run locally

1. Keep the existing `QDRANT_URL`, `QDRANT_API_KEY`, `COLLECTION_NAME`, and `EMBED_MODEL` values in `.env`; add `GEMINI_API_KEY`, `COHERE_API_KEY`, and the PostgreSQL/Redis settings from `.env.example`.
2. Start services: `docker compose up --build`.
3. The API connects directly to the existing Qdrant Cloud collection. There is no crawl, chunk, embedding, or upload step during application startup.
4. Open API docs at `http://localhost:8000/docs`.

The React frontend can continue using the existing session and `/chat` SSE contracts. Set its API URL to `http://localhost:8000`.

## Cohere reranking

- `COHERE_RERANK_MODEL=rerank-v4.0-pro` prioritizes multilingual ranking quality.
- Use `rerank-v4.0-fast` when latency and throughput matter more.
- When Cohere times out, is rate-limited, or is unavailable, retrieval falls back to Qdrant's hybrid RRF order.
- The local dense embedding model is still required for querying the existing Qdrant dense vectors; only the local cross-encoder reranker has been removed.

## Gemini model routing

- `GEMINI_FAST_MODEL=gemini-3.5-flash` handles query rewriting, intent classification, and normal answers.
- `GEMINI_COMPLEX_MODEL=gemini-3.6-flash` handles itinerary, comparison, budget, analysis, and long multi-constraint questions.
- Routing is deterministic, so it does not add a classification API call before generation.

## Test

Run `pytest -q`. Unit/API tests use fakes and do not require PostgreSQL, Redis, Qdrant, or a Gemini key.
