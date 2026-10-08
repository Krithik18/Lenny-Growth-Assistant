"""Bounded OpenAI HTTP transport; errors never contain credentials or payloads."""

import httpx
import time


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


class OpenRouterClient:
    def __init__(self, api_key: str, transport=None):
        if not api_key:
            raise ProviderError("OPENROUTER_API_KEY is not configured.")
        self.http = httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(90, connect=10), transport=transport,
        )
        self._native_cooldowns = {}

    def _available_payload(self, payload):
        if not payload.get("structured_outputs") or self._native_cooldowns.get(payload.get("model"), 0) <= time.monotonic():
            return payload
        # Keep the selected model and all generation instructions. Other Llama
        # endpoints support JSON mode; callers still validate their full schemas.
        fallback = {key: value for key, value in payload.items() if key != "structured_outputs"}
        fallback["response_format"] = {"type": "json_object"}
        preferences = payload.get("provider", {})
        fallback["provider"] = {**preferences, "ignore": list(dict.fromkeys([*preferences.get("ignore", []), "CoreWeave"]))}
        return fallback

    async def post(self, path: str, payload: dict) -> dict:
        try:
            for attempt in range(2):
                active = self._available_payload(payload)
                response = await self.http.post(path, json=active)
                if attempt == 0 and response.status_code == 429 and active.get("structured_outputs"):
                    try:
                        provider = response.json().get("error", {}).get("metadata", {}).get("provider_name")
                    except (ValueError, AttributeError):
                        provider = None
                    if provider == "CoreWeave" and not active.get("provider", {}).get("only"):
                        self._native_cooldowns[payload.get("model")] = time.monotonic() + 60
                        continue
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as error:
            raise ProviderError(f"OpenRouter request failed (HTTP {error.response.status_code}).") from None
        except (httpx.HTTPError, ValueError):
            raise ProviderError("OpenRouter request failed or returned invalid JSON.") from None

    async def close(self):
        await self.http.aclose()
