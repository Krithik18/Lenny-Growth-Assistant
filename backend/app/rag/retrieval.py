"""Indexed cosine retrieval restricted to the approved archive and embedding space."""

import asyncio
import re
from sqlalchemy import select, func, literal_column, text, and_, or_

from app.db.models import ChunkEmbedding, Episode, EpisodeRevision, TranscriptChunk
from app.db.session import Database
from app.db.search_indexes import openai_search_vector
from app.ingestion.source import ARCHIVE_SHA256
from app.rag.embeddings import EmbeddingProvider, validate_vectors
from app.schemas.retrieval import RetrievedPassage, RetrievalResult


async def retrieve(database: Database, provider: EmbeddingProvider, question: str,
                   chunking_version: str, top_k: int = 5, hybrid: bool = False,
                   candidate_pool: bool = False, concurrent_search: bool = False,
                   rank_fusion: bool = False) -> RetrievalResult:
    question = question.strip()
    if not question or len(question) > 12000 or not 1 <= top_k <= 20:
        raise ValueError("Provide a nonempty question up to 12000 characters and top_k from 1 to 20.")
    pool_size = 20 if candidate_pool else top_k
    spec = provider.spec
    vector = await provider.embed_query(question)
    validate_vectors([vector], 1, spec)
    # The primary space uses the same safe CASE expression as its HNSW index.
    indexed = (spec.provider, spec.model, spec.dimensions, spec.input_version) == (
        "openai", "text-embedding-3-small", 1536, "raw-chunk-v1")
    compatible = select(ChunkEmbedding.chunk_id, ChunkEmbedding.embedding).where(
        ChunkEmbedding.provider == spec.provider,
        ChunkEmbedding.model == spec.model,
        ChunkEmbedding.dimensions == spec.dimensions,
        ChunkEmbedding.input_version == spec.input_version,
    ).cte("compatible_embeddings").prefix_with("MATERIALIZED", dialect="postgresql") if not indexed else ChunkEmbedding.__table__
    search_vector = openai_search_vector(compatible) if indexed else compatible.c.embedding
    distance = search_vector.cosine_distance(vector)
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
        .order_by(distance).limit(pool_size * 3)
    )
    if indexed:
        statement = statement.where(search_vector.is_not(None))
    lexical = None
    if hybrid:
            # Bound and parameterize query terms. OR finds specific words even when
            # the missing-topic sentence contains terms absent from the transcript.
            terms = list(dict.fromkeys(re.findall(r"[a-zA-Z]{3,}", question.lower())))[:32]
            if terms:
                query = func.websearch_to_tsquery(literal_column("'english'::regconfig"), " OR ".join(terms))
                document = func.to_tsvector(literal_column("'english'::regconfig"), TranscriptChunk.content)
                # Rank text before loading vectors. Reusing the semantic query
                # directly makes its CASE/vector compatibility check read large
                # embeddings for every keyword match rather than the bounded winners.
                has_embedding = select(ChunkEmbedding.chunk_id).where(
                    ChunkEmbedding.chunk_id == TranscriptChunk.id,
                    ChunkEmbedding.provider == spec.provider,
                    ChunkEmbedding.model == spec.model,
                    ChunkEmbedding.dimensions == spec.dimensions,
                    ChunkEmbedding.input_version == spec.input_version,
                ).exists()
                keyword_candidates = (
                    select(TranscriptChunk.id.label("chunk_id"), func.ts_rank_cd(document, query).label("rank"))
                    .join(EpisodeRevision, EpisodeRevision.id == TranscriptChunk.episode_revision_id)
                    .join(Episode, Episode.active_revision_id == EpisodeRevision.id)
                    .where(EpisodeRevision.source_archive_sha256 == ARCHIVE_SHA256,
                           EpisodeRevision.status == "ready",
                           TranscriptChunk.chunking_version == chunking_version,
                           document.op("@@")(query), has_embedding)
                    .order_by(func.ts_rank_cd(document, query).desc(), TranscriptChunk.id)
                    .limit(pool_size * 3)
                    .cte("keyword_candidates").prefix_with("MATERIALIZED", dialect="postgresql")
                )
                lexical = statement.order_by(None).join(
                    keyword_candidates, keyword_candidates.c.chunk_id == TranscriptChunk.id
                ).order_by(keyword_candidates.c.rank.desc(), TranscriptChunk.id).limit(pool_size * 3)
    semantic, keywords = await search_rows(database, statement, lexical, indexed, concurrent_search)
    semantic_rows = unique_passages(semantic)[:pool_size]
    keyword_rows = unique_passages(keywords)[:pool_size]
    rows = (unique_passages(semantic_rows + keyword_rows)[:40] if candidate_pool
            else unique_passages(fuse_rankings(semantic_rows, keyword_rows, top_k * 2))[:top_k])
    adjacent = []
    if candidate_pool and rows:
            # A recommendation often continues just beyond a chunk boundary.
            # Fetch only immediate neighbors of a few strong hits, under the same
            # archive/revision/chunking/embedding filters, for the reranker to judge.
            seeds = unique_passages(semantic_rows[:3] + keyword_rows[:2])
            pairs = neighbor_positions(seeds)
            neighbors = statement.order_by(None).where(or_(*[
                and_(TranscriptChunk.episode_revision_id == revision_id,
                     TranscriptChunk.chunk_index == index)
                for revision_id, index in pairs
            ])).order_by(distance, TranscriptChunk.id).limit(10)
            async with database.sessions() as session:
                adjacent = (await session.execute(neighbors)).all()
            rows = unique_passages(rows + adjacent)[:50]
    if rank_fusion:
        # Without an LLM reranker, use RRF to give both search methods a
        # meaningful place in the final list. Neighbor candidates retain
        # their measured cosine distances in the semantic ranking.
        semantic_with_neighbors = unique_passages(sorted(semantic_rows + adjacent, key=lambda row: float(row[3])))
        rows = unique_passages(fuse_rankings(semantic_with_neighbors, keyword_rows, 50))
    passages = [RetrievedPassage(
            chunk_id=chunk.id, episode_id=episode.id, episode_revision_id=revision_id,
            title=episode.title, guest=episode.guest, source_url=episode.youtube_url,
            archive_member=episode.repository_path, archive_sha256=ARCHIVE_SHA256,
            text=chunk.content, start_char=chunk.start_char, end_char=chunk.end_char,
            start_seconds=chunk.start_seconds, end_seconds=chunk.end_seconds,
            similarity=1.0 - float(distance_value),
        ) for chunk, episode, revision_id, distance_value in rows]
    return RetrievalResult(question=question, provider=spec.provider, embedding_model=spec.model, passages=passages)


async def search_rows(database, semantic, lexical, indexed, concurrent):
    """Concurrent SQL requires separate sessions/connections, never one shared session."""
    async def execute(statement, vector_search=False):
        async with database.sessions() as session:
            if indexed and vector_search:
                await session.execute(text("SET LOCAL hnsw.ef_search = 200"))
            return (await session.execute(statement)).all()

    if concurrent and lexical is not None:
        # gather(return_exceptions=True) lets both sessions close cleanly even
        # when one search fails, then re-raises the original database exception.
        results = await asyncio.gather(execute(semantic, True), execute(lexical), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return results
    semantic_rows = await execute(semantic, True)
    return semantic_rows, await execute(lexical) if lexical is not None else []


def fuse_rankings(semantic, lexical, limit):
    """Reciprocal-rank fusion avoids comparing cosine and text-rank score scales."""
    scores, candidates = {}, {}
    for ranking in (semantic, lexical):
        for rank, row in enumerate(ranking, 1):
            key = row[0].id
            candidates[key] = row
            scores[key] = scores.get(key, 0) + 1 / (60 + rank)
    return [candidates[key] for key in sorted(scores, key=lambda key: (-scores[key], str(key)))[:limit]]


def unique_passages(rows):
    """Identical text in separate ZIP members should consume one result slot."""
    seen, unique = set(), []
    for row in rows:
        key = row[0].content
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def neighbor_positions(rows):
    """Never cross revision boundaries or request a negative chunk index."""
    return list(dict.fromkeys(
        (row[0].episode_revision_id, index)
        for row in rows for index in (row[0].chunk_index - 1, row[0].chunk_index + 1)
        if index >= 0
    ))
