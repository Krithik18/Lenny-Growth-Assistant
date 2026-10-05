"""Exact cosine retrieval restricted to the approved archive and embedding configuration."""

from sqlalchemy import select

from app.db.models import ChunkEmbedding, Episode, EpisodeRevision, TranscriptChunk
from app.db.session import Database
from app.ingestion.source import ARCHIVE_SHA256
from app.rag.embeddings import EmbeddingProvider, validate_vectors
from app.schemas.retrieval import RetrievedPassage, RetrievalResult


async def retrieve(database: Database, provider: EmbeddingProvider, question: str,
                   chunking_version: str, top_k: int = 5) -> RetrievalResult:
    question = question.strip()
    if not question or len(question) > 12000 or not 1 <= top_k <= 20:
        raise ValueError("Provide a nonempty question up to 12000 characters and top_k from 1 to 20.")
    spec = provider.spec
    vector = await provider.embed_query(question)
    validate_vectors([vector], 1, spec)
    # MATERIALIZED keeps incompatible dimensions outside the distance operation,
    # independent of query-planner expression evaluation order.
    compatible = select(ChunkEmbedding.chunk_id, ChunkEmbedding.embedding).where(
        ChunkEmbedding.provider == spec.provider,
        ChunkEmbedding.model == spec.model,
        ChunkEmbedding.dimensions == spec.dimensions,
        ChunkEmbedding.input_version == spec.input_version,
    ).cte("compatible_embeddings").prefix_with("MATERIALIZED", dialect="postgresql")
    distance = compatible.c.embedding.cosine_distance(vector)
    statement = (
        select(TranscriptChunk, Episode, EpisodeRevision.id.label("revision_id"), distance.label("distance"))
        .select_from(TranscriptChunk)
        .join(compatible, compatible.c.chunk_id == TranscriptChunk.id)
        .join(EpisodeRevision, EpisodeRevision.id == TranscriptChunk.episode_revision_id)
        .join(Episode, Episode.active_revision_id == EpisodeRevision.id)
        .where(
            EpisodeRevision.source_archive_sha256 == ARCHIVE_SHA256,
            EpisodeRevision.status == "ready",
            TranscriptChunk.chunking_version == chunking_version,
        )
        .order_by(distance, TranscriptChunk.id).limit(top_k)
    )
    async with database.sessions() as session:
        rows = (await session.execute(statement)).all()
        passages = [RetrievedPassage(
            chunk_id=chunk.id, episode_id=episode.id, episode_revision_id=revision_id,
            title=episode.title, guest=episode.guest, source_url=episode.youtube_url,
            archive_member=episode.repository_path, archive_sha256=ARCHIVE_SHA256,
            text=chunk.content, start_char=chunk.start_char, end_char=chunk.end_char,
            start_seconds=chunk.start_seconds, end_seconds=chunk.end_seconds,
            similarity=1.0 - float(distance_value),
        ) for chunk, episode, revision_id, distance_value in rows]
    return RetrievalResult(question=question, provider=spec.provider, embedding_model=spec.model, passages=passages)
