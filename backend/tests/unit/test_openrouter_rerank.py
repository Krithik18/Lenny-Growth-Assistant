import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.llm.client import OpenRouterClient, ProviderError
from app.rag.openrouter_rerank import rerank, ranking_document
from test_rag_refinement import passage


def response(order):
    return {"results": [
        {"index": index, "relevance_score": .9 - rank * .05,
         "document": {"text": "Do not substitute provider text"}}
        for rank, index in enumerate(order)
    ]}


def test_rerank_uses_openrouter_and_preserves_original_passages():
    candidates = [passage("Background"), passage("Answer"), passage("More detail")]
    before = [p.model_dump() for p in candidates]
    diagnostics = {}

    def handler(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/rerank"
        assert request.headers["Authorization"] == "Bearer fake"
        assert json.loads(request.content) == {
            "model": "voyageai/rerank-2.5-lite", "query": "User question",
            "documents": [ranking_document(p) for p in candidates], "top_n": 3,
        }
        return httpx.Response(200, json=response([1, 2, 0]))

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(handler))
        try:
            ranked = await rerank(client, "User question", candidates, diagnostics=diagnostics)
            assert all(ranked[i] is candidates[j] for i, j in enumerate([1, 2, 0]))
            assert [p.model_dump() for p in candidates] == before
        finally:
            await client.close()

    asyncio.run(check())
    assert diagnostics["fallback"] is False
    assert diagnostics["candidate_count"] == 3
    assert len(diagnostics["attempts"]) == 1
    assert diagnostics["attempts"][0]["order"] == [1, 2, 0]


@pytest.mark.parametrize("count", [0, 1])
def test_empty_or_single_passage_skips_request(count):
    candidates = [passage("Only chunk")] * count
    client = SimpleNamespace(post=AsyncMock())
    assert asyncio.run(rerank(client, "Question", candidates)) is candidates
    client.post.assert_not_awaited()


@pytest.mark.parametrize("payload", [
    None, {}, {"results": None}, {"results": {}}, {"results": [None]},
    {"results": [{}]}, response([]), response([0]), response([0, 0]),
    response([0, 2]), response([-1, 0]), response([0, 1, 2]),
    response([True, 0]), response([1.0, 0]), response(["1", 0]),
])
def test_invalid_ranking_retries_then_preserves_all_candidates(payload):
    candidates = [passage("First"), passage("Second")]
    client = SimpleNamespace(post=AsyncMock(return_value=payload))
    diagnostics = {}
    assert asyncio.run(rerank(client, "Question", candidates, diagnostics=diagnostics)) is candidates
    assert client.post.await_count == 2
    assert diagnostics["fallback"] is True
    assert all(record["valid"] is False for record in diagnostics["attempts"])


@pytest.mark.parametrize("error", [ProviderError("private payload"), TimeoutError("private payload")])
def test_provider_failure_falls_back_without_logging_payload(error, caplog):
    candidates = [passage("First"), passage("Second")]
    client = SimpleNamespace(post=AsyncMock(side_effect=error))
    diagnostics = {}
    assert asyncio.run(rerank(client, "Question", candidates, diagnostics=diagnostics)) is candidates
    assert client.post.await_count == 2
    assert diagnostics["fallback"] is True
    assert "private payload" not in caplog.text
    assert "private payload" not in str(diagnostics)


@pytest.mark.parametrize("first", [ProviderError("Unavailable"), response([0, 0])])
def test_second_attempt_can_recover(first):
    candidates = [passage("First"), passage("Second")]
    client = SimpleNamespace(post=AsyncMock(side_effect=[first, response([1, 0])]))
    diagnostics = {}
    ranked = asyncio.run(rerank(client, "Question", candidates, diagnostics=diagnostics))
    assert ranked == candidates[::-1]
    assert client.post.await_count == 2
    assert diagnostics["fallback"] is False
    assert [record["valid"] for record in diagnostics["attempts"]] == [False, True]


def test_ranking_scores_reject_only_low_relevance_and_preserve_text():
    relevant, weak = passage("Direct answer"), passage("Unrelated material")
    before = relevant.model_dump()
    client = SimpleNamespace(post=AsyncMock(return_value={"results": [
        {"index": 0, "relevance_score": .8}, {"index": 1, "relevance_score": .05}]}))
    diagnostics = {}
    ranked = asyncio.run(rerank(client, "Growth question", [relevant, weak], diagnostics=diagnostics))
    assert ranked == [relevant]
    assert ranked[0].model_dump() == before
    assert diagnostics["low_relevance_rejected"] == 1


def test_all_low_scores_return_no_evidence():
    candidates = [passage("Unrelated one"), passage("Unrelated two")]
    client = SimpleNamespace(post=AsyncMock(return_value={"results": [
        {"index": 0, "relevance_score": .08}, {"index": 1, "relevance_score": .05}]}))
    assert asyncio.run(rerank(client, "Growth question", candidates)) == []


def test_mixed_sponsor_and_answer_chunk_is_retained_with_soft_penalty():
    ad = passage("Get started for free at wix.com. Here is relevant onboarding advice.")
    answer = passage("Here is the direct onboarding answer.")
    client = SimpleNamespace(post=AsyncMock(return_value={"results": [
        {"index": 0, "relevance_score": .8}, {"index": 1, "relevance_score": .79}]}))
    ranked = asyncio.run(rerank(client, "Onboarding growth", [ad, answer]))
    assert ranked[0] is answer
    assert ad in ranked
