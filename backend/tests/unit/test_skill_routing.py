import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.client import ProviderError
from app.rag.openrouter_service import OpenRouterRAGService
from app.skills import catalog, registry
from app.skills.routing import select_skill


def response(provider, content):
    if provider == "openrouter":
        return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
    return {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": content}]}]}


def service(provider, payload):
    client = SimpleNamespace(post=AsyncMock(return_value=payload))
    if provider == "openrouter":
        return OpenRouterRAGService(None, client)
    return SimpleNamespace(client=client, generator=SimpleNamespace(model="gpt-6-luna"))


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
@pytest.mark.parametrize("skill", ["podcast-qa", "ship30-essay", "simple-artifact"])
def test_valid_decisions_use_selected_model_and_bounded_context(provider, skill):
    selected = service(provider, response(provider, json.dumps({"skill": skill, "needs_evidence": True})))
    history = [{"role": "assistant", "skill": "ship30-essay", "content": str(i) + "x" * 16000}
               for i in range(12)]
    result = asyncio.run(select_skill(selected, "Why does this matter?", history))
    assert result.skill == skill
    assert result.needs_evidence is True
    path, payload = selected.client.post.call_args.args
    assert payload["model"] == selected.generator.model
    if provider == "openrouter":
        assert path == "chat/completions"
        assert payload["max_tokens"] == 160
        data = json.loads(payload["messages"][1]["content"])
    else:
        assert path == "responses"
        assert payload["store"] is False
        assert payload["text"]["format"]["strict"] is True
        data = json.loads(payload["input"])
    assert data["message"] == "Why does this matter?"
    assert data["skills"] == catalog()
    assert len(data["history"]) == 6
    assert all(len(turn["content"]) == 1500 for turn in data["history"])
    assert data["history"][0]["content"].startswith("6")
    assert history[0]["content"] == "0" + "x" * 16000
    assert "Application output contract" not in json.dumps(data)


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
@pytest.mark.parametrize("content", [
    "private payload", "{}", "null", "[]",
    '{"skill":"unknown","needs_evidence":true}',
    '{"skill":"podcast-qa","needs_evidence":"false"}',
    '{"skill":"simple-artifact"}',
    '{"skill":"ship30-essay","needs_evidence":true,"instructions":"private payload"}',
    "x" * 2001,
])
def test_invalid_decisions_raise_safe_retryable_error(provider, content):
    selected = service(provider, response(provider, content))
    with pytest.raises(ProviderError, match="couldn't choose a skill") as failure:
        asyncio.run(select_skill(selected, "Question", []))
    assert "private payload" not in str(failure.value)
    assert selected.client.post.await_count == 1


@pytest.mark.parametrize("provider,payload", [
    ("openai", None), ("openai", {"status": "incomplete"}),
    ("openai", {"status": "completed", "output": [None]}),
    ("openai", {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "refusal", "refusal": "private payload"}]}]}),
    ("openrouter", {"choices": []}), ("openrouter", {"choices": [None]}),
    ("openrouter", {"choices": [{"finish_reason": "length", "message": {"content": "private payload"}}]}),
    ("openrouter", {"choices": [{"finish_reason": "stop", "message": {"content": "{}", "tool_calls": [{}]}}]}),
    ("openrouter", {"choices": [{"finish_reason": "stop", "message": {"refusal": "private payload"}}]}),
])
def test_incomplete_or_refused_decisions_never_fall_back(provider, payload):
    with pytest.raises(ProviderError, match="couldn't choose a skill"):
        asyncio.run(select_skill(service(provider, payload), "Question", []))


def test_timeout_is_bounded_and_user_can_retry(monkeypatch):
    async def timeout(awaitable, *, timeout):
        assert timeout == 25
        await awaitable
        raise TimeoutError

    monkeypatch.setattr("app.skills.routing.asyncio.wait_for", timeout)
    with pytest.raises(ProviderError, match="took too long"):
        asyncio.run(select_skill(service("openai", {}), "Question", []))


def test_catalog_uses_skill_metadata_and_execution_loads_full_instructions():
    essay = registry()["ship30-essay"]
    artifact = registry()["simple-artifact"]
    assert "revise" in essay.description
    assert "1,250" in essay.instructions()
    assert "No dependencies" in artifact.instructions()
    assert {item["name"] for item in catalog()} == {"podcast-qa", "ship30-essay", "simple-artifact"}
