import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import tiktoken

from app.llm.client import ProviderError
from app.rag.context import build_context
from app.rag.rerank import rerank
from app.rag.service import RAGService
from app.rag.retrieval import neighbor_positions
from app.schemas.retrieval import RetrievalResult
from test_rag_refinement import passage, answer


def response(order):
    return {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps({"passage_ids": order})}]}]}


@pytest.mark.parametrize("order", [[1, 0], [1, 1], [9, 0], [1], []])
def test_reranking_preserves_exact_evidence_and_rejects_invalid_ids(order):
    candidates = [passage("Background"), passage("Specific answer")]
    client = SimpleNamespace(post=AsyncMock(return_value=response(order)))
    ranked = asyncio.run(rerank(client, "Specific question", candidates))
    assert ranked == (list(reversed(candidates)) if order == [1, 0] else candidates)
    assert all(any(p is original for original in candidates) for p in ranked)


@pytest.mark.parametrize("error", [ProviderError("Unavailable"), TimeoutError()])
def test_reranking_failure_keeps_candidates(error):
    candidates = [passage("First"), passage("Second")]
    client = SimpleNamespace(post=AsyncMock(side_effect=error))
    assert asyncio.run(rerank(client, "Question", candidates)) == candidates


@pytest.mark.parametrize("payload", [None, {"status": "incomplete"},
    {"status": "completed", "output": [None]},
    {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]}])
def test_malformed_or_refused_ranking_keeps_evidence(payload):
    candidates = [passage("First"), passage("Second")]
    client = SimpleNamespace(post=AsyncMock(return_value=payload))
    assert asyncio.run(rerank(client, "Question", candidates)) == candidates


def test_service_reranks_before_truncating():
    async def check():
        candidates = [passage(str(i)) for i in range(20)]
        result = RetrievalResult(question="Question", provider="openai", embedding_model="test", passages=candidates)
        client = SimpleNamespace(post=AsyncMock(return_value=response(list(reversed(range(20))))))
        with patch("app.rag.service.retrieve", AsyncMock(return_value=result)) as search:
            found = await RAGService(None, client).retrieve("Question", top_k=5)
        assert found.passages == list(reversed(candidates))[:5]
        assert search.call_args.kwargs == {"hybrid": True, "candidate_pool": True}
    asyncio.run(check())


def test_context_budget_keeps_priority_and_skips_duplicates():
    first = passage("important " * 300)
    duplicate = first.model_copy(update={"chunk_id": passage("x").chunk_id})
    second = passage("detail " * 300)
    third = passage("other " * 300)
    context = build_context([first, duplicate, second, third], token_budget=650)
    assert list(context.values()) == [first, second]
    encoding = tiktoken.get_encoding("cl100k_base")
    assert sum(len(encoding.encode(p.text)) for p in context.values()) <= 650


def test_context_experiment_does_not_change_default():
    async def check():
        service = RAGService(None, None)
        service.retrieve = AsyncMock(return_value=SimpleNamespace(passages=[passage("Evidence")]))
        service.generator = SimpleNamespace(model="gpt-6-luna", answer=AsyncMock(return_value=answer(True)))
        with patch("app.rag.service.build_context", wraps=build_context) as pack:
            await service.ask("Question")
            assert pack.call_args.kwargs["token_budget"] == 4000
            await service.ask("Question", context_budget=6000)
            assert pack.call_args.kwargs["token_budget"] == 6000
    asyncio.run(check())


def test_neighbor_candidates_preserve_revision_and_boundaries():
    rows = [(SimpleNamespace(episode_revision_id="first", chunk_index=0),),
            (SimpleNamespace(episode_revision_id="first", chunk_index=2),),
            (SimpleNamespace(episode_revision_id="second", chunk_index=2),)]
    assert neighbor_positions(rows) == [("first", 1), ("first", 3), ("second", 1), ("second", 3)]


@pytest.mark.parametrize("invalid", [[1], [1, 1], [9, 0], [True, 0], ["1", 0], [1.0, 0]])
def test_invalid_ranking_is_retried_without_losing_evidence(invalid):
    candidates = [passage("First"), passage("Second")]
    client = SimpleNamespace(post=AsyncMock(side_effect=[response(invalid), response([1, 0])]))
    diagnostics = {}
    ranked = asyncio.run(rerank(client, "Question", candidates, diagnostics=diagnostics))
    assert ranked[0] is candidates[1] and ranked[1] is candidates[0]
    assert client.post.await_count == 2
    assert [a["valid"] for a in diagnostics["attempts"]] == [False, True]
    assert diagnostics["fallback"] is False


def test_full_candidate_schema_and_order():
    candidates = [passage(str(i)) for i in range(50)]
    client = SimpleNamespace(post=AsyncMock(return_value=response(list(reversed(range(50))))))
    ranked = asyncio.run(rerank(client, "Question", candidates))
    schema = client.post.call_args.args[1]["text"]["format"]["schema"]["properties"]["passage_ids"]
    assert schema["minItems"] == schema["maxItems"] == 50
    assert schema["items"]["enum"] == list(range(50))
    assert all(actual is expected for actual, expected in zip(ranked, reversed(candidates)))
    assert client.post.await_count == 1


def test_exhausted_retry_restores_original_order():
    candidates = [passage("First"), passage("Second")]
    client = SimpleNamespace(post=AsyncMock(return_value=response([1])))
    diagnostics = {}
    assert asyncio.run(rerank(client, "Question", candidates, diagnostics=diagnostics)) is candidates
    assert client.post.await_count == 2
    assert diagnostics["fallback"] is True


def test_incomplete_retry_increases_output_allowance():
    client = SimpleNamespace(post=AsyncMock(side_effect=[{"status": "incomplete"}, response([1, 0])]))
    asyncio.run(rerank(client, "Question", [passage("First"), passage("Second")], initial_output_tokens=1200))
    assert [call.args[1]["max_output_tokens"] for call in client.post.call_args_list] == [1200, 2400]


def test_configured_larger_initial_allowance_is_used():
    client = SimpleNamespace(post=AsyncMock(return_value=response([1, 0])))
    asyncio.run(rerank(client, "Question", [passage("First"), passage("Second")], initial_output_tokens=2400))
    assert client.post.call_args.args[1]["max_output_tokens"] == 2400


def test_external_cancellation_propagates():
    client = SimpleNamespace(post=AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(rerank(client, "Question", [passage("First"), passage("Second")]))
    assert client.post.await_count == 1
