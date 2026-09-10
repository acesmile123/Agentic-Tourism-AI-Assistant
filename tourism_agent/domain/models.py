from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class ChatSession:
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

