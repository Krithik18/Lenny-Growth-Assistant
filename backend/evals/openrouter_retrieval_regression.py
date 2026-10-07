"""Live before/after retrieval checks; no answer generation or database writes."""
import asyncio
import argparse
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace

from app.core.config import get_settings
from app.db.session import Database
from app.llm.client import OpenRouterClient, ProviderError
from app.ingestion.chunker import TranscriptChunker
from app.rag.openrouter_embeddings import OpenRouterEmbeddings
from app.rag.openrouter_service import OpenRouterRAGService
from app.rag.openrouter_rerank import rerank
from app.rag.retrieval import retrieve
from app.rag.context import build_context
from app.rag.query_intent import plan_query
from app.db.models import Episode
from sqlalchemy import select, event
from app.rag import openrouter_service as service_module
from evals.provider_comparison_live import index_coverage

DEFAULT_OUTPUT = Path(__file__).with_name("results") / "openrouter_retrieval_regression_2026-10-07.json"
DEFAULT_CASES = {"positioning", "pmf-number", "false-premise", "comparison-pmf", "activation-plan", "experimentation-risk"}
current_record = ContextVar("retrieval_evaluation_record", default=None)


async def main(output=DEFAULT_OUTPUT, case_file=None, concurrency=1, resume=False, enhanced_only=False):
    output = output.resolve()
    if output.exists() and not resume:
        raise RuntimeError("Choose a fresh output file; existing results are preserved.")
    cases = json.loads((case_file or Path(__file__).with_name("broad_questions.json")).read_text(encoding="utf-8"))
    if case_file is None:
        cases = [case for case in cases if case["id"] in DEFAULT_CASES]
    if len({case["id"] for case in cases}) != len(cases) or len({case["question"] for case in cases}) != len(cases):
        raise ValueError("Evaluation requires unique case IDs and questions.")
    settings = get_settings()
    database = Database(settings)
    client = OpenRouterClient(settings.openrouter_api_key.get_secret_value())
    service = OpenRouterRAGService(database, client)
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "cases": cases,
        "method": "Live OpenRouter BGE-M3 + Voyage reranking; before/after same archive; no answer calls", "results": []}
    report["enhanced_only"] = enhanced_only
    if enhanced_only:
        report["method"] = f"{len(cases)} questions through OpenRouter semantic scope routing, retrieval and Voyage reranking; live archive; no answer generation."
    if resume:
        report = json.loads(output.read_text(encoding="utf-8"))
        if report["cases"] != cases:
            raise ValueError("Resume cases must match the original evaluation exactly.")
        report.setdefault("resumed_utc", []).append(datetime.now(timezone.utc).isoformat())
    save_lock = asyncio.Lock()

    async def save():
        # Stage on local temporary storage, then replace atomically. This avoids
        # truncating a synced OneDrive checkpoint while its filesystem is busy.
        async with save_lock:
            data = json.dumps(report, indent=2, ensure_ascii=False)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".json") as file:
                file.write(data)
                staged = Path(file.name)
            for attempt in range(6):
                try:
                    os.replace(staged, output)
                    return
                except OSError:
                    if attempt == 5:
                        print(f"Checkpoint replacement unavailable; recovery copy: {staged}", flush=True)
                        raise
                    await asyncio.sleep(1)
    original_client_post = client.post
    original_retrieve = service_module.retrieve

    async def traced_retrieve(*args, **kwargs):
        result = await original_retrieve(*args, **kwargs)
        current_record.get()["candidates"] = [p.model_dump(mode="json") for p in result.passages]
        return result

    service_module.retrieve = traced_retrieve

    def count_queries(conn, cursor, statement, parameters, context, executemany):
        record = current_record.get()
        if record is not None:
            record["database_queries"] += 1
            if "transcript_chunks" in statement:
                record["transcript_queries"] += 1

    event.listen(database.engine.sync_engine, "before_cursor_execute", count_queries)

    async def traced_post(path, payload):
        record = current_record.get()
        call = {"path": path, "requested_model": payload.get("model")}
        record["api_calls"].append(call)
        start = time.monotonic()
        try:
            result = await original_client_post(path, payload)
            call.update(returned_model=result.get("model"), usage=result.get("usage"), success=True)
            if path == "rerank":
                call["ranking"] = result.get("results")
            elif path == "chat/completions":
                call["scope_response"] = result.get("choices", [])
            return result
        except Exception as error:
            call.update(success=False, error_type=type(error).__name__)
            raise
        finally:
            call["seconds"] = round(time.monotonic() - start, 3)

    client.post = traced_post

    async def original_post(path, payload):
        payload = dict(payload)
        payload["documents"] = [document.split("Transcript:\n", 1)[1] for document in payload["documents"]]
        return await client.post(path, payload)

    async def one(case, enhanced):
        start = time.monotonic()
        record = {"case_id": case["id"], "question": case["question"], "enhanced": enhanced, "api_calls": [],
                  "database_queries": 0, "transcript_queries": 0}
        token = current_record.set(record)
        try:
            if enhanced:
                result = await service.retrieve(case["question"], top_k=20)
            else:
                result = await retrieve(database, OpenRouterEmbeddings(client), case["question"],
                    TranscriptChunker().version, 20, hybrid=True, candidate_pool=True)
                ranked = await rerank(SimpleNamespace(post=original_post), case["question"], result.passages)
                result = result.model_copy(update={"passages": ranked[:20]})
            record["passages"] = [p.model_dump(mode="json") for p in result.passages]
            record["context"] = {key: p.model_dump(mode="json") for key, p in build_context(result.passages).items()}
            record["retrieval_metadata"] = {key: getattr(result, key, None) for key in (
                "search_question", "requested_people", "excluded_people", "blocked_reason", "ranking_diagnostics", "scope_decision")}
        except Exception as error:
            record["error"] = type(error).__name__
            if isinstance(error, ProviderError):
                record["error_detail"] = str(error)
        finally:
            current_record.reset(token)
        record["seconds"] = round(time.monotonic() - start, 2)
        report["results"].append(record)
        await save()
        print(json.dumps({"case": case["id"], "enhanced": enhanced, "seconds": record["seconds"],
            "guests": [p["guest"] for p in record.get("passages", [])[:5]], "error": record.get("error")}), flush=True)

    try:
        report["index_coverage"] = await index_coverage(database)
        async with database.sessions() as session:
            catalog = (await session.execute(select(Episode.guest).distinct())).scalars().all()
        report["query_plans"] = {case["id"]: {
            "people": list(plan_query(case["question"], catalog).people),
            "terms": list(plan_query(case["question"], catalog).terms),
            "phrases": list(plan_query(case["question"], catalog).phrases),
            "excluded_people": list(plan_query(case["question"], catalog).excluded_people),
            "search_question": plan_query(case["question"], catalog).search_question,
            "blocked_reason": plan_query(case["question"], catalog).blocked_reason,
        } for case in cases}
        print(json.dumps({"stage": "preflight", "questions": len(cases), **report["index_coverage"]}), flush=True)
        semaphore = asyncio.Semaphore(concurrency)
        completed = {(run["case_id"], run["enhanced"]) for run in report["results"]}
        async def pair(case):
            async with semaphore:
                await asyncio.gather(*(one(case, enhanced) for enhanced in ((True,) if enhanced_only else (False, True))
                    if (case["id"], enhanced) not in completed))
        await asyncio.gather(*(pair(case) for case in cases))
        report["post_run_index_coverage"] = await index_coverage(database)
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        await save()
    finally:
        service_module.retrieve = original_retrieve
        await client.close()
        await database.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--concurrency", type=int, choices=(1, 2), default=1)
    parser.add_argument("--resume", action="store_true", help="Run only missing pairs from the matching checkpoint.")
    parser.add_argument("--enhanced-only", action="store_true", help="Only the revised pipeline, preserving previous baselines.")
    args = parser.parse_args()
    asyncio.run(main(args.output, args.cases, args.concurrency, args.resume, args.enhanced_only))
