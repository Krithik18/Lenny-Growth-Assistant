import asyncio
import json

import httpx
import pytest

from app.llm.client import OpenRouterClient, ProviderError
from app.rag.openrouter_embeddings import OpenRouterEmbeddings


def test_embedding_spec():
    spec = OpenRouterEmbeddings.spec
    assert spec.provider == "openrouter"
    assert spec.model == "baai/bge-m3"
    assert spec.dimensions == 1024
    assert spec.input_version == "raw-chunk-v1"


@pytest.mark.parametrize("texts", [["first chunk", "second chunk"], ("first chunk", "second chunk")])
def test_documents_send_model_and_restore_input_order(texts):
    first, second = [1.0] * 1024, [2.0] * 1024

    def handler(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/embeddings"
        assert json.loads(request.content) == {
            "model": "baai/bge-m3", "input": list(texts),
            "dimensions": 1024, "encoding_format": "float",
        }
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": second}, {"index": 0, "embedding": first},
        ]})

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(handler))
        try:
            assert await OpenRouterEmbeddings(client).embed_documents(texts) == [first, second]
        finally:
            await client.close()

    asyncio.run(check())


def test_query_returns_single_vector():
    vector = [0.5] * 1024

    def handler(request):
        assert json.loads(request.content) == {
            "model": "baai/bge-m3", "input": ["User question"],
            "dimensions": 1024, "encoding_format": "float",
        }
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": vector}]})

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(handler))
        try:
            assert await OpenRouterEmbeddings(client).embed_query("User question") == vector
        finally:
            await client.close()

    asyncio.run(check())


def test_empty_documents_skip_api_call():
    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(
            lambda request: pytest.fail("Unexpected API call")))
        try:
            assert await OpenRouterEmbeddings(client).embed_documents([]) == []
        finally:
            await client.close()

    asyncio.run(check())


@pytest.mark.parametrize("payload", [
    {}, None, {"data": None}, {"data": []},
    {"data": [{}]},
    {"data": [{"index": 0}]},
    {"data": [{"index": 1, "embedding": [1.0] * 1024}]},
    {"data": [{"index": -1, "embedding": [1.0] * 1024}]},
    {"data": [{"index": 0, "embedding": [1.0] * 1024}] * 2},
    {"data": [{"index": 0, "embedding": [1.0] * 1536}]},
    {"data": [{"index": 0, "embedding": [1.0] * 1023}]},
    {"data": [{"index": 0, "embedding": [0.0] * 1024}]},
    {"data": [{"index": 0, "embedding": ["private payload"] * 1024}]},
    {"data": [{"index": 0, "embedding": None}]},
])
def test_invalid_embeddings_raise_sanitized_provider_error(payload):
    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=json.dumps(payload))))
        try:
            with pytest.raises(ProviderError, match=r"^OpenRouter returned invalid embeddings\.$"):
                await OpenRouterEmbeddings(client).embed_documents(["chunk"])
        finally:
            await client.close()

    asyncio.run(check())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_vectors_are_rejected(value):
    async def check():
        vector = [1.0] * 1023 + [value]
        client = OpenRouterClient("fake", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=json.dumps(
                {"data": [{"index": 0, "embedding": vector}]}))))
        try:
            with pytest.raises(ProviderError, match=r"^OpenRouter returned invalid embeddings\.$"):
                await OpenRouterEmbeddings(client).embed_documents(["chunk"])
        finally:
            await client.close()

    asyncio.run(check())


@pytest.mark.parametrize("method,input_value", [("embed_documents", ["chunk"]), ("embed_query", "question")])
def test_client_errors_propagate(method, input_value):
    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(
            lambda request: httpx.Response(429, text="private payload")))
        try:
            with pytest.raises(ProviderError, match=r"^OpenRouter request failed \(HTTP 429\)\.$"):
                await getattr(OpenRouterEmbeddings(client), method)(input_value)
        finally:
            await client.close()

    asyncio.run(check())
