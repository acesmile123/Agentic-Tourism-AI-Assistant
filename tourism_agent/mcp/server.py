from __future__ import annotations

import json
from typing import Any

from mcp.server import MCPServer

from tourism_agent.core.config import Settings, get_settings
from tourism_agent.infrastructure.redis_store import RedisStore
from tourism_agent.observability import build_observability
from tourism_agent.services.generation import GeminiGenerationService
from tourism_agent.services.reranking import CohereReranker
from tourism_agent.services.retrieval import HybridRetriever
from tourism_agent.tools.base import ToolRegistry, ToolResult
from tourism_agent.tools.budget import BudgetCalculatorTool
from tourism_agent.tools.goong import GoongPlacesTool
from tourism_agent.tools.tourism_search import TourismKnowledgeTool
from tourism_agent.tools.weather import WeatherTool
from tourism_agent.tools.web_search import TavilyWebSearchTool


def build_tool_registry(settings: Settings, observer=None) -> ToolRegistry:
    """Construct providers once; the MCP process owns all tool dependencies."""
    redis = RedisStore(
        settings.cache_redis_url,
        settings.redis_memory_ttl_seconds,
        settings.redis_cache_ttl_seconds,
        key_prefix=f"{settings.redis_key_prefix}:retrieval",
    )
    generator = GeminiGenerationService(
        settings.gemini_api_key,
        settings.gemini_fast_model,
        settings.gemini_complex_model,
        observer=observer,
    )
    reranker = CohereReranker(
        api_key=settings.cohere_api_key,
        model=settings.cohere_rerank_model,
        timeout_seconds=settings.cohere_timeout_seconds,
    )
    retriever = HybridRetriever(
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name=settings.collection_name,
        embed_model=settings.embed_model,
        reranker=reranker,
        llm=generator,
        cache=redis,
        retrieval_k=settings.retrieval_k,
        top_n=settings.retrieval_top_n,
        observer=observer,
    )
    web = TavilyWebSearchTool(settings.tavily_api_key, settings.tool_http_timeout_seconds)
    return ToolRegistry([
        TourismKnowledgeTool(
            retriever,
            settings.context_max_chars,
            web_search=web,
            confidence_threshold=settings.adaptive_retrieval_threshold,
        ),
        WeatherTool(settings.openweather_api_key, settings.tool_http_timeout_seconds),
        GoongPlacesTool(
            settings.goong_api_key,
            settings.tool_http_timeout_seconds,
            base_url=settings.goong_base_url,
        ),
        BudgetCalculatorTool(),
        web,
    ], observer=observer)


def _json_result(result: ToolResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False)


def create_mcp_server(registry: ToolRegistry, settings: Settings) -> MCPServer:
    """Expose domain tools through MCP without coupling the agent to providers."""
    server = MCPServer(
        "Vietnam Tourism Tools",
        instructions=(
            "Reusable tourism capabilities. Prefer search_tourism_knowledge for stable "
            "Vietnam tourism facts; it automatically augments weak or time-sensitive retrieval with web results."
        ),
    )
    available = {spec.name for spec in registry.specs() if spec.available}

    if "search_tourism_knowledge" in available:
        @server.tool()
        def search_tourism_knowledge(query: str) -> str:
            """Search internal tourism knowledge with adaptive, cited web fallback."""
            return _json_result(registry.execute("search_tourism_knowledge", {"query": query}))

    if "weather" in available:
        @server.tool()
        def weather(location: str, forecast: bool = False) -> str:
            """Get current weather or a five-day forecast for a location."""
            return _json_result(registry.execute("weather", {"location": location, "forecast": forecast}))

    if "map_location" in available:
        @server.tool()
        def map_location(query: str, limit: int = 1) -> str:
            """Find Vietnam places, addresses, coordinates, and map links via Goong."""
            return _json_result(registry.execute("map_location", {"query": query, "limit": limit}))

    if "budget_calculator" in available:
        @server.tool()
        def budget_calculator(
            destination: str,
            days: int,
            travelers: int = 1,
            style: str = "mid_range",
            transport_vnd: float = 0,
        ) -> str:
            """Estimate a Vietnam trip budget in VND."""
            return _json_result(registry.execute("budget_calculator", {
                "destination": destination,
                "days": days,
                "travelers": travelers,
                "style": style,
                "transport_vnd": transport_vnd,
            }))

    if "web_search" in available:
        @server.tool()
        def web_search(query: str, topic: str = "general", max_results: int = 5) -> str:
            """Search the web for recent information and source URLs."""
            return _json_result(registry.execute("web_search", {
                "query": query,
                "topic": topic,
                "max_results": max_results,
            }))

    @server.resource("tourism://tools/catalog")
    def tool_catalog() -> str:
        """Tool catalog and runtime availability."""
        return json.dumps([
            {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
                "available": spec.available,
            }
            for spec in registry.specs()
        ], ensure_ascii=False)

    @server.resource("tourism://retrieval/policy")
    def retrieval_policy() -> str:
        """Current adaptive retrieval and freshness policy."""
        return json.dumps({
            "hybrid_retrieval": "Qdrant dense+sparse RRF, then Cohere reranking",
            "confidence_signal": "maximum Qdrant hybrid score",
            "fallback_threshold": settings.adaptive_retrieval_threshold,
            "freshness_override": True,
            "fallback_provider": "Tavily when configured",
        }, ensure_ascii=False)

    return server


def main() -> None:
    settings = get_settings()
    observer = build_observability(settings)
    server = create_mcp_server(build_tool_registry(settings, observer), settings)
    try:
        server.run(
            transport="streamable-http",
            host=settings.mcp_host,
            port=settings.mcp_port,
            streamable_http_path="/mcp",
            json_response=True,
        )
    finally:
        observer.flush()


if __name__ == "__main__":
    main()
