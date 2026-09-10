from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from tourism_agent.domain.models import ChatMessage

logger = logging.getLogger(__name__)


class RedisStore:
    """Best-effort cache. PostgreSQL and Qdrant remain the sources of truth."""

    def __init__(self, url: str, memory_ttl: int, cache_ttl: int, key_prefix: str = "tourism"):
        self.client = Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        self.memory_ttl = memory_ttl
        self.cache_ttl = cache_ttl
        self.key_prefix = key_prefix.strip(":")

    def get_history(self, session_id: str) -> list[ChatMessage] | None:
        value = self._get(f"memory:{session_id}")
        if value is None:
            return None
        try:
            return [ChatMessage(item["role"], item["content"]) for item in json.loads(value)]
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def set_history(self, session_id: str, messages: list[ChatMessage]) -> None:
        payload = json.dumps([{"role": m.role, "content": m.content} for m in messages], ensure_ascii=False)
        self._set(f"memory:{session_id}", payload, self.memory_ttl)

    def delete_history(self, session_id: str) -> None:
        try:
            self.client.delete(self._key(f"memory:{session_id}"))
        except RedisError as exc:
            logger.warning("Redis delete failed: %s", exc)

    def get_retrieval(self, query: str, route_key: str) -> list[dict[str, Any]] | None:
        digest = hashlib.sha256(f"{route_key}:{query}".encode()).hexdigest()
        value = self._get(f"retrieval:{digest}")
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def set_retrieval(self, query: str, route_key: str, docs: list[dict[str, Any]]) -> None:
        digest = hashlib.sha256(f"{route_key}:{query}".encode()).hexdigest()
        self._set(f"retrieval:{digest}", json.dumps(docs, ensure_ascii=False, default=str), self.cache_ttl)

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except RedisError:
            return False

    def allow_request(self, scope: str, identity: str, limit: int, window_seconds: int) -> bool:
        """Fixed-window Redis rate limit; fails open if Redis is unavailable."""
        if limit <= 0 or window_seconds <= 0:
            return True
        bucket = int(time.time() // window_seconds)
        key = self._key(f"rate:{scope}:{bucket}:{identity}")
        try:
            with self.client.pipeline(transaction=True) as pipeline:
                pipeline.incr(key)
                pipeline.expire(key, window_seconds * 2, nx=True)
                count, _ = pipeline.execute()
            return int(count) <= limit
        except RedisError as exc:
            logger.warning("Redis rate limit failed open: %s", exc)
            return True

    def _get(self, key: str) -> str | None:
        try:
            return self.client.get(self._key(key))
        except RedisError as exc:
            logger.warning("Redis read failed: %s", exc)
            return None

    def _set(self, key: str, value: str, ttl: int) -> None:
        try:
            self.client.setex(self._key(key), ttl, value)
        except RedisError as exc:
            logger.warning("Redis write failed: %s", exc)

    def _key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}" if self.key_prefix else key
