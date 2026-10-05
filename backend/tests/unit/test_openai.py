import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.llm.client import OpenAIClient, ProviderError
from app.llm.openai_provider import OpenAIAnswerProvider
from app.main import create_app
from app.rag.openai_embeddings import OpenAIEmbeddings


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("citation,insufficient,valid", [("S1", False, True), ("invented", False, False), ("S1", True, True)])
def test_answers_enforce_source_ids_and_model(citation, insufficient, valid):
    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "gpt-6-luna"
        assert body["store"] is False
        answer = {"insufficient_evidence": insufficient, "summary": "Summary",
                  "coverage": "partial" if insufficient else "complete",
                  "summary_citation_ids": [citation], "missing_topics": ["Designers at Airbnb"] if insufficient else [],
                  "sections": [{"heading": "Advice", "content": "Grounded advice", "citation_ids": [citation]}]}
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}]})

    async def check():
        client = OpenAIClient("fake", transport=httpx.MockTransport(handler))
        try:
            operation = OpenAIAnswerProvider(client).answer("Question", {"S1": SimpleNamespace(title="Episode", text="Evidence")})
            if valid:
                assert (await operation).sections[0].citation_ids == ["S1"]
            else:
                with pytest.raises(ProviderError):
                    await operation
        finally:
            await client.close()
    run(check())


@pytest.mark.parametrize("summary_ids,coverage,missing,valid", [
    ([], "complete", [], False),
    (["unknown"], "complete", [], False),
    (["S1"], "complete", ["Missing topic"], False),
    ([], "unsupported", ["Missing topic"], True),
])
def test_summary_citations_and_uncited_abstentions(summary_ids, coverage, missing, valid):
    payload = {"coverage": coverage, "insufficient_evidence": coverage != "complete",
               "summary": "An uncited factual claim", "summary_citation_ids": summary_ids,
               "sections": [] if coverage == "unsupported" else [
                   {"heading": "Advice", "content": "Evidence", "citation_ids": ["S1"]}],
               "missing_topics": missing}
    async def check():
        client = OpenAIClient("fake", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
            "status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": json.dumps(payload)}]}]})))
        try:
            operation = OpenAIAnswerProvider(client).answer("Question", {"S1": SimpleNamespace(title="Episode", text="Evidence")})
            if valid:
                assert (await operation).summary != "An uncited factual claim"
            else:
                with pytest.raises(ProviderError):
                    await operation
        finally:
            await client.close()
    run(check())


def test_embeddings_restore_order():
    async def check():
        client = OpenAIClient("fake", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
            "data": [{"index": 1, "embedding": [2.] * 1536}, {"index": 0, "embedding": [1.] * 1536}]})))
        try:
            assert (await OpenAIEmbeddings(client).embed_documents(["first", "second"]))[0][0] == 1
        finally:
            await client.close()
    run(check())


def test_provider_errors_do_not_expose_response_or_key():
    async def check():
        client = OpenAIClient("secret-key", transport=httpx.MockTransport(lambda request: httpx.Response(429, text="private payload")))
        try:
            with pytest.raises(ProviderError, match=r"^OpenAI request failed \(HTTP 429\).$"):
                await client.post("responses", {})
        finally:
            await client.close()
    run(check())


def test_rag_disabled_in_production():
    with TestClient(create_app(Settings(_env_file=None, database_url="", openai_api_key="", app_env="production"))) as client:
        assert client.post("/api/v1/rag/ask", json={"question": "Question"}).status_code == 403


def test_question_validation_and_missing_configuration():
    with TestClient(create_app(Settings(_env_file=None, database_url="", openai_api_key=""))) as client:
        assert client.post("/api/v1/rag/ask", json={"question": "Question"}).status_code == 503


def test_no_evidence_skips_generation():
    async def check():
        client = OpenAIClient("fake", transport=httpx.MockTransport(lambda request: pytest.fail("Unexpected API call")))
        try:
            assert (await OpenAIAnswerProvider(client).answer("Question", {})).insufficient_evidence
        finally:
            await client.close()
    run(check())


@pytest.mark.parametrize("payload", [
    {"status": "incomplete", "output": []},
    {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}]},
    {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "invalid JSON"}]}]},
])
def test_incomplete_refused_and_malformed_answers_fail_closed(payload):
    async def check():
        client = OpenAIClient("fake", transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
        try:
            with pytest.raises(ProviderError):
                await OpenAIAnswerProvider(client).answer("Question", {"S1": SimpleNamespace(title="Episode", text="Evidence")})
        finally:
            await client.close()
    run(check())
