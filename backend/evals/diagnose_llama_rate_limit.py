"""Inspect a single minimal structured-output request without logging credentials."""
import asyncio
import json

from app.core.config import get_settings
from app.llm.client import OpenRouterClient
from app.llm.openrouter_provider import OpenRouterAnswerProvider, WrittenAnswers, schema_format


async def main():
    key = get_settings().openrouter_api_key.get_secret_value()
    client = OpenRouterClient(key)
    try:
        result = await client.http.post("chat/completions", json={
            "model": OpenRouterAnswerProvider.model, "max_tokens": 50,
            "structured_outputs": True, "response_format": schema_format(WrittenAnswers, "written_answers"),
            "provider": {"require_parameters": True},
            "messages": [{"role": "user", "content": 'Return {"answers":["Diagnostic test"]}.'}],
        })
        data = result.json()
        diagnostic = {"status": result.status_code, "retry_after": result.headers.get("retry-after"),
                      "error": data.get("error"), "provider": data.get("provider"), "model": data.get("model")}
        print(json.dumps(diagnostic, ensure_ascii=True).replace(key, "[redacted]"))
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
