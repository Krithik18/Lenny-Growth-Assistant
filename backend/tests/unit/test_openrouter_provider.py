import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.llm.client import OpenRouterClient, ProviderError
from app.llm.openrouter_provider import (
    AnswerPlan, AnswerValidationError, OpenRouterAnswerProvider, REVIEW_MODEL,
    assemble_answer, compare_percentages, evidence_excerpts, ratio_calculations, validate_answer, validate_review,
    validate_comparison_units,
    validate_written,
)

SOURCES = {
    "S1": SimpleNamespace(title="Episode", guest="Guest", text="A feature team delivers output. An empowered team solves problems."),
    "S2": SimpleNamespace(title="Other episode", text="A customer story describes actual behavior."),
}
REQ = {"parts": [{"topic": "Teams", "evidence": ["S1:E1", "S1:E2"]}]}
WRITTEN = {"answers": ["A feature team delivers output; an empowered team solves problems."]}


def response(content, finish_reason="stop"):
    return {"choices": [{"finish_reason": finish_reason, "message": {"content": json.dumps(content)}}]}


def approval(count=1, unavailable=()):
    return {"checks": [{"part_index": i, "verdict": "approved", "issue": ""} for i in range(count)], "missing_requests": []}


def stage(payload):
    if payload["model"] == OpenRouterAnswerProvider.model:
        return "written_answers"
    return payload["response_format"]["json_schema"]["name"]


def mock_client(requirements=REQ, written=WRITTEN, review=None):
    handlers = {"answer_requirements": requirements, "written_answers": written, "answer_review": review}
    async def post(path, payload):
        assert path == "chat/completions"
        value = handlers[stage(payload)]
        if value is None:
            parts = json.loads(payload["messages"][1]["content"])["draft"]["parts"]
            value = approval(len(parts), [i for i, p in enumerate(parts) if not p["evidence"]])
        if callable(value):
            return value(payload)
        return response(value)
    return SimpleNamespace(post=AsyncMock(side_effect=post))


@pytest.mark.parametrize("missing", [False, True])
def test_request_and_grounded_contract(missing):
    req = copy.deepcopy(REQ)
    if missing:
        req["parts"].append({"topic": "Weather", "evidence": []})
    requests = []
    def handler(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer fake"
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert payload["provider"]["require_parameters"] is True
        assert payload["structured_outputs"] is True
        if payload["model"] == REVIEW_MODEL:
            assert payload["reasoning"] == {"enabled": False}
            assert payload["provider"]["order"] == ["deepinfra"]
            assert payload["provider"]["allow_fallbacks"] is True
        if stage(payload) == "answer_requirements":
            assert payload["model"] == REVIEW_MODEL
            data = json.loads(payload["messages"][1]["content"])
            assert data["question"] == "Question" and len(data["evidence"]) == 2
            assert data["evidence"][0]["guest"] == "Guest"
            assert "title" not in data["evidence"][0]
            return httpx.Response(200, json=response(req))
        if stage(payload) == "written_answers":
            assert payload["model"] == OpenRouterAnswerProvider.model
            assert payload["structured_outputs"] is True
            assert payload["provider"] == {"require_parameters": True, "only": ["coreweave"], "allow_fallbacks": False}
            assert payload["temperature"] == .1 and payload["repetition_penalty"] == 1.05
            data = json.loads(payload["messages"][1]["content"])
            assert len(data["requirements"]) == 1
            assert data["requirements"][0]["topic"] == REQ["parts"][0]["topic"]
            assert [e["text"] for e in data["requirements"][0]["evidence"]] == ["A feature team delivers output.", "An empowered team solves problems."]
            assert all("id" not in e for e in data["requirements"][0]["evidence"])
            assert "evidence" not in data  # No unrelated original passages in the writer input.
            return httpx.Response(200, json=response(WRITTEN))
        assert payload["model"] == REVIEW_MODEL
        data = json.loads(payload["messages"][1]["content"])
        assert len(data["draft"]["parts"]) == len(req["parts"])
        assert len(data["evidence"]) == 2  # Review sees all evidence, including gaps.
        return httpx.Response(200, json=response(approval(len(req["parts"]), [i for i,p in enumerate(req["parts"]) if not p["evidence"]])))
    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(handler))
        try:
            answer = await OpenRouterAnswerProvider(client).answer("Question", SOURCES)
            assert answer.coverage == ("partial" if missing else "complete")
            assert answer.insufficient_evidence == missing
            assert answer.missing_topics == (["Weather"] if missing else [])
            assert answer.summary == answer.sections[0].content == WRITTEN["answers"][0]
            assert answer.summary_citation_ids == ["S1"]
            assert validate_answer(response(answer.model_dump()), SOURCES) == answer
        finally:
            await client.close()
    asyncio.run(check())
    assert [stage(p) for p in requests] == ["answer_requirements", "written_answers", "answer_review"]


def test_no_sources_skips_every_model():
    client = mock_client()
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Question", {}))
    assert answer.coverage == "unsupported" and answer.missing_topics == ["Question"]
    client.post.assert_not_awaited()


def test_irrelevant_sources_skip_llama_but_still_check_gap():
    client = mock_client(requirements={"parts": [{"topic": "Weather", "evidence": []}]})
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Weather", SOURCES))
    assert answer.coverage == "unsupported" and answer.sections == []
    assert [stage(c.args[1]) for c in client.post.await_args_list] == ["answer_requirements", "answer_review"]


def test_excerpt_selection_preserves_text_and_speaker_order():
    source = SimpleNamespace(text='Guest (00:01):\nAdvice.\n\nHost (00:02):\nA question?')
    assert evidence_excerpts({"S1": source}) == {
        "S1:E1": ("S1", 'Guest (00:01):\nAdvice.'), "S1:E2": ("S1", 'Host (00:02):\nA question?')}


def test_adjacent_speaker_turns_keep_their_own_identity_without_blank_lines():
    from app.llm.openrouter_provider import source_excerpts
    text = "Jane Doe (00:10):\nJane advice.\nJohn Smith (00:12):\nJohn advice."
    items = source_excerpts({"S1": SimpleNamespace(text=text)})["S1"]
    assert [item["speaker"] for item in items] == ["Jane Doe", "John Smith"]
    assert [item["text"] for item in items] == ["Jane Doe (00:10):\nJane advice.", "John Smith (00:12):\nJohn advice."]


@pytest.mark.parametrize("separator", ["\n", "\n\n"])
def test_timestamp_only_continuation_does_not_create_a_speaker_from_previous_sentence(separator):
    from app.llm.openrouter_provider import source_excerpts
    text = f"Jane Doe (00:10):\nHer first point.{separator}(00:12):\nHer second point."
    items = source_excerpts({"S1": SimpleNamespace(text=text)})["S1"]
    assert len(items) == 2 and [item["speaker"] for item in items] == ["Jane Doe", "Jane Doe"]
    assert items[1]["text"] == "(00:12):\nHer second point."


@pytest.mark.parametrize("req", [
    {"parts": []}, {"parts": [{"topic": " ", "evidence": []}]},
    {"parts": [{"topic": "Teams", "evidence": ["S1:E99"]}]},
    {"parts": [{"topic": "Teams", "evidence": ["invented:E1"]}]},
    {"parts": REQ["parts"] * 2}, {"parts": REQ["parts"], "extra": "private payload"},
])
def test_invalid_requirements_do_not_reach_writer(req):
    client = mock_client(requirements=req)
    with pytest.raises(ProviderError):
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert client.post.await_count == 2
    assert all(stage(c.args[1]) == "answer_requirements" for c in client.post.await_args_list)


@pytest.mark.parametrize("written", [
    {}, {"answers": []}, {"answers": [""]},
    {"answers": [False]}, {"answers": ["private payload"], "extra": "bad"},
])
def test_invalid_writer_output_does_not_reach_review(written):
    client = mock_client(written=written)
    with pytest.raises(ProviderError):
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert client.post.await_count == 3
    assert all(stage(c.args[1]) != "answer_review" for c in client.post.await_args_list)


@pytest.mark.parametrize("written", [
    {"answer": ["A feature team delivers output.", "An empowered team solves problems."]},
    {"answers": ["A feature team delivers output.", "An empowered team solves problems."]},
    ["A feature team delivers output.", "An empowered team solves problems."],
])
def test_single_requirement_string_bullets_are_only_repackaged_then_reviewed(written):
    client = mock_client(written=written)
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Compare teams", SOURCES))
    assert answer.sections[0].content == "A feature team delivers output.\nAn empowered team solves problems."
    assert stage(client.post.await_args_list[-1].args[1]) == "answer_review"


@pytest.mark.parametrize("written", [WRITTEN["answers"][0], {"answer": WRITTEN["answers"][0]},
                                      {"answers": WRITTEN["answers"][0]}])
def test_single_string_wrapper_preserves_text_and_still_requires_review(written):
    client = mock_client(written=written)
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Compare teams", SOURCES))
    assert answer.sections[0].content == WRITTEN["answers"][0]
    assert client.post.await_count == 3
    assert stage(client.post.await_args_list[-1].args[1]) == "answer_review"


def test_fenced_json_is_unwrapped_but_truncated_or_surrounding_prose_is_rejected():
    result = response(WRITTEN)
    result["choices"][0]["message"]["content"] = "```json\n" + json.dumps(WRITTEN) + "\n```"
    assert validate_written(result, 1).answers == WRITTEN["answers"]
    result["choices"][0]["finish_reason"] = "length"
    with pytest.raises(AnswerValidationError):
        validate_written(result, 1)
    result["choices"][0]["finish_reason"] = "stop"
    result["choices"][0]["message"]["content"] += "\nExtra claim outside JSON."
    with pytest.raises(ValueError):
        validate_written(result, 1)


def test_repair_writes_only_failed_part_and_reviews_entire_answer_again():
    req = {"parts": [REQ["parts"][0], {"topic": "Stories", "evidence": ["S2:E1"]}]}
    writings = iter([response({"answers": [WRITTEN["answers"][0], "Stories predict the future."]}),
                     response({"answers": ["A customer story describes actual behavior."]})])
    reviews = iter([response({"checks": [approval()["checks"][0],
        {"part_index": 1, "verdict": "rejected", "issue": "S2:E1 describes actual behavior, not predictions."}],
        "missing_requests": []}), response(approval(2))])
    client = mock_client(requirements=req, written=lambda p: next(writings), review=lambda p: next(reviews))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Compare teams and stories", SOURCES))
    writers = [c.args[1] for c in client.post.await_args_list if stage(c.args[1]) == "written_answers"]
    assert len(json.loads(writers[0]["messages"][1]["content"])["requirements"]) == 2
    assert [p["topic"] for p in json.loads(writers[1]["messages"][1]["content"])["requirements"]] == ["Stories"]
    final_review = json.loads(client.post.await_args_list[-1].args[1]["messages"][1]["content"])
    assert len(final_review["draft"]["parts"]) == 2
    assert final_review["draft"]["parts"][0]["content"] == WRITTEN["answers"][0]
    assert answer.coverage == "complete"
    assert answer.sections[0].content == WRITTEN["answers"][0]


@pytest.mark.parametrize("written", [
    {"answer": ["A"], "extra": "B"}, {"answer": "A"}, ["A", "B"],
    {"answers": ["A"]}, {"answers": [{"topic": "A", "content": "B"}]},
])
def test_format_normalization_never_guesses_multiple_requirement_mapping(written):
    with pytest.raises((ValueError, AnswerValidationError)):
        validate_written(response(written), 2)


def test_repeated_rejections_preserve_only_explicitly_approved_parts_as_partial():
    req = {"parts": [REQ["parts"][0], {"topic": "Customer stories", "evidence": ["S2:E1"]}]}
    review = {"checks": [{"part_index": 0, "verdict": "approved", "issue": ""},
                         {"part_index": 1, "verdict": "rejected", "issue": "The claim about hypothetical future behavior contradicts actual behavior in S2:E1."}], "missing_requests": []}
    client = mock_client(requirements=req, written={"answers": [WRITTEN["answers"][0], "Stories predict hypothetical future behavior."]}, review=review)
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Teams and customer stories", SOURCES))
    assert answer.coverage == "partial" and answer.missing_topics == ["Customer stories"]
    assert len(answer.sections) == 1 and answer.sections[0].content == WRITTEN["answers"][0]
    assert answer.summary_citation_ids == ["S1"] and "hypothetical" not in answer.summary
    assert client.post.await_count == 7


def test_writer_can_only_fill_selected_requirements_and_citations():
    req = {"parts": [REQ["parts"][0], {"topic": "Other advice", "evidence": ["S2:E1"]}, {"topic": "Missing person", "evidence": []}]}
    client = mock_client(requirements=req, written={"answers": ["Team advice", "Customer story advice"]}, review=approval(3, [2]))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Compare plus missing person", SOURCES))
    assert answer.coverage == "partial" and answer.missing_topics == ["Missing person"]
    assert [s.citation_ids for s in answer.sections] == [["S1"], ["S2"]]
    assert answer.summary_citation_ids == ["S1", "S2"]
    data = json.loads(client.post.await_args_list[2].args[1]["messages"][1]["content"])
    assert [part["source_ids"] for part in data["section_support"]] == [["S1"], ["S2"], []]
    assert json.dumps(data).count(SOURCES["S2"].text) == 1


def test_grounding_rejection_regenerates_and_is_checked_again():
    writings = iter([response({"answers": ["Empowered teams only deliver output."]}), response(WRITTEN)])
    reviews = iter([response({"checks": [{"part_index": 0, "verdict": "rejected", "issue": "S1:E1 says empowered teams solve problems; don't reverse the distinction."}], "missing_requests": []}), response(approval())])
    client = mock_client(written=lambda p: next(writings), review=lambda p: next(reviews))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Compare teams", SOURCES))
    assert answer.summary == WRITTEN["answers"][0]
    assert client.post.await_count == 5
    assert "don't reverse" in client.post.await_args_list[3].args[1]["messages"][0]["content"]
    assert "S1:E1" not in json.dumps(client.post.await_args_list[3].args[1])
    assert [stage(c.args[1]) for c in client.post.await_args_list].count("answer_requirements") == 1


def test_false_gap_can_be_corrected_before_returning_answer():
    requirements = iter([response({"parts": [{"topic": "Customer stories", "evidence": []}]}),
                         response({"parts": [{"topic": "Customer stories", "evidence": ["S2:E1"]}]})])
    reviews = iter([response({"checks": [{"part_index": 0, "verdict": "rejected", "issue": "S2:E1 already answers this request."}], "missing_requests": []}), response(approval())])
    client = mock_client(requirements=lambda p: next(requirements), review=lambda p: next(reviews))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Customer stories", SOURCES))
    assert answer.coverage == "complete" and answer.sections[0].citation_ids == ["S2"]


@pytest.mark.parametrize("review", [
    {}, {"checks": [], "missing_requests": []},
    {"checks": [{"part_index": 1, "issue": ""}], "missing_requests": []},
    {"checks": approval()["checks"] * 2, "missing_requests": []},
    {"checks": [{"part_index": "0", "issue": ""}], "missing_requests": []},
    {"checks": approval()["checks"], "missing_requests": [" "]},
])
def test_review_must_account_for_every_part(review):
    client = mock_client(review=review if review else {"wrong": "field"})
    with pytest.raises(ProviderError):
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert client.post.await_count == 4


def test_review_repair_preserves_original_evidence_and_enforces_exact_check_count():
    reviews = iter([response({"checks": [{"part_index": 0, "verdict": "rejected", "issue": "rejected"}], "missing_requests": []}),
                    response(approval())])
    client = mock_client(review=lambda p: next(reviews))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert answer.coverage == "complete"
    payload = client.post.await_args_list[-1].args[1]
    assert len(payload["messages"]) == 2
    data = json.loads(payload["messages"][-1]["content"])
    assert data["question"] == "Question" and data["draft"]["parts"][0]["content"] == WRITTEN["answers"][0]
    assert data["evidence"][0]["excerpts"][0]["text"] == SOURCES["S1"].text.split(" An empowered")[0]
    schema = payload["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["checks"]["minItems"] == schema["properties"]["checks"]["maxItems"] == 1
    assert schema["$defs"]["PartCheck"]["properties"]["part_index"]["enum"] == [0]
    assert set(schema["$defs"]["Requirement"]["properties"]["evidence"]["items"]["enum"]) == set(evidence_excerpts(SOURCES))


def test_duplicate_evidence_references_do_not_repeat_passages_in_writer_input():
    req = {"parts": [{"topic": "Teams", "evidence": ["S1:E1", "S1:E1", "S1:E2"]}]}
    client = mock_client(requirements=req)
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    data = json.loads(client.post.await_args_list[1].args[1]["messages"][1]["content"])
    assert len(data["requirements"][0]["evidence"]) == 2
    assert answer.sections[0].citation_ids == ["S1"]


def test_repeated_semantic_failures_do_not_publish_unchecked_last_draft(caplog):
    client = mock_client(review={"checks": [{"part_index": 0, "verdict": "rejected", "issue": "private payload: the claim reverses the supplied evidence"}], "missing_requests": []})
    with pytest.raises(ProviderError):
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert client.post.await_count == 7
    assert "private payload" not in caplog.text


@pytest.mark.parametrize("failed_stage", ["answer_requirements", "written_answers", "answer_review"])
@pytest.mark.parametrize("failure", ["refusal", "timeout", "provider"])
def test_errors_at_every_stage_fail_closed(failed_stage, failure):
    client = mock_client()
    original = client.post.side_effect
    async def post(path, payload):
        if stage(payload) == failed_stage:
            if failure == "refusal":
                return response({}, "content_filter")
            if failure == "timeout":
                raise TimeoutError("private payload")
            raise ProviderError("Safe failure")
        return await original(path, payload)
    client.post.side_effect = post
    with pytest.raises(ProviderError) as error:
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert "private payload" not in str(error.value)
    expected = ["answer_requirements", "written_answers", "answer_review"].index(failed_stage) + 1
    assert client.post.await_count == expected + (failure == "timeout" and failed_stage != "written_answers")


@pytest.mark.parametrize("failed_stage", ["answer_requirements", "answer_review"])
def test_helper_timeout_retries_once_with_compatible_alternative_routing(failed_stage):
    client = mock_client()
    original = client.post.side_effect
    failed = False
    async def post(path, payload):
        nonlocal failed
        if stage(payload) == failed_stage and not failed:
            failed = True
            raise TimeoutError("private payload")
        return await original(path, payload)
    client.post.side_effect = post
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert answer.coverage == "complete"
    payloads = [call.args[1] for call in client.post.await_args_list if stage(call.args[1]) == failed_stage]
    assert len(payloads) == 2 and payloads[0]["provider"]["order"] == ["deepinfra"]
    assert payloads[1]["provider"] == {"require_parameters": True, "ignore": ["deepinfra"], "sort": "latency", "allow_fallbacks": True}
    assert all(payload["model"] == REVIEW_MODEL for payload in payloads)


@pytest.mark.parametrize("status", [404, 429, 502, 503, 504])
def test_temporarily_unavailable_native_writer_uses_same_model_json_fallback(status):
    client = mock_client()
    original = client.post.side_effect
    failed = False
    async def post(path, payload):
        nonlocal failed
        if stage(payload) == "written_answers" and not failed:
            failed = True
            raise ProviderError(f"OpenRouter request failed (HTTP {status}).")
        return await original(path, payload)
    client.post.side_effect = post
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert answer.coverage == "complete"
    writers = [c.args[1] for c in client.post.await_args_list if stage(c.args[1]) == "written_answers"]
    assert len(writers) == 2 and all(p["model"] == OpenRouterAnswerProvider.model for p in writers)
    assert writers[1]["response_format"] == {"type": "json_object"}
    assert "structured_outputs" not in writers[1]
    assert writers[1]["provider"] == {"require_parameters": True, "ignore": ["coreweave"], "order": ["deepinfra"], "allow_fallbacks": True}
    assert stage(client.post.await_args_list[-1].args[1]) == "answer_review"


def test_alternate_writer_is_still_rejected_if_json_or_grounding_is_invalid():
    client = mock_client(written={"answers": []})
    original = client.post.side_effect
    failed = False
    async def post(path, payload):
        nonlocal failed
        if stage(payload) == "written_answers" and not failed:
            failed = True
            raise ProviderError("OpenRouter request failed (HTTP 429).")
        return await original(path, payload)
    client.post.side_effect = post
    with pytest.raises(ProviderError):
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert client.post.await_count == 4
    assert all(stage(c.args[1]) != "answer_review" for c in client.post.await_args_list)


def test_unavailable_writer_is_skipped_until_cooldown_expires(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.llm.openrouter_provider.time.monotonic", lambda: now[0])
    client = mock_client()
    original = client.post.side_effect
    failed = False
    async def post(path, payload):
        nonlocal failed
        if stage(payload) == "written_answers" and not failed:
            failed = True
            raise ProviderError("OpenRouter request failed (HTTP 429).")
        return await original(path, payload)
    client.post.side_effect = post
    provider = OpenRouterAnswerProvider(client)
    async def check():
        for stamp in (100.0, 110.0, 161.0):
            now[0] = stamp
            assert (await provider.answer("Question", SOURCES)).coverage == "complete"
    asyncio.run(check())
    writers = [c.args[1] for c in client.post.await_args_list if stage(c.args[1]) == "written_answers"]
    assert [p["response_format"]["type"] for p in writers] == ["json_schema", "json_object", "json_object", "json_schema"]


def test_unavailable_endpoint_does_not_consume_the_validated_draft_repair():
    writes = iter([ProviderError("OpenRouter request failed (HTTP 429)."),
                   response({"answers": []}), response(WRITTEN)])
    def write(payload):
        result = next(writes)
        if isinstance(result, Exception):
            raise result
        return result
    client = mock_client(written=write)
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert answer.coverage == "complete"
    assert [stage(c.args[1]) for c in client.post.await_args_list] == ["answer_requirements", "written_answers", "written_answers", "written_answers", "answer_review"]


@pytest.mark.parametrize("failure", [429, "timeout", "invalid_json"])
def test_http_errors_are_sanitized(failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private payload", request=request)
        return httpx.Response(200, text="private payload") if failure == "invalid_json" else httpx.Response(failure, text="private payload")
    async def check():
        client = OpenRouterClient("secret-key", transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderError) as error:
                await OpenRouterAnswerProvider(client).answer("Question", SOURCES)
            assert "private payload" not in str(error.value) and "secret-key" not in str(error.value)
        finally:
            await client.close()
    asyncio.run(check())


@pytest.mark.parametrize("question,percentage", [
    ("84 very disappointed respondents out of 200", "42.00"),
    ("78 of 200 respondents", "39.00"),
    ("0 of 100 respondents", "0"),
])
def test_counts_are_calculated_without_a_model(question, percentage):
    assert ratio_calculations(question)[0]["percentage"] == percentage


def test_calculator_never_executes_expressions_or_divides_by_zero():
    assert ratio_calculations("1 of 0; __import__('os').system('bad')") == []


@pytest.mark.parametrize("count", ["84 very disappointed users", "84 users", "84 customers", "84 respondents", "84 people"])
def test_count_calculation_accepts_explicit_survey_nouns(count):
    assert ratio_calculations(count + " out of 200 responses")[0]["percentage"] == "42.00"


@pytest.mark.parametrize("count", [1, 2, 3, 10])
def test_writer_schema_enforces_actual_requirement_count(count):
    req = {"parts": [{"topic": f"Topic {i}", "evidence": ["S1:E1"]} for i in range(count)]}
    client = mock_client(requirements=req, written={"answers": ["Supported answer"] * count}, review=approval(count))
    asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    payload = client.post.await_args_list[1].args[1]
    schema = payload["response_format"]["json_schema"]["schema"]["properties"]["answers"]
    assert schema["minItems"] == schema["maxItems"] == count
    assert payload["max_tokens"] >= 400 * count


def test_complete_evidence_list_is_not_cut_at_twelve_sentences():
    texts = [f"Relevant step {i}." for i in range(1, 16)]
    source = SimpleNamespace(title="Steps", text=" ".join(texts))
    req = {"parts": [{"topic": "Steps", "evidence": [f"S1:E{i}" for i in range(1, 16)]}]}
    client = mock_client(requirements=req, written={"answers": ["The episode describes fifteen relevant steps."]})
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Describe the steps", {"S1": source}))
    schema = client.post.await_args_list[0].args[1]["response_format"]["json_schema"]["schema"]
    evidence_schema = schema["$defs"]["Requirement"]["properties"]["evidence"]
    assert set(evidence_schema["items"]["enum"]) == set(req["parts"][0]["evidence"])
    received = json.loads(client.post.await_args_list[1].args[1]["messages"][1]["content"])["requirements"][0]["evidence"]
    assert [item["text"] for item in received] == texts
    assert answer.sections[0].citation_ids == ["S1"]


def test_server_still_rejects_overlong_topics_after_native_string_limit_removal():
    client = mock_client(requirements={"parts": [{"topic": "A" * 301, "evidence": ["S1:E1"]}]})
    with pytest.raises(ProviderError):
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert client.post.await_count == 2


def test_unknown_review_verdict_cannot_approve_a_cited_claim():
    client = mock_client(review={"checks": [{"part_index": 0, "verdict": "unknown", "issue": ""}], "missing_requests": []})
    with pytest.raises(ProviderError):
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))


def test_writer_receives_only_selected_sentences():
    source = SimpleNamespace(title="Mixed", text="Recover failed cards with a marketing funnel. Ask cancellation questions during offboarding.")
    client = mock_client(requirements={"parts": [{"topic": "Failed cards", "evidence": ["S1:E1"]}]},
        written={"answers": ["Use a recovery marketing funnel."]})
    asyncio.run(OpenRouterAnswerProvider(client).answer("Failed cards", {"S1": source}))
    data = json.loads(client.post.await_args_list[1].args[1]["messages"][1]["content"])
    assert data["requirements"][0]["evidence"][0]["text"] == "Recover failed cards with a marketing funnel."
    assert "offboarding" not in json.dumps(data)


def test_writer_gets_guest_metadata_without_inventing_a_speaker():
    source = SimpleNamespace(title="Two guests", guest="Jake Knapp + John Zeratsky", text="Make a clear customer promise.")
    client = mock_client(requirements={"parts": [{"topic": "Episode advice", "evidence": ["S1:E1"]}]})
    asyncio.run(OpenRouterAnswerProvider(client).answer("Episode advice", {"S1": source}))
    item = json.loads(client.post.await_args_list[1].args[1]["messages"][1]["content"])["requirements"][0]["evidence"][0]
    assert item["speaker"] is None and item["source_guest"] == "Multiple guests; individual speaker unidentified"
    assert "source_title" not in item


def test_unidentified_speaker_preserves_the_customer_recruitment_task():
    source = SimpleNamespace(guest="Melissa Perri + Denise Tilles", text="Build an opt-in customer research database.")
    topic = "Recruit customers who opt into research"
    client = mock_client(requirements={"parts": [{"topic": topic, "evidence": ["S1:E1"]}]},
        written={"answers": ["The episode recommends an opt-in research database; the individual speaker is unidentified."]})
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("How can I recruit customer interview participants?", {"S1": source}))
    data = json.loads(client.post.await_args_list[1].args[1]["messages"][1]["content"])
    assert data["requirements"][0]["topic"] == topic
    assert answer.sections[0].heading == topic
    assert answer.coverage == "complete" and answer.missing_topics == []
    assert "individual speaker is unidentified" in answer.sections[0].content


def test_unlabeled_multi_guest_advice_cannot_be_assigned_to_one_guest():
    source = SimpleNamespace(title="Panel", guest="Jane Doe + John Smith 2.0", text="Understand the customer problem.")
    writings = iter([response({"answers": ["Jane Doe says to understand the customer problem."]}),
                     response({"answers": ["The episode recommends understanding the customer problem; the speaker is unidentified."]})])
    client = mock_client(requirements={"parts": [{"topic": "Jane Doe's advice", "evidence": ["S1:E1"]}]}, written=lambda p: next(writings))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("What is Jane Doe's advice?", {"S1": source}))
    assert answer.coverage == "partial" and answer.missing_topics == ["Individual attribution to Jane Doe"]
    assert answer.sections[0].heading == "Episode advice (speaker unidentified)"
    assert "Jane Doe" not in answer.sections[0].content and answer.sections[0].citation_ids == ["S1"]
    assert client.post.await_count == 4


def test_collective_episode_request_preserves_advice_without_individual_attribution():
    source = SimpleNamespace(title="Panel", guest="Jane Doe + John Smith", text="Understand the customer problem.")
    client = mock_client(requirements={"parts": [{"topic": "Panel advice", "evidence": ["S1:E1"]}]},
        written={"answers": ["The episode recommends understanding the customer problem."]})
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("What does the Jane Doe and John Smith episode recommend?", {"S1": source}))
    assert answer.coverage == "complete" and answer.missing_topics == []


def test_explicit_guest_label_supports_individual_attribution_in_a_panel():
    source = SimpleNamespace(title="Panel", guest="Jane Doe + John Smith", text="Jane Doe (00:10):\nUnderstand the customer problem.")
    client = mock_client(requirements={"parts": [{"topic": "Jane Doe's advice", "evidence": ["S1:E1"]}]},
        written={"answers": ["Jane Doe recommends understanding the customer problem."]})
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("What is Jane Doe's advice?", {"S1": source}))
    assert answer.coverage == "complete" and answer.sections[0].heading == "Jane Doe's advice"


def test_reviewer_cannot_invent_an_individual_speaker_from_topic_availability():
    source = SimpleNamespace(title="Panel", guest="Jane Doe + John Smith", text="Understand the customer problem.")
    review = {"checks": [{"part_index": 0, "verdict": "approved", "issue": ""},
                          {"part_index": 1, "verdict": "rejected", "issue": "Jane's advice is in the unlabeled episode."}],
              "missing_requests": [{"topic": "Jane Doe's advice", "evidence": ["S1:E1"]}]}
    client = mock_client(requirements={"parts": [{"topic": "Jane Doe's advice", "evidence": ["S1:E1"]}]},
        written={"answers": ["The episode recommends understanding the customer problem; the speaker is unidentified."]}, review=review)
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("What is Jane Doe's advice?", {"S1": source}))
    assert answer.coverage == "partial" and answer.missing_topics == ["Individual attribution to Jane Doe"]
    assert client.post.await_count == 3


def test_attribution_constraint_never_overrides_a_factual_rejection():
    source = SimpleNamespace(title="Panel", guest="Jane Doe + John Smith", text="Understand the customer problem.")
    review = {"checks": [{"part_index": 0, "verdict": "rejected", "issue": "The actual advice was reversed."},
                          {"part_index": 1, "verdict": "approved", "issue": ""}], "missing_requests": []}
    client = mock_client(requirements={"parts": [{"topic": "Jane Doe's advice", "evidence": ["S1:E1"]}]},
        written={"answers": ["The episode says to ignore customer problems."]}, review=review)
    with pytest.raises(ProviderError):
        asyncio.run(OpenRouterAnswerProvider(client).answer("What is Jane Doe's advice?", {"S1": source}))
    assert client.post.await_count == 7


def test_internal_excerpt_ids_trigger_repair_before_review():
    writings = iter([response({"answers": ["Teams solve problems (S1:E2)."]}), response(WRITTEN)])
    client = mock_client(written=lambda p: next(writings))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Teams", SOURCES))
    assert answer.summary == WRITTEN["answers"][0] and "S1:E" not in answer.summary
    assert [stage(c.args[1]) for c in client.post.await_args_list] == ["answer_requirements", "written_answers", "written_answers", "answer_review"]


def test_missing_request_already_represented_as_gap_does_not_trigger_rejection():
    client = mock_client(requirements={"parts": [{"topic": "Weather in Pune", "evidence": []}]},
        review={"checks": [{"part_index": 0, "verdict": "approved", "issue": "No weather evidence."}],
                "missing_requests": [{"topic": "weather in Pune", "evidence": []}]})
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Weather in Pune", SOURCES))
    assert answer.coverage == "unsupported" and client.post.await_count == 2


def test_answerable_request_cannot_be_dropped_as_duplicate_of_empty_gap():
    requirements = iter([response({"parts": [{"topic": "Customer stories", "evidence": []}]}),
                         response({"parts": [{"topic": "Customer stories", "evidence": ["S2:E1"]}]})])
    reviews = iter([response({**approval(), "missing_requests": [{"topic": "customer stories", "evidence": ["S2:E1"]}]}),
                    response(approval())])
    client = mock_client(requirements=lambda p: next(requirements), written={"answers": ["A customer story describes actual behavior."]}, review=lambda p: next(reviews))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Customer stories", SOURCES))
    assert answer.coverage == "complete" and answer.sections[0].citation_ids == ["S2"]
    assert [stage(c.args[1]) for c in client.post.await_args_list] == ["answer_requirements", "answer_review", "answer_requirements", "written_answers", "answer_review"]


def test_omitted_unavailable_request_preserves_supported_answer():
    review = approval()
    review["missing_requests"] = [{"topic": "Weather in Pune", "evidence": []}]
    client = mock_client(review=review)
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Compare teams and weather in Pune", SOURCES))
    assert answer.coverage == "partial" and answer.missing_topics == ["Weather in Pune"]
    assert answer.sections[0].content == WRITTEN["answers"][0]
    assert answer.sections[0].citation_ids == ["S1"]
    assert client.post.await_count == 3


def test_omitted_available_request_requires_another_reviewed_draft():
    reviews = iter([response({**approval(), "missing_requests": [{"topic": "Customer stories", "evidence": ["S2:E1"]}]}),
                    response(approval(2))])
    requirements = iter([response(REQ), response({"parts": [*REQ["parts"], {"topic": "Customer stories", "evidence": ["S2:E1"]}]})])
    writings = iter([response(WRITTEN), response({"answers": [WRITTEN["answers"][0], "A customer story describes actual behavior."]})])
    client = mock_client(requirements=lambda p: next(requirements), written=lambda p: next(writings), review=lambda p: next(reviews))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Compare teams and explain customer stories", SOURCES))
    assert answer.coverage == "complete" and len(answer.sections) == 2
    assert answer.sections[1].citation_ids == ["S2"] and client.post.await_count == 6


def test_review_cannot_invent_evidence_for_an_omitted_request():
    review = {**approval(), "missing_requests": [{"topic": "Customer stories", "evidence": ["S9:E1"]}]}
    client = mock_client(review=review)
    with pytest.raises(ProviderError):
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert client.post.await_count == 4


@pytest.mark.parametrize("verdict", ["approved", "rejected"])
def test_review_verdict_cannot_be_published_as_a_missing_topic(verdict):
    client = mock_client(review={**approval(), "missing_requests": [{"topic": verdict, "evidence": []}]})
    with pytest.raises(ProviderError):
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert client.post.await_count == 4


def test_factual_repair_keeps_original_task_and_expands_only_its_cited_sources():
    req = {"parts": [{"topic": "Compare teams", "evidence": ["S1:E1"]}]}
    writings = iter([response({"answers": ["Both teams only deliver output."]}), response(WRITTEN)])
    reviews = iter([response({"checks": [{"part_index": 0, "verdict": "rejected", "issue": "S1:E2 says empowered teams solve problems; preserve the original comparison task."}], "missing_requests": []}),
                    response(approval())])
    client = mock_client(requirements=req, written=lambda p: next(writings), review=lambda p: next(reviews))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("Compare teams", SOURCES))
    writers = [call.args[1] for call in client.post.await_args_list if stage(call.args[1]) == "written_answers"]
    second = json.loads(writers[1]["messages"][1]["content"])["requirements"][0]
    assert second["topic"] == "Compare teams"
    assert [e["text"] for e in second["evidence"]] == ["A feature team delivers output.", "An empowered team solves problems."]
    assert answer.sections[0].citation_ids == ["S1"]
    assert "Regenerate a concise complete plan" not in writers[1]["messages"][0]["content"]
    assert "Return only the answers array" in writers[1]["messages"][0]["content"]


@pytest.mark.parametrize("question,relation,difference", [
    ("84 out of 200", "above", "2.00"), ("78 of 200", "below", "1.00"), ("80 of 200", "equal", "0.0"),
])
def test_comparison_direction_is_calculated(question, relation, difference):
    hint = compare_percentages(ratio_calculations(question), ["Benchmark: 40%."])[0]["comparisons"][0]
    assert hint["relation"] == relation
    assert float(hint["difference_percentage_points"]) == float(difference)
    assert "percentage points" in hint["statement"] if relation != "equal" else "equals" in hint["statement"]


@pytest.mark.parametrize("answer", [
    "42% is a 2% difference from 40%.", "42% is 2% above 40%.", "The gap is 2%.",
])
def test_absolute_gap_cannot_use_relative_percent_units(answer):
    hints = compare_percentages(ratio_calculations("84 out of 200"), ["40%"])
    with pytest.raises(AnswerValidationError, match="percentage points"):
        validate_comparison_units([answer], hints)


@pytest.mark.parametrize("answer", [
    "42% is 2 percentage points above 40%.",
    "42% is a 5% relative increase from 40%.",
    "The survey result is 42%, above the 40% benchmark.",
    "A different survey reported 2% of respondents choosing an option.",
])
def test_percentage_rates_and_explicit_relative_change_are_not_rewritten(answer):
    hints = compare_percentages(ratio_calculations("84 out of 200"), ["40%"])
    validate_comparison_units([answer], hints)


def test_relative_change_is_not_confused_with_another_benchmarks_absolute_gap():
    hints = compare_percentages(ratio_calculations("84 out of 200"), ["Benchmark 40%; previous measurement 37%."])
    validate_comparison_units(["42% is 5% higher than 40% in relative terms."], hints)


def test_wrong_comparison_unit_is_repaired_before_semantic_review():
    source = SimpleNamespace(text="The benchmark is 40%.")
    writings = iter([response({"answers": ["42% is a 2% difference from 40%."]}),
                     response({"answers": ["42% is 2 percentage points above the 40% benchmark."]})])
    client = mock_client(requirements={"parts": [{"topic": "Survey", "evidence": ["S1:E1"]}]},
                         written=lambda p: next(writings))
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("84 out of 200 respondents", {"S1": source}))
    assert "2 percentage points" in answer.summary
    assert [stage(c.args[1]) for c in client.post.await_args_list] == ["answer_requirements", "written_answers", "written_answers", "answer_review"]
    assert "percentage points, not %" in client.post.await_args_list[2].args[1]["messages"][0]["content"]


def test_percentage_point_abbreviation_is_expanded_without_changing_numbers():
    source = SimpleNamespace(text="The benchmark is 40%.")
    client = mock_client(requirements={"parts": [{"topic": "Survey", "evidence": ["S1:E1"]}]},
                         written={"answers": ["42% is 2.00% points above 40%."]})
    answer = asyncio.run(OpenRouterAnswerProvider(client).answer("84 out of 200", {"S1": source}))
    assert answer.summary == "42% is 2.00 percentage points above 40%."
    draft = json.loads(client.post.await_args_list[2].args[1]["messages"][1]["content"])["draft"]
    assert draft["parts"][0]["content"] == answer.summary


def test_total_answer_deadline_cancels_model_work(monkeypatch):
    monkeypatch.setattr("app.llm.openrouter_provider.ANSWER_TIMEOUT", .01)
    cancelled = []
    async def slow(*args):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
    client = SimpleNamespace(post=AsyncMock(side_effect=slow))
    with pytest.raises(ProviderError, match="generation timed out"):
        asyncio.run(OpenRouterAnswerProvider(client).answer("Question", SOURCES))
    assert cancelled == [True]
