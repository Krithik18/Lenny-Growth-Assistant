"""Indexed cosine retrieval restricted to the approved archive and embedding space."""

import asyncio
import re
from sqlalchemy import select, func, literal_column, text, and_, or_, case

from app.db.models import ChunkEmbedding, Episode, EpisodeRevision, TranscriptChunk
from app.db.session import Database
from app.db.search_indexes import openai_search_vector
from app.ingestion.source import ARCHIVE_SHA256
from app.rag.embeddings import EmbeddingProvider, validate_vectors
from app.schemas.retrieval import RetrievedPassage, RetrievalResult
from app.rag.query_intent import plan_query, lexical_queries, name_catalog


async def retrieve(database: Database, provider: EmbeddingProvider, question: str,
                   chunking_version: str, top_k: int = 5, hybrid: bool = False,
                   candidate_pool: bool = False, concurrent_search: bool = False,
                   rank_fusion: bool = False, query_aware: bool = False, diagnostics=None,
                   domain_checked: bool = False) -> RetrievalResult:
    question = question.strip()
    if not question or len(question) > 12000 or not 1 <= top_k <= 20:
        raise ValueError("Provide a nonempty question up to 12000 characters and top_k from 1 to 20.")
    pool_size = 20 if candidate_pool else top_k
    spec = provider.spec
    intent = None
    if query_aware:
        async with database.sessions() as session:
            catalog = (await session.execute(select(Episode.guest).distinct()
                .join(EpisodeRevision, Episode.active_revision_id == EpisodeRevision.id)
                .where(EpisodeRevision.source_archive_sha256 == ARCHIVE_SHA256,
                       EpisodeRevision.status == "ready"))).all()
        intent = plan_query(question, [row[0] for row in catalog if row[0]], domain_checked=domain_checked)
        if diagnostics is not None:
            diagnostics.update(search_question=intent.search_question, requested_people=list(intent.people),
                excluded_people=list(intent.excluded_people), blocked_reason=intent.blocked_reason)
        if intent.blocked_reason:
            return RetrievalResult(question=question, provider=spec.provider, embedding_model=spec.model, passages=[])
    vector = await provider.embed_query(intent.search_question if intent else question)
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
    if intent and intent.excluded_guests:
        excluded_scope = and_(Episode.guest.not_in(intent.excluded_guests),
            or_(TranscriptChunk.speaker.is_(None), func.lower(TranscriptChunk.speaker).not_in(intent.excluded_people)),
            *[~TranscriptChunk.content.op("~*")(r"(?m)^\s*" + r"\s+".join(re.escape(w) for w in person.split()) + r"\s+\(\d")
              for person in intent.excluded_people])
        statement = statement.where(excluded_scope)
    else:
        excluded_scope = None
    identity_scope = None
    if intent and intent.people:
        identity_scope = or_(Episode.guest.in_(intent.guests), *[
            TranscriptChunk.content.op("~*")(r"\m" + r"\s+".join(re.escape(word) for word in person.split()) + r"\M")
            for person in intent.people
        ])
        statement = statement.where(identity_scope)
    lexical = None
    if hybrid:
            # Bound and parameterize query terms. OR finds specific words even when
            # the missing-topic sentence contains terms absent from the transcript.
            terms = list(intent.terms) if intent and intent.terms else list(dict.fromkeys(re.findall(r"[a-zA-Z]{3,}", question.lower())))[:32]
            if terms:
                query = func.websearch_to_tsquery(literal_column("'english'::regconfig"), " OR ".join(terms))
                document = func.to_tsvector(literal_column("'english'::regconfig"), TranscriptChunk.content)
                rank = func.ts_rank_cd(document, query)
                if intent:
                    broad, focused, phrases = lexical_queries(intent)
                    # With no topic terms, retain name retrieval rather than an empty tsquery.
                    if broad:
                        query = func.websearch_to_tsquery(literal_column("'english'::regconfig"), broad)
                        focused_query = func.websearch_to_tsquery(literal_column("'english'::regconfig"), focused)
                        rank = func.ts_rank_cd(document, query) + case((document.op("@@")(focused_query), 1.0), else_=0.0)
                        if phrases:
                            phrase_query = func.websearch_to_tsquery(literal_column("'english'::regconfig"), phrases)
                            rank += case((document.op("@@")(phrase_query), 2.0), else_=0.0)
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
                    select(TranscriptChunk.id.label("chunk_id"), rank.label("rank"))
                    .join(EpisodeRevision, EpisodeRevision.id == TranscriptChunk.episode_revision_id)
                    .join(Episode, Episode.active_revision_id == EpisodeRevision.id)
                    .where(EpisodeRevision.source_archive_sha256 == ARCHIVE_SHA256,
                           EpisodeRevision.status == "ready",
                           TranscriptChunk.chunking_version == chunking_version,
                           document.op("@@")(query), has_embedding)
                    .where(identity_scope if identity_scope is not None else True)
                    .where(excluded_scope if excluded_scope is not None else True)
                    .order_by(rank.desc(), TranscriptChunk.id)
                    .limit(pool_size * 3)
                    .cte("keyword_candidates").prefix_with("MATERIALIZED", dialect="postgresql")
                )
                lexical = statement.order_by(None).join(
                    keyword_candidates, keyword_candidates.c.chunk_id == TranscriptChunk.id
                ).order_by(keyword_candidates.c.rank.desc(), TranscriptChunk.id).limit(pool_size * 3)
    if intent and 1 < len(intent.people) <= 4:
        # Give each explicitly requested person a candidate pool, so a prolific
        # guest cannot consume the entire comparison before reranking.
        groups = []
        for person in intent.people:
            scope = or_(Episode.guest.in_([g for g in intent.guests if person in name_catalog([g])]),
                        TranscriptChunk.content.op("~*")(r"\m" + r"\s+".join(re.escape(w) for w in person.split()) + r"\M"))
            groups.append(await search_rows(database, statement.where(scope),
                lexical.where(scope) if lexical is not None else None, indexed, concurrent_search))
        semantic, keywords = [
            [group[kind][rank] for rank in range(pool_size * 3) for group in groups if rank < len(group[kind])]
            for kind in (0, 1)
        ]
    else:
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
            seeds = unique_passages(semantic_rows[:8] + keyword_rows[:4]) if query_aware else unique_passages(semantic_rows[:3] + keyword_rows[:2])
            pairs = neighbor_positions(seeds)
            neighbors = statement.order_by(None).where(or_(*[
                and_(TranscriptChunk.episode_revision_id == revision_id,
                     TranscriptChunk.chunk_index == index)
                for revision_id, index in pairs
            ])).order_by(distance, TranscriptChunk.id).limit(24 if query_aware else 10)
            async with database.sessions() as session:
                adjacent = (await session.execute(neighbors)).all()
            rows = unique_passages(rows + adjacent)[:80 if query_aware else 50]
    if rank_fusion or query_aware:
        # Without an LLM reranker, use RRF to give both search methods a
        # meaningful place in the final list. Neighbor candidates retain
        # their measured cosine distances in the semantic ranking.
        semantic_with_neighbors = unique_passages(sorted(semantic_rows + adjacent, key=lambda row: float(row[3])))
        rows = unique_passages(fuse_rankings(semantic_with_neighbors, keyword_rows, (80 if query_aware else 50) if candidate_pool else top_k))
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
