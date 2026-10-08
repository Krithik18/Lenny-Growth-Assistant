import json
import re
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


def llama_essay(content=None):
    if content is None:
        content = '**Start with activation.**\n\n- Measure the first experience.\n- Inspect friction.\n- Review results.\n\n' + 'A grounded explanation of the first experience. ' * 40
        source_ids = ['S1']
    else:
        source_ids = re.findall(r'\[(S\d+)\]', content)
    output = {"title": "A useful idea", "sections": [
        {"heading": "Growth step " + str(index + 1), "content": content, "source_ids": source_ids}
        for index in range(4)]}
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]}


def test_llama_short_essay_can_use_one_section(providers):
    client, services = providers
    output = {"title": "Activation", "sections": [{"heading": "Reach value", "content":
        "**Start with value.**\n\n- Measure activation.\n\nHelp users reach value before investing in acquisition.",
        "source_ids": ["S1"]}]}
    selected = services['openrouter']
    selected.client.post.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]}
    result = client.post('/api/v1/workspace/chat', json={'message': 'Write a short essay on activation', 'mode': 'essay', 'provider': 'openrouter'})
    assert result.status_code == 200
    assert len(result.json()['artifact']['content'].split()) < 100
    assert selected.client.post.call_count == 1
    services['openai'].client.post.assert_not_called()


def test_llama_essay_persistent_overflow_is_rejected(providers):
    client, services = providers
    selected = services['openrouter']
    selected.client.post.return_value = llama_essay(content='**Value.** [S1]\n\n- Measure activation.\n\n' + 'Explanation ' * 400)
    result = client.post('/api/v1/workspace/chat', json={'message': 'Write an essay on growth', 'mode': 'essay', 'provider': 'openrouter'})
    assert result.status_code == 502
    assert selected.client.post.call_count == 2
    services['openai'].client.post.assert_not_called()


def routed(provider, skill, needs_evidence=True):
    content = json.dumps({"skill": skill, "needs_evidence": needs_evidence})
    if provider == "openrouter":
        return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
    return {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": content}]}]}


@pytest.fixture
def providers(request):
    environment, remote = getattr(request, "param", ("test", False))
    database = SimpleNamespace(close=AsyncMock())
    openai = SimpleNamespace(post=AsyncMock(return_value=generated()), close=AsyncMock())
    openrouter = SimpleNamespace(post=AsyncMock(return_value=llama_essay()), close=AsyncMock())
    settings = Settings(_env_file=None, app_env=environment, database_url="postgresql+asyncpg://test",
                        openai_api_key="fake-openai", openrouter_api_key="fake-openrouter")
    with patch("app.main.Database", return_value=database), \
         patch("app.main.OpenAIClient", return_value=openai), \
         patch("app.main.OpenRouterClient", return_value=openrouter):
        app = create_app(settings)
        options = {"client": ("198.51.100.2", 1234)} if remote else {}
        with TestClient(app, **options) as client:
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
@pytest.mark.parametrize("providers", [("test", False), ("production", True)], indirect=True)
def test_chat_selects_requested_provider_and_defaults_to_openai(providers, provider):
    client, services = providers
    body = {"message": "How to grow?", "mode": "chat", "history": [{"role": "user", "content": "Activation"}]}
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
        assert payload["response_format"]["type"] == ("json_schema" if mode == "code" else "json_object")
        if mode == "code":
            assert payload["response_format"]["json_schema"]["strict"] is True
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
    result = client.post("/api/v1/workspace/chat", json={"message": "Question", "mode": "chat", "provider": provider})
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
@pytest.mark.parametrize("providers", [("test", False), ("production", True)], indirect=True)
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
            assert client.post("/api/v1/workspace/chat", json={"message": "Question", "mode": "chat", "provider": "openrouter"}).status_code == 200
            assert client.post("/api/v1/workspace/chat", json={"message": "Question"}).status_code == 503
            openai.assert_not_called()
        transport.close.assert_awaited_once()


@pytest.mark.parametrize("endpoint", ["ask", "retrieve"])
@pytest.mark.parametrize("providers", [("production", False), ("production", True), ("test", True)], indirect=True)
def test_raw_rag_access_guards_remain_with_configured_services(providers, endpoint):
    client, services = providers
    with patch.object(services["openai"], "retrieve", new_callable=AsyncMock) as retrieve:
        result = client.post(f"/api/v1/rag/{endpoint}", json={"question": "Question"})
        assert result.status_code == 403
        retrieve.assert_not_awaited()
    for service in services.values():
        service.ask.assert_not_awaited()
        service.client.post.assert_not_awaited()


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
    services["openrouter"].client.post.return_value = llama_essay(content="Unsupported claim [S999]")
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
    selected.client.post.side_effect = [llama_essay(content="Unsupported claim. [S999]"), llama_essay()]
    result = client.post("/api/v1/workspace/chat", json={"message": "Essay", "mode": "essay", "provider": "openrouter"})
    assert result.status_code == 200
    assert selected.client.post.await_count == 2
    assert all(call.args[0] == "chat/completions" for call in selected.client.post.await_args_list)
    assert selected.client.post.call_args.args[1]['messages'][3]['role'] == 'assistant'
    assert 'complete corrected title and sections' in selected.client.post.call_args.args[1]['messages'][4]['content']
    services["openai"].client.post.assert_not_awaited()


def test_valid_llama_essay_missing_bullets_is_formatted_without_regeneration(providers):
    client, services = providers
    selected = services['openrouter']
    selected.client.post.return_value = llama_essay(content='Measure activation before investing in acquisition. [S1]')
    result = client.post('/api/v1/workspace/chat', json={'message': 'Write a short essay on growth', 'mode': 'essay', 'provider': 'openrouter'})
    assert result.status_code == 200
    content = result.json()['artifact']['content']
    assert '## Key takeaways' in content and '- **Growth step 1** [S1]' in content
    assert 'Measure activation before investing in acquisition.' in content
    assert selected.client.post.await_count == 1
    services['openai'].client.post.assert_not_awaited()


@pytest.mark.parametrize('provider', ['openai', 'openrouter'])
def test_conversation_recall_uses_older_messages_without_archive_lookup(providers, provider):
    client, services = providers
    selected = services[provider]
    reply = json.dumps({'message': 'You called your app Orbit Garden.'})
    selected.client.post.side_effect = [routed(provider, 'podcast-qa', False),
        {'choices': [{'finish_reason': 'stop', 'message': {'content': reply}}]} if provider == 'openrouter' else
        {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': reply}]}]}]
    history = [{'role': 'user', 'content': 'My app is Orbit Garden.'},
               {'role': 'assistant', 'content': 'We can discuss Orbit Garden.'}]
    history += [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'Other message {i}'} for i in range(30)]
    result = client.post('/api/v1/workspace/chat', json={'provider': provider,
        'message': 'What name did I give my app?', 'history': history})
    assert result.status_code == 200
    assert 'Orbit Garden' in result.json()['message']
    selected.ask.assert_not_awaited()
    other = services['openai' if provider == 'openrouter' else 'openrouter']
    other.client.post.assert_not_awaited()
    payload = selected.client.post.call_args.args[1]
    data = json.loads(payload['messages'][1]['content'] if provider == 'openrouter' else payload['input'])
    assert 'Orbit Garden' in json.dumps(data['history'])


def test_llama_conclusion_can_recap_cited_sections_without_new_attribution(providers):
    client, services = providers
    output = {'title': 'Growth', 'sections': [
        {'heading': 'Reach value', 'content': '**Measure activation.**\n\n- Improve onboarding.', 'source_ids': ['S1']},
        {'heading': 'Conclusion', 'content': 'Focus on delivering value before expanding acquisition.', 'source_ids': []}]}
    services['openrouter'].client.post.return_value = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(output)}}]}
    result = client.post('/api/v1/workspace/chat', json={'message': 'Write an essay', 'mode': 'essay', 'provider': 'openrouter'})
    assert result.status_code == 200
    assert '**Synthesis:**' in result.json()['artifact']['content']


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
@pytest.mark.parametrize("providers", [("test", False), ("production", True)], indirect=True)
@pytest.mark.parametrize("skill,question", [
    ("podcast-qa", "How can I improve activation?"),
    ("ship30-essay", "Write an essay about activation."),
    ("ship30-essay", "Give me something about activation in ship30for30 style."),
    ("simple-artifact", "Build an HTML growth calculator."),
])
def test_automatic_skill_selection_dispatches_using_selected_provider(providers, provider, skill, question):
    client, services = providers
    selected = services[provider]
    calls = [routed(provider, skill, needs_evidence=skill != "simple-artifact")]
    if skill != "podcast-qa":
        calls.append((llama_essay() if provider == "openrouter" else generated()) if skill == "ship30-essay"
                     else (chat_generated if provider == "openrouter" else generated)("html", "<button>Try it</button>"))
    selected.client.post.side_effect = calls
    result = client.post("/api/v1/workspace/chat", json={"message": question, "provider": provider})
    assert result.status_code == 200
    body = result.json()
    assert body["skill"] == skill
    assert body["provider"] == provider
    assert body["model"] == selected.generator.model
    assert selected.client.post.await_count == (1 if skill == "podcast-qa" else 2)
    if skill == "simple-artifact":
        assert body["artifact"]["language"] == "html"
        assert body["sources"] == {}
        selected.ask.assert_not_awaited()
    else:
        selected.ask.assert_awaited_once_with(question)
        assert body["sources"]["S1"]["title"] == "Growth discussion"
        if skill == "ship30-essay":
            assert body["artifact"]["language"] == "markdown"
            assert body["message"] == "Your essay is ready."
        else:
            assert body["artifact"] is None
    assert all(call.args[1]["model"] == selected.generator.model for call in selected.client.post.await_args_list)
    other = services["openrouter" if provider == "openai" else "openai"]
    other.ask.assert_not_awaited()
    other.client.post.assert_not_awaited()


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_model_reconsiders_skill_for_followups_and_task_switches(providers, provider):
    client, services = providers
    selected = services[provider]
    history = []
    for question, skill, artifact in [
        ("How can I improve activation?", "podcast-qa", None),
        ("Turn this into an essay.", "ship30-essay", ("markdown", None)),
        ("Build a small calculator instead.", "simple-artifact", ("html", "<h1>Calculator</h1>")),
        ("Add a reset button.", "simple-artifact", ("html", "<button>Reset</button>")),
        ("What does Elena Verna say about retention?", "podcast-qa", None),
    ]:
        calls = [routed(provider, skill, needs_evidence=skill != "simple-artifact")]
        if artifact:
            calls.append(llama_essay() if provider == "openrouter" and skill == "ship30-essay"
                         else (chat_generated if provider == "openrouter" else generated)(*artifact))
        selected.client.post.side_effect = calls
        result = client.post("/api/v1/workspace/chat", json={"message": question, "provider": provider,
                                                           "history": history})
        assert result.status_code == 200
        data = result.json()
        assert data["skill"] == skill
        call = selected.client.post.await_args_list[-len(calls)]
        routing_data = json.loads(call.args[1]["messages"][1]["content"] if provider == "openrouter"
                                  else call.args[1]["input"])
        assert routing_data["message"] == question
        assert len(routing_data["history"]) == len(history)
        history.extend([{"role": "user", "content": question},
                        {"role": "assistant", "skill": skill, "content": data["message"] +
                         ("\n\n" + data["artifact"]["content"] if data["artifact"] else "")}])


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_podcast_based_artifact_retrieves_and_validates_evidence(providers, provider):
    client, services = providers
    selected = services[provider]
    selected.client.post.side_effect = [routed(provider, "simple-artifact"),
        (chat_generated if provider == "openrouter" else generated)("markdown", "# Checklist\n\nMeasure activation. [S1]")]
    result = client.post("/api/v1/workspace/chat", json={"message": "Create a checklist from Elena Verna's advice.",
                                                       "provider": provider})
    assert result.status_code == 200
    assert result.json()["sources"]["S1"]["title"] == "Growth discussion"
    selected.ask.assert_awaited_once()
    payload = selected.client.post.call_args.args[1]
    data = json.loads(payload["messages"][1]["content"] if provider == "openrouter" else payload["input"])
    assert data["evidence"][0]["id"] == "S1"
    assert "verified_answer" in data


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
@pytest.mark.parametrize("content", ["No source citation", "A claim [S999]", "A claim [S1, S999]"])
def test_routed_artifact_cannot_invent_or_drop_citations(providers, provider, content):
    client, services = providers
    services[provider].client.post.side_effect = [routed(provider, "simple-artifact"),
        (chat_generated if provider == "openrouter" else generated)("markdown", content)]
    result = client.post("/api/v1/workspace/chat", json={"message": "Make a podcast-based checklist.", "provider": provider})
    assert result.status_code == 502
    assert "source validation" in result.json()["detail"]


@pytest.mark.parametrize("skill", ["ship30-essay", "simple-artifact"])
def test_routed_unsupported_requests_do_not_generate_artifacts(providers, skill):
    client, services = providers
    selected = services["openai"]
    answer = grounded(selected.generator.model).model_copy(update={"sources": {}, "answer": GroundedAnswer(
        coverage="unsupported", insufficient_evidence=True, summary="No evidence.", summary_citation_ids=[],
        sections=[], missing_topics=["unknown"])})
    selected.ask.return_value = answer
    selected.client.post.return_value = routed("openai", skill)
    result = client.post("/api/v1/workspace/chat", json={"message": "Create it using unsupported podcast facts."})
    assert result.status_code == 200
    assert result.json()["coverage"] == "unsupported"
    assert result.json()["artifact"] is None
    assert selected.client.post.await_count == 1


def test_qa_cannot_skip_grounding_when_router_returns_false(providers):
    client, services = providers
    services["openai"].client.post.return_value = routed("openai", "podcast-qa", False)
    result = client.post("/api/v1/workspace/chat", json={"message": "Question"})
    assert result.status_code == 200
    services["openai"].ask.assert_awaited_once()


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_invalid_routing_stops_before_retrieval_and_generation(providers, provider):
    client, services = providers
    selected = services[provider]
    selected.client.post.return_value = {"private": "payload"}
    result = client.post("/api/v1/workspace/chat", json={"message": "Question", "provider": provider})
    assert result.status_code == 502
    assert "private" not in result.text
    assert selected.client.post.await_count == 1
    selected.ask.assert_not_awaited()


def test_api_documents_automatic_default_and_skill_history(providers):
    client, _ = providers
    components = client.get("/openapi.json").json()["components"]["schemas"]
    mode = components["WorkspaceRequest"]["properties"]["mode"]
    assert mode["default"] == "auto"
    assert mode["enum"] == ["auto", "chat", "essay", "code"]
    assert mode["deprecated"] is True
    assert "skill" in components["Turn"]["properties"]


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
@pytest.mark.parametrize("skill", ["podcast-qa", "ship30-essay"])
@pytest.mark.parametrize("structured", [False, True])
def test_questions_and_essays_after_large_artifacts_fit_retrieval_limit(providers, provider, skill, structured):
    client, services = providers
    selected = services[provider]
    response = grounded(selected.generator.model)

    async def retrieve(question):
        # Enforce the real retrievers' contract at this boundary; the previous
        # implementation raised ValueError and returned HTTP 500 here.
        if not question.strip() or len(question) > 12000:
            raise ValueError("Retrieval question exceeds 12000 characters")
        assert question.endswith("Explain product growth.")
        return response

    selected.ask.side_effect = retrieve
    selected.client.post.side_effect = [routed(provider, skill)] + (
        [(llama_essay if provider == "openrouter" else generated)()] if skill == "ship30-essay" else [])
    history = []
    for index in range(6):
        turn = {"role": "assistant", "skill": "ship30-essay", "content": "Essay " + str(index)}
        if structured:
            turn["artifact"] = {"title": "Product growth", "language": "markdown", "content": "Growth " * 16000}
        else:
            turn["content"] = ("Growth " * 3000)[:16000]
        history.extend([{"role": "user", "content": "Write an essay about growth."}, turn])
    result = client.post("/api/v1/workspace/chat", json={"message": "Explain product growth.",
                                                       "provider": provider, "history": history})
    assert result.status_code == 200
    selected.ask.assert_awaited_once()
    assert "Growth" in selected.ask.call_args.args[0]


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_code_edits_keep_complete_source_and_router_receives_only_metadata(providers, provider):
    client, services = providers
    selected = services[provider]
    source = "<!doctype html><p>" + "x" * 20000 + "</p><script>const completeSource = true;</script>"
    selected.client.post.side_effect = [routed(provider, "simple-artifact", False),
        (chat_generated if provider == "openrouter" else generated)("html", "<button>Clear</button>")]
    result = client.post("/api/v1/workspace/chat", json={"message": "Add a Clear button.", "provider": provider,
        "history": [{"role": "assistant", "skill": "simple-artifact", "content": "Calculator ready.",
                     "artifact": {"title": "Calculator", "language": "html", "content": source}}]})
    assert result.status_code == 200
    payloads = [call.args[1] for call in selected.client.post.await_args_list]
    data = [json.loads(p["messages"][1]["content"] if provider == "openrouter" else p["input"]) for p in payloads]
    assert data[0]["history"][0]["artifact"] == {"title": "Calculator", "language": "html"}
    assert data[1]["history"][0]["artifact"]["content"] == source
    selected.ask.assert_not_awaited()


def test_full_length_current_question_is_never_truncated_for_history(providers):
    client, services = providers
    selected = services["openai"]
    selected.client.post.return_value = routed("openai", "podcast-qa")
    message = "Growth? " + "é" * (12000 - len("Growth? "))
    result = client.post("/api/v1/workspace/chat", json={"message": message,
        "history": [{"role": "assistant", "content": "Old essay " * 1500}]})
    assert result.status_code == 200
    selected.ask.assert_awaited_once_with(message)


@pytest.mark.parametrize("payload", [None, [], {"status": "completed", "output": [None]}])
def test_malformed_openai_artifacts_return_retryable_error(providers, payload):
    client, services = providers
    services["openai"].client.post.return_value = payload
    result = client.post("/api/v1/workspace/chat", json={"message": "Build a calculator", "mode": "code"})
    assert result.status_code == 502


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
@pytest.mark.parametrize("broken", [
    '<button onclick="eval(\'2+3\')">Calculate</button>',
    '<script>const calculate = new Function("return 2+3");</script>',
    '<script>localStorage.setItem("answer", "5");</script>',
    '<script src="https://example.com/calculator.js"></script>',
    '<script>const unfinished = true;',
])
def test_preview_incompatible_code_is_repaired_once(providers, provider, broken):
    client, services = providers
    selected = services[provider]
    build = chat_generated if provider == "openrouter" else generated
    selected.client.post.side_effect = [routed(provider, "simple-artifact", False),
                                       build("html", broken), build("html", "<button>5</button>")]
    result = client.post("/api/v1/workspace/chat", json={"message": "Build a calculator", "provider": provider})
    assert result.status_code == 200
    assert selected.client.post.await_count == 3
    payload = selected.client.post.call_args.args[1]
    data = json.loads(payload["messages"][1]["content"] if provider == "openrouter" else payload["input"])
    assert data["draft"]["content"] == broken
    assert result.json()["artifact"]["content"] == "<button>5</button>"
    selected.ask.assert_not_awaited()


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_unrepaired_preview_incompatible_code_returns_safe_error(providers, provider):
    client, services = providers
    selected = services[provider]
    build = chat_generated if provider == "openrouter" else generated
    broken = build("html", '<script>eval("2+3");</script>')
    selected.client.post.side_effect = [routed(provider, "simple-artifact", False), broken, broken]
    result = client.post("/api/v1/workspace/chat", json={"message": "Build a calculator", "provider": provider})
    assert result.status_code == 502
    assert selected.client.post.await_count == 3
    assert result.json()["detail"] == "The code could not run in the preview. Please retry your request."


def test_openrouter_completed_invalid_json_has_one_format_repair(providers):
    client, services = providers
    selected = services["openrouter"]
    selected.client.post.side_effect = [{"choices": [{"finish_reason": "stop", "message": {"content": "{invalid json"}}]},
                                       chat_generated("html", "<button>5</button>")]
    result = client.post("/api/v1/workspace/chat", json={"message": "Build a calculator", "mode": "code", "provider": "openrouter"})
    assert result.status_code == 200
    assert selected.client.post.await_count == 2
    payload = selected.client.post.call_args.args[1]
    assert payload["temperature"] == 0
    assert json.loads(payload["messages"][1]["content"])["invalid_draft"] == "{invalid json"


def test_openrouter_refusal_is_not_retried(providers):
    client, services = providers
    selected = services["openrouter"]
    selected.client.post.return_value = {"choices": [{"finish_reason": "stop", "message": {"refusal": "Refused"}}]}
    result = client.post("/api/v1/workspace/chat", json={"message": "Create it", "mode": "code", "provider": "openrouter"})
    assert result.status_code == 502
    assert selected.client.post.await_count == 1


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_essay_missing_citations_gets_one_evidence_based_revision(providers, provider):
    client, services = providers
    selected = services[provider]
    build = llama_essay if provider == "openrouter" else generated
    selected.client.post.side_effect = [build(content="# Product growth\n\nA draft missing citations."), build()]
    result = client.post("/api/v1/workspace/chat", json={"message": "Write an essay on product growth.", "mode": "essay", "provider": provider})
    assert result.status_code == 200
    assert selected.client.post.await_count == 2
    payload = selected.client.post.call_args.args[1]
    instructions = payload["messages"][0]["content"] if provider == "openrouter" else payload["instructions"]
    assert "allowed IDs: S1" in instructions
    assert "[S1]" in result.json()["artifact"]["content"]


def test_switching_models_in_one_conversation_uses_new_provider_each_turn(providers):
    client, services = providers
    history = []
    for provider in ("openai", "openrouter", "openai"):
        selected = services[provider]
        before = {name: service.ask.await_count for name, service in services.items()}
        selected.ask.return_value.answer.summary = provider + " answer"
        selected.client.post.return_value = routed(provider, "podcast-qa")
        result = client.post("/api/v1/workspace/chat", json={"provider": provider, "message": "Explain product growth.", "history": history})
        assert result.status_code == 200
        body = result.json()
        assert body["message"].startswith(provider + " answer")
        assert body["provider"] == provider
        assert body["model"] == selected.generator.model
        assert selected.ask.await_count == before[provider] + 1
        other = "openrouter" if provider == "openai" else "openai"
        assert services[other].ask.await_count == before[other]
        history.extend([{"role": "user", "content": "Explain product growth."},
                        {"role": "assistant", "content": body["message"], "skill": body["skill"]}])
