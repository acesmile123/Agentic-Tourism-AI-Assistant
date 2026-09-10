from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    session_id: str | None = None
    query: str = Field(min_length=1, max_length=4000)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class SessionCreateResponse(BaseModel):
    session_id: str
    created_at: datetime


class SessionInfo(BaseModel):
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class MessageResponse(BaseModel):
    role: str
    content: str
