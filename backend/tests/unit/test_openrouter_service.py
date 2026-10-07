import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.ingestion.chunker import TranscriptChunker
from app.llm.client import OpenRouterClient, ProviderError
from app.llm.openrouter_provider import OpenRouterAnswerProvider
from app.rag.context import build_context
from app.rag.openrouter_embeddings import OpenRouterEmbeddings
from app.rag.openrouter_service import OpenRouterRAGService
from app.schemas.retrieval import RetrievalResult
from test_openrouter_retrieval import SearchDatabase, row, scope_response
from test_rag_refinement import answer, passage


def retrieval(passages):
    return RetrievalResult(question="Question", provider="openrouter", embedding_model="baai/bge-m3", passages=passages)


def test_openrouter_service_defaults_to_concurrent_search():
    assert OpenRouterRAGService(None, None).concurrent_search is True


@pytest.mark.parametrize("reranking,concurrent", [(True, False), (True, True), (False, False)])
def test_retrieve_uses_openrouter_candidates_and_ranks_before_truncation(reranking, concurrent):
    candidates = [passage(str(i)) for i in range(25)]
    service = OpenRouterRAGService(None, None, reranking=reranking, concurrent_search=concurrent)
    assert isinstance(service.embeddings, OpenRouterEmbeddings)
    assert isinstance(service.generator, OpenRouterAnswerProvider)
    with patch("app.rag.openrouter_service.retrieve", AsyncMock(return_value=retrieval(candidates))) as search, \
         patch("app.rag.openrouter_service.rerank", AsyncMock(return_value=candidates[::-1])) as rank:
        result = asyncio.run(service.retrieve("Question", top_k=3, hybrid=False))
    expected_options = {"hybrid": False, "candidate_pool": True, "concurrent_search": concurrent}
    if not reranking:
        expected_options["rank_fusion"] = True
    search.assert_awaited_once_with(None, None, "Question", TranscriptChunker().version, 20, **expected_options)
    if reranking:
        rank.assert_awaited_once_with(None, "Question", candidates, diagnostics={})
    else:
        rank.assert_not_awaited()
    assert result.passages == (candidates[::-1] if reranking else candidates)[:3]
    assert result.provider == "openrouter"


@pytest.mark.parametrize("stage", ["retrieve", "ask"])
def test_invalid_limits_skip_all_work(stage):
    service = OpenRouterRAGService(None, None)
    with patch("app.rag.openrouter_service.retrieve", AsyncMock()) as search:
        with pytest.raises(ValueError):
            asyncio.run(service.retrieve("Question", top_k=0) if stage == "retrieve"
                        else service.ask("Question", context_budget=499))
        search.assert_not_awaited()


def test_full_flow_calls_bge_rerank_and_llama_and_resolves_citations():
    first, second = row("Background", .1), row("Specific answer", .2)
    database = SearchDatabase([[first, second], [], []])
    paths = []

    def handler(request):
        paths.append(request.url.path)
        payload = json.loads(request.content)
        if "evidence" not in json.loads(payload.get("messages", [{}, {"content": "{}"}])[1].get("content", "{}")):
            if response := scope_response(request):
                return response
        if request.url.path.endswith("/embeddings"):
            assert payload["model"] == "baai/bge-m3"
            assert payload["input"] == ["Growth question"]
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0] * 1024}]})
        if request.url.path.endswith("/rerank"):
            assert payload["model"] == "voyageai/rerank-2.5-lite"
            assert all("Episode guest" in document for document in payload["documents"])
            assert [document.split("Transcript:\n", 1)[1] for document in payload["documents"]] == ["Background", "Specific answer"]
            return httpx.Response(200, json={"results": [{"index": 1}, {"index": 0}]})
        assert request.url.path.endswith("/chat/completions")
        assert payload["model"] == "meta-llama/llama-3.1-8b-instruct"
        evidence = json.loads(payload["messages"][1]["content"])["evidence"]
        assert [(item["id"], item["text"]) for item in evidence] == [
            ("S1", "Specific answer"), ("S2", "Background")]
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": answer(True).model_dump_json()}}]})

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(handler))
        try:
            result = await OpenRouterRAGService(database, client).ask("Growth question")
            assert result.model == "meta-llama/llama-3.1-8b-instruct"
            assert result.answer.coverage == "complete"
            assert list(result.sources) == ["S1"]
            assert result.sources["S1"].chunk_id == second[0].id
        finally:
            await client.close()
    asyncio.run(check())
    assert paths == ["/api/v1/chat/completions", "/api/v1/embeddings", "/api/v1/rerank", "/api/v1/chat/completions"]
    assert database.active_sessions == 0


@pytest.mark.parametrize("failure", [None, ProviderError("Unavailable"), SQLAlchemyError("Unavailable"), TimeoutError()])
def test_refinement_retains_initial_answer_on_failure_and_keeps_source_ids(failure):
    first, second = passage("Initial"), passage("Additional evidence")
    service = OpenRouterRAGService(None, None)
    service.retrieve = AsyncMock(side_effect=[retrieval([first]), failure or retrieval([second, first])])
    service.generator.answer = AsyncMock(side_effect=[answer(), answer(True)])
    result = asyncio.run(service.ask("Multipart question"))
    assert result.answer.coverage == ("partial" if failure else "complete")
    assert result.sources["S1"].chunk_id == first.chunk_id
    assert service.retrieve.await_count == 2
    service.retrieve.assert_awaited_with("Designers at Airbnb", top_k=10, hybrid=True)
    assert service.generator.answer.await_count == (1 if failure else 2)
    if not failure:
        expanded = service.generator.answer.call_args.args[1]
        assert expanded["S1"] is first
        assert expanded["S2"] is second


@pytest.mark.parametrize("revision", ["worse", "failed", "same"])
def test_refined_answer_is_accepted_only_if_coverage_does_not_decrease(revision):
    first, second = passage("Initial"), passage("New")
    service = OpenRouterRAGService(None, None)
    service.retrieve = AsyncMock(side_effect=[retrieval([first]), retrieval([second])])
    initial = answer()
    if revision == "failed":
        revised = ProviderError("Invalid answer")
    elif revision == "worse":
        revised = initial.model_copy(update={"coverage": "unsupported", "sections": [], "summary_citation_ids": []})
    else:
        revised = initial.model_copy(update={"summary": "More detail"})
    service.generator.answer = AsyncMock(side_effect=[initial, revised])
    result = asyncio.run(service.ask("Question"))
    assert result.answer == (revised if revision == "same" else initial)
    assert result.sources["S1"] is first


def test_refinement_is_bounded_and_deduplicates_round_robin_candidates():
    first, second, third = passage("Initial"), passage("Second"), passage("Third")
    initial = answer().model_copy(update={"missing_topics": ["x" * 2500, "Other topic", "Unused topic"]})
    service = OpenRouterRAGService(None, None)
    service.retrieve = AsyncMock(side_effect=[retrieval([first]), retrieval([second, first]), retrieval([third, second])])
    service.generator.answer = AsyncMock(side_effect=[initial, initial])
    asyncio.run(service.ask("Question"))
    assert service.retrieve.await_count == 3
    assert service.retrieve.await_args_list[1].args == ("x" * 2000,)
    assert service.retrieve.await_args_list[2].args == ("Other topic",)
    expanded = service.generator.answer.call_args.args[1]
    assert list(expanded.values()) == [first, second, third]
    assert service.generator.answer.await_count == 2


def test_complete_answer_respects_context_budget_and_does_not_refine():
    service = OpenRouterRAGService(None, None)
    service.retrieve = AsyncMock(return_value=retrieval([passage("Evidence")]))
    service.generator.answer = AsyncMock(return_value=answer(True))
    with patch("app.rag.service.build_context", wraps=build_context) as context:
        asyncio.run(service.ask("Question", context_budget=6000))
    context.assert_called_once()
    assert context.call_args.kwargs == {"token_budget": 6000}
    assert service.retrieve.await_count == service.generator.answer.await_count == 1


def test_no_evidence_returns_unsupported_without_generation_or_refinement():
    service = OpenRouterRAGService(None, SimpleNamespace(post=AsyncMock()))
    service.retrieve = AsyncMock(return_value=retrieval([]))
    result = asyncio.run(service.ask("Question"))
    assert result.answer.coverage == "unsupported"
    assert result.sources == {}
    service.client.post.assert_not_awaited()
    assert service.retrieve.await_count == 1


@pytest.mark.parametrize("stage", ["retrieve", "answer"])
def test_initial_failures_propagate(stage):
    service = OpenRouterRAGService(None, None)
    error = ProviderError("Unavailable")
    service.retrieve = AsyncMock(side_effect=error if stage == "retrieve" else None,
                                 return_value=retrieval([passage("Evidence")]))
    service.generator.answer = AsyncMock(side_effect=error)
    with pytest.raises(ProviderError, match="Unavailable"):
        asyncio.run(service.ask("Question"))
    if stage == "retrieve":
        service.generator.answer.assert_not_awaited()
