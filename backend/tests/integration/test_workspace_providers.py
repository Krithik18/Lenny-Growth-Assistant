import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.llm.client import ProviderError
from app.main import create_app
from app.rag.openrouter_service import OpenRouterRAGService
from app.rag.service import RAGService
from app.schemas.answer import AnswerResult, GroundedAnswer, AnswerSection
from app.schemas.retrieval import RetrievedPassage
from test_workspace import generated


def grounded(model):
    source = RetrievedPassage(
        chunk_id=uuid4(), episode_id=uuid4(), episode_revision_id=uuid4(),
        title="Growth discussion", guest="Guest", source_url=None,
        archive_member="test", archive_sha256="test", text="Measure activation.",
        start_char=0, end_char=19, start_seconds=0, end_seconds=10, similarity=.8,
    )
    return AnswerResult(question="Question", model=model, sources={"S1": source}, answer=GroundedAnswer(
        coverage="complete", insufficient_evidence=False, summary="Measure activation.",
        summary_citation_ids=["S1"], missing_topics=[],
        sections=[AnswerSection(heading="Start here", content="Measure activation first.", citation_ids=["S1"])],
    ))


def chat_generated(language="markdown", content=None):
    output = json.loads(generated(language, content)["output"][0]["content"][0]["text"])
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]}


@pytest.fixture
def providers():
    database = SimpleNamespace(close=AsyncMock())
    openai = SimpleNamespace(post=AsyncMock(return_value=generated()), close=AsyncMock())
    openrouter = SimpleNamespace(post=AsyncMock(return_value=chat_generated()), close=AsyncMock())
    settings = Settings(_env_file=None, app_env="test", database_url="postgresql+asyncpg://test",
                        openai_api_key="fake-openai", openrouter_api_key="fake-openrouter")
    with patch("app.main.Database", return_value=database), \
         patch("app.main.OpenAIClient", return_value=openai), \
         patch("app.main.OpenRouterClient", return_value=openrouter):
        app = create_app(settings)
        with TestClient(app) as client:
            assert type(app.state.rag) is RAGService
            assert type(app.state.openrouter_rag) is OpenRouterRAGService
            assert app.state.rag.client is openai
            assert app.state.openrouter_rag.client is openrouter
            services = {"openai": app.state.rag, "openrouter": app.state.openrouter_rag}
            for service in services.values():
                service.ask = AsyncMock(return_value=grounded(service.generator.model))
            yield client, services
        openai.close.assert_awaited_once()
        openrouter.close.assert_awaited_once()
        database.close.assert_awaited_once()


@pytest.mark.parametrize("provider", [None, "openai", "openrouter"])
def test_chat_selects_requested_provider_and_defaults_to_openai(providers, provider):
    client, services = providers
    body = {"message": "How to grow?", "history": [{"role": "user", "content": "Activation"}]}
    if provider is not None:
        body["provider"] = provider
    result = client.post("/api/v1/workspace/chat", json=body)
    assert result.status_code == 200
    assert "[S1]" in result.json()["message"]
    assert result.json()["sources"]["S1"]["title"] == "Growth discussion"
    assert result.json()["coverage"] == "complete"
    selected = provider or "openai"
    services[selected].ask.assert_awaited_once()
    assert "Activation" in services[selected].ask.call_args.args[0]
    services["openrouter" if selected == "openai" else "openai"].ask.assert_not_awaited()
    for service in services.values():
        service.client.post.assert_not_awaited()


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
@pytest.mark.parametrize("mode", ["code", "essay"])
def test_artifacts_use_selected_provider_protocol(providers, provider, mode):
    client, services = providers
    selected = services[provider]
    if mode == "code":
        selected.client.post.return_value = (chat_generated if provider == "openrouter" else generated)(
            "html", "<button>Try it</button>")
    response = client.post("/api/v1/workspace/chat", json={"message": "Create it", "mode": mode, "provider": provider})
    assert response.status_code == 200
    assert response.json()["artifact"]["language"] == ("html" if mode == "code" else "markdown")
    path, payload = selected.client.post.call_args.args
    assert payload["model"] == selected.generator.model
    if provider == "openrouter":
        assert path == "chat/completions"
        assert payload["response_format"] == {"type": "json_object"}
        data = json.loads(payload["messages"][1]["content"])
    else:
        assert path == "responses"
        data = json.loads(payload["input"])
    if mode == "essay":
        assert "verified_answer" in data
        assert response.json()["sources"]["S1"]["title"] == "Growth discussion"
    else:
        selected.ask.assert_not_awaited()
    other = services["openrouter" if provider == "openai" else "openai"]
    other.ask.assert_not_awaited()
    other.client.post.assert_not_awaited()


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
@pytest.mark.parametrize("failure,status", [(ProviderError("Safe failure"), 502), (SQLAlchemyError("private payload"), 503)])
def test_selected_service_errors_keep_existing_http_mapping(providers, provider, failure, status):
    client, services = providers
    services[provider].ask.side_effect = failure
    result = client.post("/api/v1/workspace/chat", json={"message": "Question", "provider": provider})
    assert result.status_code == status
    assert "private payload" not in result.text


@pytest.mark.parametrize("provider", ["unknown", "ollama", None, 42])
def test_invalid_provider_is_rejected_before_service_calls(providers, provider):
    client, services = providers
    assert client.post("/api/v1/workspace/chat", json={"message": "Question", "provider": provider}).status_code == 422
    for service in services.values():
        service.ask.assert_not_awaited()
        service.client.post.assert_not_awaited()


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_unconfigured_selection_does_not_fall_back_to_other_provider(providers, provider):
    client, services = providers
    setattr(client.app.state, "rag" if provider == "openai" else "openrouter_rag", None)
    result = client.post("/api/v1/workspace/chat", json={"message": "Question", "provider": provider})
    assert result.status_code == 503
    assert ("OPENAI_API_KEY" if provider == "openai" else "OPENROUTER_API_KEY") in result.json()["detail"]
    for service in services.values():
        service.ask.assert_not_awaited()


def test_openrouter_only_configuration_works_and_openai_remains_default():
    settings = Settings(_env_file=None, app_env="test", database_url="postgresql+asyncpg://test",
                        openai_api_key="", openrouter_api_key="fake")
    transport = SimpleNamespace(post=AsyncMock(), close=AsyncMock())
    database = SimpleNamespace(close=AsyncMock())
    with patch("app.main.Database", return_value=database), \
         patch("app.main.OpenRouterClient", return_value=transport), \
         patch("app.main.OpenAIClient") as openai:
        app = create_app(settings)
        with TestClient(app) as client:
            app.state.openrouter_rag.ask = AsyncMock(return_value=grounded("meta-llama/llama-3.1-8b-instruct"))
            assert client.post("/api/v1/workspace/chat", json={"message": "Question", "provider": "openrouter"}).status_code == 200
            assert client.post("/api/v1/workspace/chat", json={"message": "Question"}).status_code == 503
            openai.assert_not_called()
        transport.close.assert_awaited_once()


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
@pytest.mark.parametrize("environment,remote", [("production", False), ("test", True)])
def test_access_guards_apply_to_both_providers(provider, environment, remote):
    app = create_app(Settings(_env_file=None, app_env=environment, database_url="",
                              openai_api_key="", openrouter_api_key=""))
    options = {"client": ("198.51.100.2", 1234)} if remote else {}
    with TestClient(app, **options) as client:
        assert client.post("/api/v1/workspace/chat", json={"message": "Question", "provider": provider}).status_code == 403


@pytest.mark.parametrize("payload", [
    None, {}, {"choices": []}, {"choices": [None]},
    {"choices": [{"finish_reason": "length", "message": {"content": "private payload"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"refusal": "private payload"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "private payload"}}]},
])
def test_openrouter_artifact_errors_fail_closed(providers, payload):
    client, services = providers
    services["openrouter"].client.post.return_value = payload
    result = client.post("/api/v1/workspace/chat", json={"message": "Create it", "mode": "code", "provider": "openrouter"})
    assert result.status_code == 502
    assert "private payload" not in result.text


def test_openrouter_essay_rejects_invented_citations(providers):
    client, services = providers
    services["openrouter"].client.post.return_value = chat_generated(content="Unsupported claim [S999]")
    result = client.post("/api/v1/workspace/chat", json={"message": "Essay", "mode": "essay", "provider": "openrouter"})
    assert result.status_code == 502


def test_legacy_rag_endpoints_still_use_openai(providers):
    client, services = providers
    result = client.post("/api/v1/rag/ask", json={"question": "Question"})
    assert result.status_code == 200
    assert result.json()["model"] == "gpt-6-luna"
    services["openai"].ask.assert_awaited_once_with("Question")
    services["openrouter"].ask.assert_not_awaited()


def test_openapi_documents_provider_enum_and_default(providers):
    client, _ = providers
    schema = client.get("/openapi.json").json()
    provider = schema["components"]["schemas"]["WorkspaceRequest"]["properties"]["provider"]
    assert provider["enum"] == ["openai", "openrouter"]
    assert provider["default"] == "openai"


def test_openrouter_essay_revision_stays_with_selected_provider(providers):
    client, services = providers
    selected = services["openrouter"]
    selected.client.post.side_effect = [chat_generated(content="A short answer. [S1]"), chat_generated()]
    result = client.post("/api/v1/workspace/chat", json={"message": "Essay", "mode": "essay", "provider": "openrouter"})
    assert result.status_code == 200
    assert selected.client.post.await_count == 2
    assert all(call.args[0] == "chat/completions" for call in selected.client.post.await_args_list)
    assert "draft" in json.loads(selected.client.post.call_args.args[1]["messages"][1]["content"])
    services["openai"].client.post.assert_not_awaited()
