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
            assert pack.call_args.kwargs["token_budget"] == 2000
            await service.ask("Question", context_budget=4000)
            assert pack.call_args.kwargs["token_budget"] == 4000
    asyncio.run(check())


def test_neighbor_candidates_preserve_revision_and_boundaries():
    rows = [(SimpleNamespace(episode_revision_id="first", chunk_index=0),),
            (SimpleNamespace(episode_revision_id="first", chunk_index=2),),
            (SimpleNamespace(episode_revision_id="second", chunk_index=2),)]
    assert neighbor_positions(rows) == [("first", 1), ("first", 3), ("second", 1), ("second", 3)]
