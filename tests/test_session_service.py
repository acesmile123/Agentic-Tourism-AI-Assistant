from datetime import datetime, timezone

from tourism_agent.domain.models import ChatMessage, ChatSession
from tourism_agent.services.sessions import SessionService


class FakeRepository:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.session = ChatSession("s1", "Phiên chat mới", now, now)
        self.history = [ChatMessage("user", "xin chào")]

    def get(self, session_id):
        return self.session if session_id == "s1" else None

    def messages(self, session_id, limit=None):
        return self.history[-limit:] if limit else self.history


class FakeMemory:
    def __init__(self):
        self.history = None

    def get_history(self, session_id):
        return self.history

    def set_history(self, session_id, history):
        self.history = history


def test_recent_history_falls_back_to_database_and_warms_redis():
    memory = FakeMemory()
    service = SessionService(FakeRepository(), memory, memory_limit=6)

    result = service.recent_history("s1")

    assert result[0].content == "xin chào"
    assert memory.history == result

