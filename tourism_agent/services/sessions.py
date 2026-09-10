from __future__ import annotations

from tourism_agent.domain.models import ChatMessage, ChatSession
from tourism_agent.infrastructure.redis_store import RedisStore
from tourism_agent.infrastructure.session_repository import PostgresSessionRepository


class SessionService:
    def __init__(self, repository: PostgresSessionRepository, memory: RedisStore, memory_limit: int = 6):
        self.repository = repository
        self.memory = memory
        self.memory_limit = memory_limit

    def create(self) -> ChatSession:
        return self.repository.create()

    def get_or_create(self, session_id: str | None) -> ChatSession:
        if session_id:
            existing = self.repository.get(session_id)
            if existing:
                return existing
        return self.create()

    def list(self) -> list[ChatSession]:
        return self.repository.list()

    def all_messages(self, session_id: str) -> list[ChatMessage]:
        if not self.repository.get(session_id):
            raise KeyError(session_id)
        return self.repository.messages(session_id)

    def recent_history(self, session_id: str) -> list[ChatMessage]:
        cached = self.memory.get_history(session_id)
        if cached is not None:
            return cached
        messages = self.repository.messages(session_id, self.memory_limit)
        self.memory.set_history(session_id, messages)
        return messages

    def save_exchange(self, session_id: str, query: str, answer: str) -> ChatSession:
        session = self.repository.append_exchange(session_id, query, answer)
        recent = self.repository.messages(session_id, self.memory_limit)
        self.memory.set_history(session_id, recent)
        return session

    def delete(self, session_id: str) -> bool:
        deleted = self.repository.delete(session_id)
        if deleted:
            self.memory.delete_history(session_id)
        return deleted

    def ping(self) -> bool:
        return self.repository.ping()
