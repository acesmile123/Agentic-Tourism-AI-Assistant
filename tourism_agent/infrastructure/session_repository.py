from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from tourism_agent.domain.models import ChatMessage, ChatSession
from tourism_agent.infrastructure.database import MessageRecord, SessionRecord


class PostgresSessionRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def create(self) -> ChatSession:
        now = datetime.now(timezone.utc)
        record = SessionRecord(id=str(uuid4()), title="Phiên chat mới", created_at=now, updated_at=now)
        with self._session_factory.begin() as db:   
            db.add(record)
        return self._to_domain(record, 0)

    def get(self, session_id: str) -> ChatSession | None:
        with self._session_factory() as db:
            row = db.execute(
                select(SessionRecord, func.count(MessageRecord.id)) 
                .outerjoin(MessageRecord)
                .where(SessionRecord.id == session_id)
                .group_by(SessionRecord.id)
            ).one_or_none()
            return self._to_domain(row[0], row[1]) if row else None

    def list(self) -> list[ChatSession]:
        with self._session_factory() as db:
            rows = db.execute(
                select(SessionRecord, func.count(MessageRecord.id))
                .outerjoin(MessageRecord)
                .group_by(SessionRecord.id)
                .order_by(SessionRecord.updated_at.desc())
            ).all()
            return [self._to_domain(record, count) for record, count in rows]

    def messages(self, session_id: str, limit: int | None = None) -> list[ChatMessage]:
        statement = select(MessageRecord).where(MessageRecord.session_id == session_id)
        if limit:
            statement = statement.order_by(MessageRecord.created_at.desc(), MessageRecord.id.desc()).limit(limit)
        else:
            statement = statement.order_by(MessageRecord.created_at, MessageRecord.id)
        with self._session_factory() as db:
            records = list(db.scalars(statement))
        if limit:
            records.reverse()
        return [ChatMessage(r.role, r.content, r.created_at) for r in records]

    def append_exchange(self, session_id: str, query: str, answer: str) -> ChatSession:
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as db:
            record = db.get(SessionRecord, session_id)
            if record is None:
                raise KeyError(session_id)
            db.add_all([
                MessageRecord(session_id=session_id, role="user", content=query, created_at=now),
                MessageRecord(session_id=session_id, role="assistant", content=answer, created_at=now),
            ])
            record.updated_at = now
            if record.title == "Phiên chat mới":
                clean = query.strip()
                record.title = clean[:45] + ("…" if len(clean) > 45 else "")
        return self.get(session_id)  # type: ignore[return-value]

    def delete(self, session_id: str) -> bool:
        with self._session_factory.begin() as db:
            record = db.get(SessionRecord, session_id)
            if record is None:
                return False
            db.delete(record)
            return True

    def ping(self) -> bool:
        try:
            with self._session_factory() as db:
                db.execute(select(1))
            return True
        except Exception:
            return False

    @staticmethod
    def _to_domain(record: SessionRecord, count: int) -> ChatSession:
        return ChatSession(record.id, record.title, record.created_at, record.updated_at, count)
