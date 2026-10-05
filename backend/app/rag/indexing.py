"""Resumable embedding batches. Provider API calls happen outside DB transactions."""

from uuid import uuid4

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import ChunkEmbedding, Episode, EpisodeRevision, TranscriptChunk
from app.db.session import Database
from app.ingestion.source import ARCHIVE_SHA256
from app.rag.embeddings import EmbeddingProvider, validate_vectors


async def embed_pending_chunks(database: Database, provider: EmbeddingProvider, chunking_version: str, batch_size: int = 32) -> int:
    if not 1 <= batch_size <= 128:
        raise ValueError("batch_size must be between 1 and 128")
    spec = provider.spec
    completed = 0
    while True:
        already_embedded = exists(select(ChunkEmbedding.id).where(
            ChunkEmbedding.chunk_id == TranscriptChunk.id,
            ChunkEmbedding.provider == spec.provider,
            ChunkEmbedding.model == spec.model,
            ChunkEmbedding.dimensions == spec.dimensions,
            ChunkEmbedding.input_version == spec.input_version,
        ))
        statement = (
            select(TranscriptChunk.id, TranscriptChunk.content)
            .join(EpisodeRevision, EpisodeRevision.id == TranscriptChunk.episode_revision_id)
            .join(Episode, Episode.active_revision_id == EpisodeRevision.id)
            .where(
                EpisodeRevision.source_archive_sha256 == ARCHIVE_SHA256,
                EpisodeRevision.status == "ready",
                TranscriptChunk.chunking_version == chunking_version,
                ~already_embedded,
            )
            .order_by(TranscriptChunk.id).limit(batch_size)
        )
        async with database.sessions() as session:
            batch = (await session.execute(statement)).all()
        if not batch:
            return completed
        vectors = await provider.embed_documents([row.content for row in batch])
        validate_vectors(vectors, len(batch), spec)
        async with database.sessions.begin() as session:
            for row, vector in zip(batch, vectors, strict=True):
                await session.execute(insert(ChunkEmbedding).values(
                    id=uuid4(), chunk_id=row.id, provider=spec.provider,
                    model=spec.model, dimensions=spec.dimensions,
                    input_version=spec.input_version, embedding=vector,
                ).on_conflict_do_nothing(constraint="uq_chunk_embeddings_config"))
        completed += len(batch)
