import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from app.ingestion.source import ARCHIVE_SHA256
from app.llm.client import OpenRouterClient, ProviderError
from app.rag.openrouter_retrieval import retrieve
from app.rag.retrieval import fuse_rankings, unique_passages


class SearchDatabase:
    def __init__(self, batches):
        self.batches = iter(batches)
        self.statements = []
        self.active_sessions = 0

    @asynccontextmanager
    async def sessions(self):
        self.active_sessions += 1
        try:
            yield SimpleNamespace(execute=self.execute)
        finally:
            self.active_sessions -= 1

    async def execute(self, statement):
        self.statements.append(statement.compile(dialect=postgresql.dialect()))
        rows = next(self.batches)
        return SimpleNamespace(all=lambda: rows)


def row(content, distance, *, revision_id=None, index=1):
    revision_id = revision_id or uuid4()
    chunk = SimpleNamespace(
        id=uuid4(), content=content, episode_revision_id=revision_id, chunk_index=index,
        start_char=0, end_char=len(content), start_seconds=0, end_seconds=10,
    )
    episode = SimpleNamespace(
        id=uuid4(), title="Episode", guest="Guest", youtube_url=None,
        repository_path="episodes/example/transcript.md",
    )
    return chunk, episode, revision_id, distance


def assert_openrouter_filters(statement):
    sql = str(statement)
    params = statement.params
    assert "compatible_embeddings AS MATERIALIZED" in sql
    for column, expected in (
        ("provider", "openrouter"), ("model", "baai/bge-m3"),
        ("dimensions", 1024), ("input_version", "raw-chunk-v1"),
    ):
        matching = [value for key, value in params.items() if key.startswith(column + "_")]
        assert matching and all(value == expected for value in matching)
    assert "openai" not in params.values()
    assert "VECTOR(1536)" not in sql
    assert ARCHIVE_SHA256 in params.values()
    assert "ready" in params.values()
    assert "chunks-v1" in params.values()
    assert "active_revision_id =" in sql


def run_search(database, **options):
    vector = [1.0] * 1024
    requests = []

    def handler(request):
        assert database.active_sessions == 0
        assert str(request.url) == "https://openrouter.ai/api/v1/embeddings"
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload == {
            "model": "baai/bge-m3", "input": ["Growth question"],
            "dimensions": 1024, "encoding_format": "float",
        }
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": vector}]})

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(handler))
        try:
            return await retrieve(database, client, "  Growth question  ", "chunks-v1", **options)
        finally:
            await client.close()

    result = asyncio.run(check())
    assert len(requests) == 1
    assert database.active_sessions == 0
    for statement in database.statements:
        assert_openrouter_filters(statement)
        assert vector in statement.params.values()
    assert result.provider == "openrouter"
    assert result.embedding_model == "baai/bge-m3"
    assert result.question == "Growth question"
    return result


def test_semantic_retrieval_uses_bge_m3_and_preserves_source_metadata():
    first, duplicate, second = row("First", .1), row("First", .2), row("Second", .3)
    database = SearchDatabase([[first, duplicate, second]])
    result = run_search(database, hybrid=False, top_k=2)
    assert [p.chunk_id for p in result.passages] == [first[0].id, second[0].id]
    assert [p.similarity for p in result.passages] == pytest.approx([.9, .7])
    assert result.passages[0].episode_id == first[1].id
    assert result.passages[0].episode_revision_id == first[2]
    assert result.passages[0].archive_sha256 == ARCHIVE_SHA256
    assert result.passages[0].text == first[0].content
    assert len(database.statements) == 1


@pytest.mark.parametrize("concurrent", [False, True])
def test_hybrid_search_reuses_keyword_ranking_and_fusion(concurrent):
    first, shared, lexical_only = row("Semantic", .1), row("Shared", .2), row("Keyword", .8)
    semantic, keywords = [first, shared], [shared, lexical_only]
    database = SearchDatabase([semantic, keywords])
    result = run_search(database, top_k=2, concurrent_search=concurrent)
    expected = unique_passages(fuse_rankings(semantic, keywords, 4))[:2]
    assert [p.chunk_id for p in result.passages] == [r[0].id for r in expected]
    assert len(database.statements) == 2
    keyword = database.statements[1]
    assert "keyword_candidates AS MATERIALIZED" in str(keyword)
    assert "EXISTS (SELECT" in str(keyword)
    assert "websearch_to_tsquery" in str(keyword)
    assert "growth OR question" in keyword.params.values()


@pytest.mark.parametrize("rank_fusion", [False, True])
def test_candidate_pool_neighbors_keep_openrouter_filters(rank_fusion):
    revision_id = uuid4()
    first = row("First", .1, revision_id=revision_id, index=0)
    second = row("Second", .3)
    neighbor = row("Neighbor", .2, revision_id=revision_id, index=1)
    database = SearchDatabase([[first], [second], [neighbor, first]])
    result = run_search(database, candidate_pool=True, rank_fusion=rank_fusion)
    assert {p.chunk_id for p in result.passages} == {first[0].id, second[0].id, neighbor[0].id}
    assert len(result.passages) == 3
    assert len(database.statements) == 3
    neighbors = database.statements[2]
    assert "chunk_index =" in str(neighbors)
    assert revision_id in neighbors.params.values()
    assert -1 not in neighbors.params.values()
    if rank_fusion:
        expected = fuse_rankings([first, neighbor], [second], 50)
        assert [p.chunk_id for p in result.passages] == [r[0].id for r in expected]


def test_no_matching_embeddings_returns_empty_result():
    database = SearchDatabase([[], []])
    assert run_search(database, candidate_pool=True).passages == []
    assert len(database.statements) == 2


@pytest.mark.parametrize("question,top_k", [(" ", 5), ("x" * 12001, 5), ("Question", 0), ("Question", 21)])
def test_invalid_input_skips_embedding_and_search(question, top_k):
    database = SearchDatabase([])

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(
            lambda request: pytest.fail("Unexpected embedding request")))
        try:
            with pytest.raises(ValueError):
                await retrieve(database, client, question, "chunks-v1", top_k=top_k)
        finally:
            await client.close()
    asyncio.run(check())
    assert database.statements == []


@pytest.mark.parametrize("failure", ["http", "bad_dimensions"])
def test_embedding_failure_never_searches_database(failure):
    database = SearchDatabase([])

    def handler(request):
        if failure == "http":
            return httpx.Response(429, text="private payload")
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0] * 1536}]})

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderError):
                await retrieve(database, client, "Question", "chunks-v1")
        finally:
            await client.close()
    asyncio.run(check())
    assert database.statements == []
