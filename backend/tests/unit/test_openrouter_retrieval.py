import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from unittest.mock import AsyncMock
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
        if str(statement).startswith("SELECT DISTINCT app_data.episodes.guest"):
            return SimpleNamespace(all=lambda: [(name,) for name in getattr(self, "guests", [])])
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
        if response := scope_response(request):
            return response
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


def scope_response(request):
    if request.url.path.endswith("/chat/completions"):
        question = json.loads(json.loads(request.content)["messages"][1]["content"])["question"]
        return httpx.Response(200, json=scope_payload(question))


def scope_payload(question):
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
        "in_scope": True, "search_question": question, "reason": "in_scope"})}}]}


def scope_client():
    return SimpleNamespace(post=AsyncMock(side_effect=lambda path, payload:
        scope_payload(json.loads(payload["messages"][1]["content"])["question"])
        if path == "chat/completions" else {"data": [{"index": 0, "embedding": [1.0] * 1024}]}))


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
    assert '"growth"' in keyword.params.values()


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
        if response := scope_response(request):
            return response
        if failure == "http":
            return httpx.Response(429, text="private payload")
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0] * 1536}]})

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderError):
                await retrieve(database, client, "Growth question", "chunks-v1")
        finally:
            await client.close()
    asyncio.run(check())
    assert database.statements == []


def query_search(question, database, **options):
    client = scope_client()
    return asyncio.run(retrieve(database, client, question, "chunks-v1", **options))


def test_person_scope_applies_to_semantic_keyword_and_neighbor_queries():
    hit = row("April evidence", .1)
    database = SearchDatabase([[hit], [hit], []])
    database.guests = ["April Dunford", "April Dunford 2.0", "Brian Chesky"]
    query_search("April Dunford's competitive alternatives", database, candidate_pool=True)
    assert len(database.statements) == 3
    for statement in database.statements:
        assert_openrouter_filters(statement)
        assert "episodes.guest IN" in str(statement)
        assert "~*" in str(statement)
        assert ["April Dunford", "April Dunford 2.0"] in statement.params.values()
        assert r"\mapril\s+dunford\M" in statement.params.values()
    keyword = database.statements[1]
    assert '"competitive" OR "alternatives"' in keyword.params.values()
    assert '"competitive" "alternatives"' in keyword.params.values()


def test_person_without_hits_does_not_silently_fall_back_to_other_guests():
    database = SearchDatabase([[], []])
    database.guests = ["April Dunford"]
    result = query_search("April Dunford on an unavailable topic", database)
    assert result.passages == []
    assert len(database.statements) == 2


def test_short_keyword_and_number_use_lexical_search():
    database = SearchDatabase([[], []])
    query_search("AI 40", database)
    assert len(database.statements) == 2
    assert '"ai" OR "40"' in database.statements[1].params.values()


def test_quoted_phrase_receives_separate_ranking_bonus():
    database = SearchDatabase([[], []])
    query_search('Explain "competitive alternatives"', database)
    statement = database.statements[1]
    assert '"competitive alternatives"' in statement.params.values()
    assert "CASE WHEN" in str(statement)


def test_comparison_searches_each_person_and_keeps_both_candidates():
    first, second = row("Sean evidence", .1), row("Rahul evidence", .7)
    database = SearchDatabase([[first], [first], [second], [second], []])
    database.guests = ["Sean Ellis", "Rahul Vohra"]
    result = query_search("Compare Sean Ellis and Rahul Vohra on PMF", database, candidate_pool=True)
    assert {p.chunk_id for p in result.passages} == {first[0].id, second[0].id}
    assert len(database.statements) == 5


def test_unknown_person_does_not_invent_an_identity_filter():
    database = SearchDatabase([[], []])
    database.guests = ["April Dunford"]
    query_search("Unknown Person on growth", database)
    assert all("episodes.guest IN" not in str(statement) for statement in database.statements)


@pytest.mark.parametrize("question", ["What is tomorrow's weather in Mumbai?", "What is my database password?", "What did he recommend?"])
def test_out_of_domain_request_never_opens_database_or_calls_api(question):
    database = SimpleNamespace(sessions=lambda: pytest.fail("Database must not be opened"))
    client = SimpleNamespace(post=AsyncMock())
    result = asyncio.run(retrieve(database, client, question, "chunks-v1"))
    assert result.passages == []
    assert result.blocked_reason
    client.post.assert_not_awaited()


def test_misspelled_name_is_corrected_for_embedding_and_filtered_queries():
    database = SearchDatabase([[], []])
    database.guests = ["April Dunford", "April Dunford 2.0", "Brian Chesky"]
    client = scope_client()
    result = asyncio.run(retrieve(database, client, "What does Apryl Dunfrd recommend about positioning?", "chunks-v1"))
    assert "april dunford" in client.post.call_args.args[1]["input"][0]
    assert result.requested_people == ["april dunford"]
    assert all("episodes.guest IN" in str(statement) for statement in database.statements)


def test_excluded_guest_filter_applies_to_keyword_and_semantic_search():
    database = SearchDatabase([[], []])
    database.guests = ["April Dunford", "April Dunford 2.0"]
    result = query_search("Which guests other than April Dunford discuss positioning?", database)
    assert result.requested_people == []
    assert result.excluded_people == ["april dunford"]
    assert all("episodes.guest NOT IN" in str(statement) for statement in database.statements)
    assert all("speaker IS NULL" in str(statement) for statement in database.statements)
    assert all(r"(?m)^\s*april\s+dunford\s+\(\d" in statement.params.values() for statement in database.statements)


def test_unknown_explicit_person_skips_chunk_queries_and_embedding():
    database = SearchDatabase([])
    database.guests = ["April Dunford"]
    client = scope_client()
    result = asyncio.run(retrieve(database, client, "What does Alexandra Exampleton recommend about positioning?", "chunks-v1"))
    assert result.blocked_reason == "unknown_or_ambiguous_person"
    assert database.statements == []
    assert [call.args[0] for call in client.post.await_args_list] == ["chat/completions"]


def test_comparison_in_multi_guest_episode_keeps_episode_scope_for_each_person():
    database = SearchDatabase([[], [], [], []])
    database.guests = ["Jake Knapp + John Zeratsky 2.0"]
    query_search("Compare Jake Knapp and John Zeratsky on design", database)
    assert len(database.statements) == 4
    for statement in database.statements:
        guest_lists = [value for value in statement.params.values() if isinstance(value, list) and (not value or isinstance(value[0], str))]
        assert ["Jake Knapp + John Zeratsky 2.0"] in guest_lists
        assert [] not in guest_lists


def test_default_hybrid_searches_overlap_in_independent_sessions():
    class BarrierDatabase(SearchDatabase):
        def __init__(self):
            super().__init__([[], []])
            self.started = 0
            self.both_started = asyncio.Event()
            self.maximum_sessions = 0

        async def execute(self, statement):
            if not str(statement).startswith("SELECT DISTINCT app_data.episodes.guest"):
                self.started += 1
                self.maximum_sessions = max(self.maximum_sessions, self.active_sessions)
                if self.started == 2:
                    self.both_started.set()
                # Sequential search cannot cross this barrier and will time out.
                await self.both_started.wait()
            return await super().execute(statement)

    async def check():
        database = BarrierDatabase()
        await asyncio.wait_for(retrieve(database, scope_client(), "Growth question", "chunks-v1"), 2)
        assert database.started == 2
        assert database.maximum_sessions == 2
        assert database.active_sessions == 0

    asyncio.run(check())
