import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.api.routes.workspace import get_workspace_rag
from app.schemas.answer import AnswerResult, GroundedAnswer, AnswerSection
from app.schemas.retrieval import RetrievedPassage


def generated(language="markdown", content=None):
    if content is None:
        content = '# A useful idea\n\n**Start small.** [S1]\n\n- Measure activation.\n- Inspect the first experience.\n- Review the evidence.\n\n' + ('A grounded explanation of the first experience. ' * 165)
    return {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps({"message": "Your artifact is ready.",
          "artifact": {"title": "A useful idea", "language": language, "content": content}})}]}]}


@pytest.fixture
def workspace():
    source = RetrievedPassage(chunk_id=uuid4(), episode_id=uuid4(), episode_revision_id=uuid4(),
        title="Growth discussion", guest="Guest", source_url=None, archive_member="test", archive_sha256="test",
        text="Measure activation before investing in acquisition.", start_char=0, end_char=50,
        start_seconds=0, end_seconds=10, similarity=.8)
    result = AnswerResult(question="growth", model="test", answer=GroundedAnswer(coverage="complete",
        insufficient_evidence=False, summary="Measure activation.", summary_citation_ids=["S1"],
        sections=[AnswerSection(heading="Start here", content="Measure activation first.", citation_ids=["S1"])], missing_topics=[]),
        sources={"S1": source})
    service = SimpleNamespace(ask=AsyncMock(return_value=result),
        client=SimpleNamespace(post=AsyncMock(return_value=generated())), generator=SimpleNamespace(model="test"))
    app=create_app(Settings(_env_file=None,database_url="",openai_api_key=""))
    app.dependency_overrides[get_workspace_rag]=lambda:service
    with TestClient(app) as client:
        yield client, service


def test_chat_preserves_sources_without_extra_generation(workspace):
    client, service=workspace
    result=client.post('/api/v1/workspace/chat',json={"message":"How to grow?"})
    assert result.status_code==200
    assert '[S1]' in result.json()['message']
    assert result.json()['sources']['S1']['title']=='Growth discussion'
    assert result.json()['artifact'] is None
    service.client.post.assert_not_called()


def test_essay_skill_loaded_and_cited_artifact_returned(workspace):
    client, service=workspace
    result=client.post('/api/v1/workspace/chat',json={"message":"Write about growth", "mode":"essay"})
    assert result.status_code==200
    assert result.json()['artifact']['language']=='markdown'
    payload=service.client.post.call_args.args[1]
    assert '1,250' in payload['instructions']
    assert 'verified_answer' in json.loads(payload['input'])


def test_essay_rejects_invented_citations(workspace):
    client, service=workspace
    service.client.post.return_value=generated(content='Unsupported claim [S999]')
    assert client.post('/api/v1/workspace/chat',json={"message":"Essay", "mode":"essay"}).status_code==502


def test_essay_revises_missing_format_once(workspace):
    client, service=workspace
    service.client.post.side_effect=[generated(content='A short answer. [S1]'),generated()]
    response=client.post('/api/v1/workspace/chat',json={"message":"Essay", "mode":"essay"})
    assert response.status_code==200
    assert service.client.post.call_count==2
    assert 'draft' in json.loads(service.client.post.call_args.args[1]['input'])


def test_essay_approximate_length_does_not_leak_internal_status(workspace):
    client, service=workspace
    content='# Activation\n\n**Start here.** [S1]\n\n- First step\n- Second step\n- Third step\n\n'
    content+=' '.join(['Explanation']*(1405-len(content.split())))
    assert len(content.split())==1405
    response=generated(content=content)
    payload=json.loads(response['output'][0]['content'][0]['text'])
    payload['message']='Complete Markdown essay synthesizing the supplied evidence, with limitations and practical applications clearly distinguished.'
    response['output'][0]['content'][0]['text']=json.dumps(payload)
    service.client.post.return_value=response
    result=client.post('/api/v1/workspace/chat',json={'message':'Write an essay about activation','mode':'essay'})
    assert result.status_code==200
    assert result.json()['message']=='Your essay is ready.'
    assert result.json()['artifact']['content']==content
    assert service.client.post.call_count==1


def test_grouped_invented_citation_is_rejected(workspace):
    client, service=workspace
    service.client.post.return_value=generated(content='A claim [S1, S999]. Another [S1].')
    assert client.post('/api/v1/workspace/chat',json={"message":"Essay", "mode":"essay"}).status_code==502


def test_create_does_not_spend_retrieval_calls_and_passes_history(workspace):
    client, service=workspace
    service.client.post.return_value=generated('html','<button>Try it</button>')
    result=client.post('/api/v1/workspace/chat',json={"message":"Make it green", "mode":"code",
        "history":[{"role":"assistant","content":"A small calculator"}]})
    assert result.status_code==200
    assert result.json()['artifact']['language']=='html'
    assert result.json()['sources']=={}
    service.ask.assert_not_called()
    assert 'A small calculator' in service.client.post.call_args.args[1]['input']


@pytest.mark.parametrize('mode', ['chat', 'essay'])
def test_unsupported_question_gets_helpful_redirect(workspace, mode):
    client, service=workspace
    service.ask.return_value=AnswerResult(question='unknown',model='test',sources={},answer=GroundedAnswer(
        coverage='unsupported',insufficient_evidence=True,summary='No evidence found.',summary_citation_ids=[],sections=[],missing_topics=['unknown']))
    result=client.post('/api/v1/workspace/chat',json={"message":"unknown", "mode":mode})
    assert result.status_code==200
    assert result.json()['artifact'] is None
    assert result.json()['sources'] == {}
    assert result.json()['coverage'] == 'unsupported'
    assert "Lenny's Podcast" in result.json()['message']
    assert 'How can I improve user activation?' in result.json()['message']
    assert 'Evidence gaps' not in result.json()['message']
    assert 'unknown' not in result.json()['message']
    service.client.post.assert_not_called()


def test_invalid_requests_and_incomplete_generation(workspace):
    client, service=workspace
    assert client.post('/api/v1/workspace/chat',json={"message":" "}).status_code==422
    assert client.post('/api/v1/workspace/chat',json={"message":"Hi", "mode":"unknown"}).status_code==422
    service.client.post.return_value={"status":"incomplete"}
    assert client.post('/api/v1/workspace/chat',json={"message":"A calculator", "mode":"code"}).status_code==502


def test_workspace_respects_existing_production_and_setup_guards():
    for environment,expected in [('production',403),('test',503)]:
        app=create_app(Settings(_env_file=None,app_env=environment,database_url='',openai_api_key=''))
        with TestClient(app) as client:
            assert client.post('/api/v1/workspace/chat',json={'message':'Hello'}).status_code==expected
