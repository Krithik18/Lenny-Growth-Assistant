"""Retrieval output contains evidence only, never a generated answer."""

from uuid import UUID
from pydantic import BaseModel


class RetrievedPassage(BaseModel):
    chunk_id: UUID
    episode_id: UUID
    episode_revision_id: UUID
    title: str
    guest: str | None
    source_url: str | None
    archive_member: str
    archive_sha256: str
    text: str
    start_char: int | None
    end_char: int | None
    start_seconds: int | None
    end_seconds: int | None
    similarity: float


class RetrievalResult(BaseModel):
    question: str
    provider: str
    embedding_model: str
    passages: list[RetrievedPassage]
