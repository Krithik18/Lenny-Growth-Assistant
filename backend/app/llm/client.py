"""Bounded OpenAI HTTP transport; errors never contain credentials or payloads."""

import httpx


class ProviderError(RuntimeError):
    pass


class OpenAIClient:
    def __init__(self, api_key: str, transport=None):
        if not api_key:
            raise ProviderError("OPENAI_API_KEY is not configured.")
        self.http = httpx.AsyncClient(
            base_url="https://api.openai.com/v1/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(90, connect=10), transport=transport,
        )

    async def post(self, path: str, payload: dict) -> dict:
        try:
            response = await self.http.post(path, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            raise ProviderError(f"OpenAI request failed (HTTP {error.response.status_code}).") from None
        except (httpx.HTTPError, ValueError):
            raise ProviderError("OpenAI request failed or returned invalid JSON.") from None

    async def close(self):
        await self.http.aclose()
