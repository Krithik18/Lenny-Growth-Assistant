"""Private profiles, conversations, messages, and generation attempts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, IdentityMixin, UpdatedMixin


class Profile(CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "profiles"
    # Supabase owns auth.users. The migration adds its FK without managing that table.
    id: Mapped[UUID] = mapped_column(primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    preferred_provider: Mapped[str | None] = mapped_column(String(30))
    preferred_model: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (CheckConstraint("preferred_provider IN ('openai', 'ollama')", name="provider"),)


class Conversation(IdentityMixin, CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "conversations"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app_data.profiles.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), server_default="New chat")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(IdentityMixin, CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("app_data.conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, server_default="")
    mode: Mapped[str] = mapped_column(String(20), server_default="answer")
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    sequence_number: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_number"),
        UniqueConstraint("id", "conversation_id", name="uq_messages_id_conversation"),
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        CheckConstraint("mode IN ('answer', 'essay', 'code')", name="mode"),
        CheckConstraint("status IN ('pending', 'streaming', 'completed', 'failed', 'cancelled')", name="status"),
        CheckConstraint("sequence_number >= 0", name="sequence"),
    )


class Generation(IdentityMixin, Base):
    __tablename__ = "generations"
    user_message_id: Mapped[UUID] = mapped_column(ForeignKey("app_data.messages.id", ondelete="CASCADE"), index=True)
    assistant_message_id: Mapped[UUID | None] = mapped_column(ForeignKey("app_data.messages.id", ondelete="SET NULL"))
    client_request_id: Mapped[UUID] = mapped_column()
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("user_message_id", "client_request_id"),
        CheckConstraint("provider IN ('openai', 'ollama')", name="provider"),
        CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'cancelled')", name="status"),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="tokens"),
        CheckConstraint("finished_at >= started_at", name="timing"),
    )
