"""Versioned transcript storage and links from answers to supporting passages."""

from datetime import date, datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, IdentityMixin, UpdatedMixin


class IngestionRun(IdentityMixin, Base):
    __tablename__ = "ingestion_runs"
    source_commit: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), server_default="running")
    episodes_processed: Mapped[int] = mapped_column(Integer, server_default="0")
    episodes_failed: Mapped[int] = mapped_column(Integer, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("status IN ('running', 'completed', 'failed')", name="status"),
        CheckConstraint("episodes_processed >= 0 AND episodes_failed >= 0", name="counts"),
    )


class Episode(IdentityMixin, CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "episodes"
    title: Mapped[str] = mapped_column(Text)
    guest: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    youtube_url: Mapped[str | None] = mapped_column(Text)
    video_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    published_at: Mapped[date | None] = mapped_column(Date)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    repository_path: Mapped[str] = mapped_column(Text, unique=True)
    active_revision_id: Mapped[UUID | None] = mapped_column()
    __table_args__ = (
        CheckConstraint("duration_seconds >= 0", name="duration"),
        ForeignKeyConstraint(
            ["active_revision_id", "id"], ["app_data.episode_revisions.id", "app_data.episode_revisions.episode_id"],
            name="fk_episodes_active_revision", use_alter=True,
        ),
    )


class EpisodeRevision(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "episode_revisions"
    episode_id: Mapped[UUID] = mapped_column(ForeignKey("app_data.episodes.id", ondelete="RESTRICT"), index=True)
    source_commit: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    transcript_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    ingestion_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("app_data.ingestion_runs.id", ondelete="SET NULL"))
    __table_args__ = (
        UniqueConstraint("episode_id", "source_commit"),
        UniqueConstraint("id", "episode_id", name="uq_revisions_id_episode"),
        CheckConstraint("status IN ('pending', 'processing', 'ready', 'failed')", name="status"),
    )


class TranscriptChunk(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "transcript_chunks"
    episode_revision_id: Mapped[UUID] = mapped_column(ForeignKey("app_data.episode_revisions.id", ondelete="RESTRICT"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    speaker: Mapped[str | None] = mapped_column(Text)
    start_seconds: Mapped[int | None] = mapped_column(Integer)
    end_seconds: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    # Variable dimensions until an embedding model is chosen. Retrieval must filter
    # by model/dimensions; a later migration can add a model-specific vector index.
    embedding: Mapped[list[float] | None] = mapped_column(Vector())
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    chunking_version: Mapped[str] = mapped_column(String(100))
    __table_args__ = (
        UniqueConstraint("episode_revision_id", "chunking_version", "chunk_index"),
        CheckConstraint("chunk_index >= 0 AND token_count > 0", name="position_size"),
        CheckConstraint("start_seconds >= 0 AND end_seconds >= start_seconds", name="timestamps"),
        CheckConstraint(
            "(embedding IS NULL AND embedding_model IS NULL AND embedding_dimensions IS NULL) OR "
            "(embedding IS NOT NULL AND embedding_model IS NOT NULL AND embedding_dimensions IS NOT NULL "
            "AND embedding_dimensions > 0 AND vector_dims(embedding) = embedding_dimensions)",
            name="embedding_metadata",
        ),
    )


class MessageSource(IdentityMixin, Base):
    __tablename__ = "message_sources"
    message_id: Mapped[UUID] = mapped_column(ForeignKey("app_data.messages.id", ondelete="CASCADE"))
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey("app_data.transcript_chunks.id", ondelete="RESTRICT"), index=True)
    citation_number: Mapped[int] = mapped_column(Integer)
    quoted_text: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("message_id", "citation_number"),
        UniqueConstraint("message_id", "chunk_id", name="uq_sources_message_chunk"),
        CheckConstraint("citation_number > 0", name="citation"),
    )
