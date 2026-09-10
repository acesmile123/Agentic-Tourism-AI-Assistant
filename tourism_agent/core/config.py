from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Vietnam Tourism AI Platform"
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: Annotated[list[str], NoDecode, BeforeValidator(_split_csv)] = ["http://localhost:5173"]

    database_url: str = "postgresql+psycopg://tourism:tourism@localhost:5432/tourism"
    redis_url: str = "redis://localhost:6379/0"
    # Keep the legacy URL for local development; production can isolate workloads
    # in separate Redis databases or separate ElastiCache clusters.
    redis_memory_url: str = ""
    redis_cache_url: str = ""
    redis_rate_limit_url: str = ""
    redis_key_prefix: str = "tourism"
    redis_memory_ttl_seconds: int = 3600
    redis_cache_ttl_seconds: int = 900
    memory_message_limit: int = 6

    rate_limit_enabled: bool = True
    rate_limit_requests: int = 20
    rate_limit_window_seconds: int = 60
    trusted_proxy_headers: bool = False

    auth_enabled: bool = False
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_audience: str = "tourism-api"

    qdrant_url: str
    qdrant_api_key: str | None = None
    collection_name: str
    embed_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    retrieval_k: int = 25
    retrieval_top_n: int = 7
    context_max_chars: int = 4500

    cohere_api_key: str = ""
    cohere_rerank_model: str = "rerank-v4.0-pro"
    cohere_timeout_seconds: float = 10.0

    openweather_api_key: str = ""
    goong_api_key: str = ""
    goong_base_url: str = "https://rsapi.goong.io"
    tavily_api_key: str = ""
    tool_http_timeout_seconds: float = 10.0

    mcp_server_url: str = "http://localhost:8001/mcp"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8001
    mcp_read_timeout_seconds: float = 45.0
    mcp_discovery_ttl_seconds: int = 300
    adaptive_retrieval_threshold: float = 0.3
    agent_max_retries: int = 1

    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_sample_rate: float = 1.0

    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    gemini_fast_model: str = "gemini-3.5-flash"
    gemini_complex_model: str = "gemini-3.6-flash"

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.app_env.lower() == "production":
            placeholders = {"replace-me", "your-key", "your-existing-collection"}
            if self.gemini_api_key in placeholders or self.qdrant_url.endswith("your-cluster.region.cloud.qdrant.io:6333"):
                raise ValueError("Production configuration contains placeholder secrets or Qdrant URL")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS must list explicit origins in production")
        if self.auth_enabled and len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters when AUTH_ENABLED=true")
        return self

    @property
    def memory_redis_url(self) -> str:
        return self.redis_memory_url or self.redis_url

    @property
    def cache_redis_url(self) -> str:
        return self.redis_cache_url or self.redis_url

    @property
    def rate_limit_redis_url(self) -> str:
        return self.redis_rate_limit_url or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
