import asyncio
import json

import httpx
import pytest

from app.llm.client import OpenRouterClient, ProviderError


@pytest.mark.parametrize("api_key", ["", None])
def test_missing_api_key(api_key):
    with pytest.raises(ProviderError, match=r"^OPENROUTER_API_KEY is not configured\.$"):
        OpenRouterClient(api_key)


@pytest.mark.parametrize("path", ["chat/completions", "/chat/completions"])
def test_post_sends_authenticated_json_and_returns_response(path):
    payload = {"model": "meta-llama/llama-3.1-8b-instruct",
               "messages": [{"role": "user", "content": "Question"}]}
    result = {"choices": [{"message": {"content": "Answer"}}]}

    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.headers["Content-Type"] == "application/json"
        assert json.loads(request.content) == payload
        assert request.extensions["timeout"] == {
            "connect": 10, "read": 90, "write": 90, "pool": 90,
        }
        return httpx.Response(200, json=result)

    async def check():
        client = OpenRouterClient("test-key", transport=httpx.MockTransport(handler))
        try:
            assert await client.post(path, payload) == result
            assert payload["model"] == "meta-llama/llama-3.1-8b-instruct"
        finally:
            await client.close()

    asyncio.run(check())


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 502, 503])
def test_http_errors_are_sanitized(status):
    async def check():
        client = OpenRouterClient("secret-key", transport=httpx.MockTransport(
            lambda request: httpx.Response(status, text="private response secret-key")))
        try:
            with pytest.raises(ProviderError) as error:
                await client.post("chat/completions", {"private": "payload"})
            assert str(error.value) == f"OpenRouter request failed (HTTP {status})."
            assert error.value.__suppress_context__ is True
        finally:
            await client.close()

    asyncio.run(check())


@pytest.mark.parametrize("error_type", [
    httpx.ConnectError, httpx.ReadError, httpx.ConnectTimeout,
    httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout,
    httpx.RemoteProtocolError,
])
def test_transport_errors_are_sanitized(error_type):
    def handler(request):
        raise error_type("private payload secret-key", request=request)

    async def check():
        client = OpenRouterClient("secret-key", transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderError) as error:
                await client.post("chat/completions", {})
            assert str(error.value) == "OpenRouter request failed or returned invalid JSON."
            assert error.value.__suppress_context__ is True
        finally:
            await client.close()

    asyncio.run(check())


@pytest.mark.parametrize("body", ["", "invalid JSON", "<html>private payload secret-key</html>"])
def test_invalid_json_is_sanitized(body):
    async def check():
        client = OpenRouterClient("secret-key", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=body)))
        try:
            with pytest.raises(ProviderError) as error:
                await client.post("chat/completions", {})
            assert str(error.value) == "OpenRouter request failed or returned invalid JSON."
            assert error.value.__suppress_context__ is True
        finally:
            await client.close()

    asyncio.run(check())


def test_close_releases_transport_and_is_repeatable():
    class TrackingTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.close_calls = 0

        async def handle_async_request(self, request):
            return httpx.Response(200, json={})

        async def aclose(self):
            self.close_calls += 1

    async def check():
        transport = TrackingTransport()
        client = OpenRouterClient("test-key", transport=transport)
        assert not client.http.is_closed
        await client.close()
        assert client.http.is_closed
        assert transport.close_calls == 1
        await client.close()
        assert transport.close_calls == 1

    asyncio.run(check())
