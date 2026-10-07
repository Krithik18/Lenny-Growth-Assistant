import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.llm.client import OpenRouterClient, ProviderError
from app.llm.openrouter_provider import OpenRouterAnswerProvider
from app.schemas.answer import GroundedAnswer


SOURCES = {
    "S1": SimpleNamespace(title="Episode", text="Supplied evidence"),
    "S2": SimpleNamespace(title="Other episode", text="Other evidence"),
}
VALID = {
    "coverage": "complete", "insufficient_evidence": False,
    "summary": "Supported summary", "summary_citation_ids": ["S1"],
    "sections": [{"heading": "Advice", "content": "Supported advice", "citation_ids": ["S1"]}],
    "missing_topics": [],
}


def response(answer, finish_reason="stop"):
    return {"choices": [{"finish_reason": finish_reason,
                         "message": {"role": "assistant", "content": json.dumps(answer)}}]}


@pytest.mark.parametrize("coverage", ["complete", "partial"])
def test_request_and_grounded_answer_contract(coverage):
    expected = copy.deepcopy(VALID)
    if coverage == "partial":
        expected.update(coverage="partial", insufficient_evidence=True, missing_topics=["Unanswered topic"])

    def handler(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer fake"
        payload = json.loads(request.content)
        assert payload["model"] == "meta-llama/llama-3.1-8b-instruct"
        assert payload["max_tokens"] == 1800
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["provider"] == {"require_parameters": True}
        system, user = payload["messages"]
        assert system["role"] == "system"
        assert "Answer only from supplied podcast evidence" in system["content"]
        assert json.dumps(GroundedAnswer.model_json_schema()) in system["content"]
        assert user["role"] == "user"
        assert json.loads(user["content"]) == {
            "question": "Question", "evidence": [
                {"id": key, "title": value.title, "text": value.text}
                for key, value in SOURCES.items()
            ],
        }
        return httpx.Response(200, json=response(expected))

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(handler))
        try:
            answer = await OpenRouterAnswerProvider(client).answer("Question", SOURCES)
            assert isinstance(answer, GroundedAnswer)
            assert answer.model_dump() == expected
        finally:
            await client.close()
    asyncio.run(check())


def test_no_sources_skips_generation():
    client = SimpleNamespace(post=AsyncMock())
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Question", {}))
    assert answer.coverage == "unsupported"
    assert answer.insufficient_evidence is True
    assert answer.sections == answer.summary_citation_ids == []
    assert answer.missing_topics == ["Question"]
    client.post.assert_not_awaited()


def test_unsupported_answer_replaces_uncited_model_claim():
    payload = dict(VALID, coverage="unsupported", insufficient_evidence=True,
                   sections=[], summary_citation_ids=[], missing_topics=["Question"])
    client = SimpleNamespace(post=AsyncMock(return_value=response(payload)))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert answer.summary == "The retrieved podcast passages do not provide enough evidence to answer this question."


@pytest.mark.parametrize("update", [
    {"summary_citation_ids": []}, {"summary_citation_ids": ["invented"]},
    {"summary_citation_ids": ["S2"]}, {"summary": "  "}, {"sections": []},
    {"sections": [{"heading": "Advice", "content": "Claim", "citation_ids": []}]},
    {"sections": [{"heading": "Advice", "content": "Claim", "citation_ids": ["invented"]}]},
    {"sections": [{"heading": " ", "content": "Claim", "citation_ids": ["S1"]}]},
    {"sections": [{"heading": "Advice", "content": " ", "citation_ids": ["S1"]}]},
    {"insufficient_evidence": True}, {"missing_topics": ["Unexpected gap"]},
    {"coverage": "partial", "insufficient_evidence": True},
    {"coverage": "partial", "insufficient_evidence": True, "missing_topics": [" "]},
    {"coverage": "unsupported", "insufficient_evidence": True, "missing_topics": ["Question"]},
    {"coverage": "unsupported", "insufficient_evidence": True, "missing_topics": ["Question"], "sections": []},
    {"extra": "private payload"}, {"insufficient_evidence": "false"},
])
def test_invalid_citations_and_coverage_raise_provider_error(update):
    payload = dict(copy.deepcopy(VALID), **update)
    client = SimpleNamespace(post=AsyncMock(return_value=response(payload)))
    with pytest.raises(ProviderError, match="^OpenRouter answer was incomplete, refused, or failed evidence validation\\.$"):
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))


@pytest.mark.parametrize("payload", [
    None, {}, {"error": {"message": "private payload"}}, {"choices": None}, {"choices": []},
    {"choices": [None]}, {"choices": [{}]},
    response(VALID, "length"), response(VALID, "content_filter"), response(VALID, "error"),
    {"choices": [{"finish_reason": "stop", "message": None}]},
    {"choices": [{"finish_reason": "stop", "message": {"refusal": "private payload", "content": json.dumps(VALID)}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "private payload"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": []}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(VALID), "tool_calls": [{}]}}]},
])
def test_malformed_incomplete_or_refused_response_fails_closed(payload):
    client = SimpleNamespace(post=AsyncMock(return_value=payload))
    with pytest.raises(ProviderError) as error:
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert str(error.value) == "OpenRouter answer was incomplete, refused, or failed evidence validation."


@pytest.mark.parametrize("failure", [429, "timeout", "invalid_json"])
def test_transport_errors_raise_sanitized_provider_error(failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private payload", request=request)
        if failure == "invalid_json":
            return httpx.Response(200, text="private payload")
        return httpx.Response(failure, text="private payload")

    async def check():
        client = OpenRouterClient("secret-key", transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderError) as error:
                await OpenRouterAnswerProvider(client).answer("Question", SOURCES)
            assert "private payload" not in str(error.value)
            assert "secret-key" not in str(error.value)
        finally:
            await client.close()
    asyncio.run(check())
