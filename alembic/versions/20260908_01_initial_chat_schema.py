"""initial chat schema

Revision ID: 20260908_01
Revises:
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260908_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "chat_sessions" not in tables:
        op.create_table(
            "chat_sessions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("title", sa.String(length=120), nullable=False, server_default="Phiên chat mới"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "chat_messages" not in tables:
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_messages_role"),
            sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        )
    # IF NOT EXISTS makes repeated local and production deployments idempotent.
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_sessions_updated_at ON chat_sessions (updated_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id ON chat_messages (session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_messages_session_created ON chat_messages (session_id, created_at)")


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_created", table_name="chat_messages")
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_updated_at", table_name="chat_sessions")
    op.drop_table("chat_sessions")
