from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tourism_agent.agent.planner import AgentPlanner
from tourism_agent.agent.workflow import AgentWorkflow
from tourism_agent.core.config import Settings
from tourism_agent.infrastructure.database import build_session_factory
from tourism_agent.infrastructure.redis_store import RedisStore
from tourism_agent.infrastructure.session_repository import PostgresSessionRepository
from tourism_agent.mcp.client import MCPToolRegistry
from tourism_agent.observability import build_observability
from tourism_agent.services.generation import GeminiGenerationService
from tourism_agent.services.mcp_rag import MCPRAGService
from tourism_agent.services.sessions import SessionService


@dataclass
class Container:
    settings: Settings
    sessions: SessionService
    rag: MCPRAGService
    agent: AgentWorkflow
    redis: RedisStore
    observer: Any = None
    rate_limiter: RedisStore | None = None


def build_container(settings: Settings) -> Container:
    observer = build_observability(settings)
    memory_redis = RedisStore(
        settings.memory_redis_url,
        settings.redis_memory_ttl_seconds,
        settings.redis_cache_ttl_seconds,
        key_prefix=f"{settings.redis_key_prefix}:memory",
    )
    rate_limiter = RedisStore(
        settings.rate_limit_redis_url,
        settings.redis_memory_ttl_seconds,
        settings.redis_cache_ttl_seconds,
        key_prefix=f"{settings.redis_key_prefix}:ratelimit",
    )
    repository = PostgresSessionRepository(build_session_factory(settings.database_url))
    sessions = SessionService(repository, memory_redis, settings.memory_message_limit)
    generator = GeminiGenerationService(
        settings.gemini_api_key, settings.gemini_fast_model, settings.gemini_complex_model,
        observer=observer,
    )
    tools = MCPToolRegistry(
        settings.mcp_server_url,
        read_timeout_seconds=settings.mcp_read_timeout_seconds,
        discovery_ttl_seconds=settings.mcp_discovery_ttl_seconds,
        observer=observer,
    )
    rag = MCPRAGService(tools, generator)
    agent = AgentWorkflow(
        AgentPlanner(generator),
        tools,
        generator,
        max_retries=settings.agent_max_retries,
        observer=observer,
    )
    return Container(
        settings=settings,
        sessions=sessions,
        rag=rag,
        agent=agent,
        redis=memory_redis,
        observer=observer,
        rate_limiter=rate_limiter,
    )
