from datetime import datetime, timezone

import jwt
from fastapi.testclient import TestClient

from tourism_agent.api.app import create_app
from tourism_agent.application.container import Container
from tourism_agent.core.config import Settings
from tourism_agent.domain.models import ChatMessage, ChatSession


class FakeSessions:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.session = ChatSession("s1", "Phiên chat mới", now, now)
        self.messages = []

    def create(self):
        return self.session

    def get_or_create(self, session_id):
        return self.session

    def list(self):
        return [self.session]

    def all_messages(self, session_id):
        return self.messages

    def recent_history(self, session_id):
        return []

    def save_exchange(self, session_id, query, answer):
        self.messages = [ChatMessage("user", query), ChatMessage("assistant", answer)]
        return ChatSession(
            self.session.id, query, self.session.created_at, datetime.now(timezone.utc), 2
        )

    def delete(self, session_id):
        return session_id == "s1"


class FakeAgent:
    def stream(self, query, history, session_id=None):
        yield "Xin "
        yield "chào"


class FakeEventAgent(FakeAgent):
    def stream_events(self, query, history, session_id=None):
        yield {"type": "activity", "id": "planning", "label": "Phân tích yêu cầu", "status": "running"}
        yield {"type": "activity", "id": "planning", "label": "Phân tích yêu cầu", "status": "completed"}
        yield {"type": "token", "token": "Xin chào"}


class FakeRedis:
    def ping(self):
        return True


class FakeRateLimiter:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    def allow_request(self, *args):
        self.calls.append(args)
        return self.allowed


def test_chat_keeps_existing_sse_contract():
    settings = Settings(
        qdrant_url="http://qdrant:6333",
        collection_name="tourism",
        gemini_api_key="test",
    )
    fake_sessions = FakeSessions()

    def factory(current_settings):
        agent = FakeAgent()
        return Container(settings=current_settings, sessions=fake_sessions, rag=agent, agent=agent, redis=FakeRedis())

    app = create_app(settings, factory)
    with TestClient(app) as client:
        response = client.post("/chat", json={"session_id": "s1", "query": "Xin chào"})

    assert response.status_code == 200
    assert '"token": "Xin "' in response.text
    assert '"done": true' in response.text
    assert fake_sessions.messages[-1].content == "Xin chào"

    with TestClient(app) as client:
        messages = client.get("/sessions/s1/messages")
    assert messages.status_code == 200
    assert messages.json()[-1] == {"role": "assistant", "content": "Xin chào"}


def test_chat_rejects_blank_query():
    settings = Settings(qdrant_url="http://qdrant:6333", collection_name="tourism", gemini_api_key="test")

    def factory(current_settings):
        agent = FakeAgent()
        return Container(settings=current_settings, sessions=FakeSessions(), rag=agent, agent=agent, redis=FakeRedis())

    with TestClient(create_app(settings, factory)) as client:
        response = client.post("/chat", json={"query": "   "})
    assert response.status_code == 422


def test_chat_rate_limit_returns_429_before_agent_execution():
    settings = Settings(qdrant_url="http://qdrant:6333", collection_name="tourism", gemini_api_key="test")

    def factory(current_settings):
        agent = FakeAgent()
        return Container(
            settings=current_settings,
            sessions=FakeSessions(),
            rag=agent,
            agent=agent,
            redis=FakeRedis(),
            rate_limiter=FakeRateLimiter(allowed=False),
        )

    with TestClient(create_app(settings, factory)) as client:
        response = client.post("/chat", json={"query": "Xin chào"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


def test_optional_jwt_protects_application_routes_but_not_liveness():
    secret = "a" * 32
    settings = Settings(
        qdrant_url="http://qdrant:6333",
        collection_name="tourism",
        gemini_api_key="test",
        auth_enabled=True,
        jwt_secret=secret,
    )

    def factory(current_settings):
        agent = FakeAgent()
        return Container(settings=current_settings, sessions=FakeSessions(), rag=agent, agent=agent, redis=FakeRedis())

    with TestClient(create_app(settings, factory)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/sessions").status_code == 401
        token = jwt.encode({"sub": "intern", "aud": "tourism-api"}, secret, algorithm="HS256")
        response = client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_chat_streams_safe_activity_events_without_saving_them_as_answer():
    settings = Settings(
        qdrant_url="http://qdrant:6333", collection_name="tourism", gemini_api_key="test"
    )
    fake_sessions = FakeSessions()

    def factory(current_settings):
        agent = FakeEventAgent()
        return Container(
            settings=current_settings,
            sessions=fake_sessions,
            rag=agent,
            agent=agent,
            redis=FakeRedis(),
        )

    with TestClient(create_app(settings, factory)) as client:
        response = client.post("/chat", json={"session_id": "s1", "query": "Lập lịch trình"})

    assert '"event": "activity"' in response.text
    assert '"label": "Phân tích yêu cầu"' in response.text
    assert fake_sessions.messages[-1].content == "Xin chào"
