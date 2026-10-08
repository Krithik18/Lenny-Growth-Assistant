import asyncio
import json
from types import SimpleNamespace

import pytest

from app.llm.openrouter_provider import OpenRouterAnswerProvider, ProviderError
from test_openrouter_provider import approval, mock_client, response, stage


SOURCES = {
    "S1": SimpleNamespace(guest="Deb Liu", text="Product growth helps people reach and use a product's value. Growth work improves how people find and experience that value."),
    "S2": SimpleNamespace(guest="Fareed Mosavat", text="Growth work connects more customers to experiences the product already offers. Teams measure whether changes improve engagement."),
}
EXPLANATION = "Product growth means helping more people find and use a product's value. Teams improve how customers reach that value and measure whether the changes improve engagement."


def test_simple_growth_explanation_skips_planning_but_requires_grounding_review():
    client = mock_client(written={"answers": [EXPLANATION]})
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("explain about product growth", SOURCES))
    assert [stage(c.args[1]) for c in client.post.await_args_list] == ["written_answers", "answer_review"]
    assert answer.coverage == "complete" and answer.missing_topics == []
    assert answer.summary.startswith("Product growth means")
    assert answer.sections[0].content == EXPLANATION
    assert set(answer.sections[0].citation_ids) == {"S1", "S2"}
    writer_data = json.loads(client.post.await_args_list[0].args[1]["messages"][1]["content"])
    assert writer_data["answer_style"] == "introductory_explanation"
    assert len(writer_data["requirements"]) == 1


def test_introductory_answer_cannot_publish_unsupported_claims_without_repair():
    writes = iter([response({"answers": ["Growth guarantees every customer will stay forever."]}),
                   response({"answers": [EXPLANATION]})])
    reviews = iter([response({"checks": [{"part_index": 0, "verdict": "rejected",
        "issue": "Neither S1:E1 nor S2:E1 supports a guarantee that customers stay forever."}], "missing_requests": []}),
                    response(approval())])
    client = mock_client(written=lambda p: next(writes), review=lambda p: next(reviews))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("explain product growth", SOURCES))
    assert "guarantees" not in answer.summary
    assert [stage(c.args[1]) for c in client.post.await_args_list] == [
        "written_answers", "answer_review", "written_answers", "answer_review"]


def test_introductory_missing_supported_request_reverts_to_complete_planning():
    requests = {"parts": [
        {"topic": "Product growth meaning", "evidence": ["S1:E1", "S2:E1"]},
        {"topic": "Measuring growth improvements", "evidence": ["S2:E2"]},
    ]}
    writes = iter([response({"answers": ["Growth connects more customers to existing experiences."]}),
                   response({"answers": [EXPLANATION, "Teams measure whether changes improve engagement."]})])
    reviews = iter([response({**approval(), "missing_requests": [requests["parts"][1]]}), response(approval(2))])
    client = mock_client(requirements=requests, written=lambda p: next(writes), review=lambda p: next(reviews))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("explain about product growth", SOURCES))
    assert [stage(c.args[1]) for c in client.post.await_args_list] == [
        "written_answers", "answer_review", "answer_requirements", "written_answers", "answer_review"]
    assert answer.coverage == "complete" and len(answer.sections) == 2


def test_introductory_review_receives_all_whole_selected_sources_once():
    sources = {f"S{i}": SimpleNamespace(guest="Deb Liu", text=f"Product growth makes it easier for customer group {i} to find value. Keep this context together.")
               for i in range(1, 8)}
    client = mock_client(written={"answers": [EXPLANATION]})
    asyncio.run(OpenRouterAnswerProvider(client).answer("explain product growth", sources))
    review = json.loads(client.post.await_args_list[-1].args[1]["messages"][1]["content"])
    assert [s["id"] for s in review["evidence"]] == ["S1", "S2", "S3", "S4"]
    for source in review["evidence"]:
        assert " ".join(e["text"] for e in source["excerpts"]) == sources[source["id"]].text
    assert review["section_support"][0]["source_ids"] == ["S1", "S2", "S3", "S4"]


def test_introductory_outage_does_not_turn_unreviewed_text_into_complete_answer():
    client = mock_client(written={"answers": [EXPLANATION]})
    original = client.post.side_effect
    async def post(path, payload):
        if stage(payload) == "answer_review":
            raise ProviderError("Unavailable")
        return await original(path, payload)
    client.post.side_effect = post
    with pytest.raises(ProviderError):
        asyncio.run(OpenRouterAnswerProvider(client).answer("explain product growth", SOURCES))
