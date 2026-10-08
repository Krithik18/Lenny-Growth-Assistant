"""Live generation-only evaluation over frozen, reviewed transcript snapshots."""
import argparse
import asyncio
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from app.core.config import get_settings
from app.llm.client import OpenRouterClient, ProviderError
from app.llm.openrouter_provider import OpenRouterAnswerProvider, REVIEW_MODEL, Requirements, WrittenAnswers, AnswerPlan, response_content, validate_answer, validate_review, AnswerValidationError
from app.schemas.retrieval import RetrievedPassage

ROOT = Path(__file__).parent
CURRENT = ContextVar("generation_case", default=None)

async def main(output, resume=False, fixture=ROOT / "answer_generation_fixed_sources_20.json", selected_ids=None):
    data = fixture.read_bytes()
    cases = json.loads(data)
    fingerprint = hashlib.sha256(data).hexdigest()
    assert len(cases) == len({c["id"] for c in cases}) == len({c["question"] for c in cases}) == 20
    selected_ids = sorted(set(selected_ids or [c["id"] for c in cases]))
    if not set(selected_ids) <= {c["id"] for c in cases}:
        raise ValueError("Unknown evaluation case")
    if output.exists() and not resume:
        raise ValueError("Choose a fresh output file; prior results are preserved.")
    report = {"started_utc": datetime.now(timezone.utc).isoformat(),
        "method": "Generation only: fixed reviewed evidence; no database, scope, embedding, retrieval or reranker calls.",
        "model": OpenRouterAnswerProvider.model, "review_model": REVIEW_MODEL,
        "provider_sha256": hashlib.sha256((ROOT.parent / "app/llm/openrouter_provider.py").read_bytes()).hexdigest(),
        "fixture_sha256": fingerprint, "selected_case_ids": selected_ids, "cases": cases, "results": []}
    if resume:
        report = json.loads(output.read_text(encoding="utf-8"))
        assert report["fixture_sha256"] == fingerprint and report["cases"] == cases
        assert report.get("selected_case_ids", sorted(c["id"] for c in cases)) == selected_ids
    client = OpenRouterClient(get_settings().openrouter_api_key.get_secret_value())
    provider = OpenRouterAnswerProvider(client)
    original_post = client.post
    save_lock = asyncio.Lock()

    async def save():
        async with save_lock:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".json") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
                staged = Path(f.name)
            for attempt in range(6):
                try:
                    os.replace(staged, output)
                    return
                except OSError:
                    if attempt == 5:
                        raise
                    await asyncio.sleep(1)

    async def traced_post(path, payload):
        assert path == "chat/completions" and payload["model"] in {provider.model, REVIEW_MODEL}, "Generation-only boundary violated."
        record = CURRENT.get()
        schema_name = payload.get("response_format", {}).get("json_schema", {}).get("name")
        stage = {"answer_requirements": "requirements", "written_answers": "writing", "answer_review": "grounding_review"}[schema_name]
        call = {"path": path, "requested_model": payload["model"], "stage": stage}
        record["api_calls"].append(call)
        started = time.monotonic()
        try:
            result = await original_post(path, payload)
            call.update(success=True, returned_model=result.get("model"), provider=result.get("provider"), usage=result.get("usage"), choices=result.get("choices"))
            try:
                if stage == "grounding_review":
                    data = json.loads(payload["messages"][1]["content"])
                    draft = AnswerPlan.model_validate(data["draft"])
                    review = validate_review(result, draft, {e["id"] for s in data["evidence"] for e in s["excerpts"]},
                        data.get("locked_unavailable_parts", []), data.get("application_attribution_limits", []))
                    call["grounding_issues"] = review.issues
                elif stage == "requirements":
                    Requirements.model_validate_json(response_content(result), strict=True)
                elif stage == "writing":
                    written = WrittenAnswers.model_validate_json(response_content(result), strict=True)
                    expected = len(json.loads(payload["messages"][1]["content"])["requirements"])
                    if len(written.answers) != expected or any(not answer.strip() for answer in written.answers):
                        raise AnswerValidationError("Wrong answer count or blank answer")
                call["structurally_valid"] = True
            except (AnswerValidationError, ValueError) as error:
                call.update(structurally_valid=False, validation_feedback=str(error))
            return result
        except ProviderError as error:
            call.update(success=False, error=str(error))
            raise
        finally:
            call["seconds"] = round(time.monotonic() - started, 3)
    client.post = traced_post

    async def one(case):
        sources = {sid: RetrievedPassage.model_validate(p) for sid, p in case["sources"].items()}
        record = {"case_id": case["id"], "question": case["question"], "api_calls": [], "_sources": sources}
        token = CURRENT.set(record)
        started = time.monotonic()
        try:
            answer = await asyncio.wait_for(provider.answer(case["question"], sources), timeout=150)
            record["answer"] = answer.model_dump()
            validate_answer({"choices": [{"finish_reason": "stop", "message": {"content": answer.model_dump_json()}}]}, sources)
            record["final_contract_valid"] = True
            record["expected_coverage_match"] = answer.coverage in case["expected_coverages"]
        except Exception as error:
            record["error"] = type(error).__name__
            if isinstance(error, ProviderError):
                record["error_detail"] = str(error)
        finally:
            CURRENT.reset(token)
            del record["_sources"]
            record["seconds"] = round(time.monotonic() - started, 2)
        report["results"].append(record)
        await save()
        print(json.dumps({"case": case["id"], "coverage": record.get("answer", {}).get("coverage"),
            "attempts": len(record["api_calls"]), "error": record.get("error"), "seconds": record["seconds"]}), flush=True)

    completed = {r["case_id"] for r in report["results"]}
    semaphore = asyncio.Semaphore(2)
    async def limited(case):
        async with semaphore:
            await one(case)
    try:
        await asyncio.gather(*(limited(case) for case in cases if case["id"] in selected_ids and case["id"] not in completed))
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        await save()
    finally:
        await client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "llama_generation_fixed_20_2026-10-08.json")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fixture", type=Path, default=ROOT / "answer_generation_fixed_sources_20.json")
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    asyncio.run(main(args.output.resolve(), args.resume, args.fixture.resolve(), args.case))
