"""Generated artifacts and immutable content versions."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, IdentityMixin, UpdatedMixin


class Artifact(IdentityMixin, CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "artifacts"
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("app_data.conversations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(20))
    __table_args__ = (CheckConstraint("type IN ('code', 'essay', 'document')", name="type"),)


class ArtifactVersion(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "artifact_versions"
    artifact_id: Mapped[UUID] = mapped_column(ForeignKey("app_data.artifacts.id", ondelete="CASCADE"))
    message_id: Mapped[UUID | None] = mapped_column(ForeignKey("app_data.messages.id", ondelete="SET NULL"))
    version_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(100))
    format: Mapped[str] = mapped_column(String(100), server_default="markdown")
    __table_args__ = (
        UniqueConstraint("artifact_id", "version_number"),
        CheckConstraint("version_number > 0", name="version"),
    )
