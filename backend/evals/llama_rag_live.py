"""Read-only live workspace RAG evaluation; never changes production policies."""

import argparse
import asyncio
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

import httpx
from sqlalchemy import event, select, text
import tiktoken

from app.core.config import get_settings
from app.db.models import TranscriptChunk
from app.ingestion.source import ARCHIVE_SHA256
from app.main import create_app
from app.rag import openrouter_service as service_module
from evals.provider_comparison_live import index_coverage


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ContextVar("full_rag_evaluation", default=None)
RETRIEVAL = ContextVar("full_rag_retrieval", default=None)
CALL = ContextVar("full_rag_call", default=None)
STAGE = ContextVar("full_rag_stage", default="retrieval")
ENCODING = tiktoken.get_encoding("cl100k_base")
CODE_PATHS = [
    "app/main.py", "app/api/routes/workspace.py", "app/api/routes/rag.py",
    "app/db/session.py", "app/llm/client.py", "app/llm/openrouter_provider.py",
    "app/rag/service.py", "app/rag/openrouter_service.py", "app/rag/retrieval.py",
    "app/rag/openrouter_retrieval.py", "app/rag/openrouter_embeddings.py",
    "app/rag/openrouter_rerank.py", "app/rag/openrouter_scope.py",
    "app/rag/query_intent.py", "app/rag/context.py", "app/schemas/answer.py",
    "app/schemas/retrieval.py", "app/skills/context.py",
]


def utc():
    return datetime.now(timezone.utc).isoformat()


def hashes():
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in CODE_PATHS}


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def dump(passages):
    return [passage.model_dump(mode="json") for passage in passages]


def intervals_overlap(queries):
    semantic = [q for q in queries if q["kind"] == "semantic" and "end" in q]
    keyword = [q for q in queries if q["kind"] == "keyword" and "end" in q]
    return any(a["connection"] != b["connection"] and
               max(a["start"], b["start"]) < min(a["end"], b["end"])
               for a in semantic for b in keyword)


async def revision_snapshot(database):
    # Bounded episode metadata only; no schema or archive mutations.
    async with database.sessions() as session:
        rows = (await session.execute(text("""
            SELECT e.id::text AS episode_id, e.active_revision_id::text AS revision_id,
                   e.repository_path AS member
            FROM app_data.episodes e
            JOIN app_data.episode_revisions r ON r.id=e.active_revision_id
            WHERE r.source_archive_sha256=:sha AND r.status='ready'
            ORDER BY e.id
        """), {"sha": ARCHIVE_SHA256})).mappings().all()
    return [dict(row) for row in rows]


async def main(args):
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.case:
        cases = [case for case in cases if case["id"] in args.case]
    if not cases or len({c["id"] for c in cases}) != len(cases) or len({c["question"] for c in cases}) != len(cases):
        raise ValueError("Cases must have unique IDs and questions.")
    fixture_hash = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    if args.output.exists() and not args.resume:
        raise ValueError("Use a fresh output path; existing runs are preserved.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    case_dir = args.output.with_suffix("")
    case_dir.mkdir(exist_ok=True)
    settings = get_settings()
    if not settings.database_url.get_secret_value() or not settings.openrouter_api_key.get_secret_value():
        raise RuntimeError("Database and OpenRouter must be configured.")
    report = {
        "started_utc": utc(), "method": "Real workspace route, provider=openrouter, mode=chat, empty history; live database and provider APIs; no frozen source injection, mocks, or answer cache. Sequential questions; concurrent semantic/keyword searches remain enabled.",
        "archive_sha256": ARCHIVE_SHA256, "fixture_sha256": fixture_hash,
        "cases": cases, "code_sha256_before": hashes(), "results": [],
        "production_changes": [], "other_provider_calls": [],
        "limits": "Regression/integration baseline. Coverage labels and citation membership do not prove claim support. Detailed source review is reported separately. Frontend, auto skill selection, essays, and artifacts are outside this chat-RAG baseline.",
    }
    if args.resume:
        report = json.loads(args.output.read_text(encoding="utf-8"))
        if report["cases"] != cases or report["fixture_sha256"] != fixture_hash or report["code_sha256_before"] != hashes():
            raise ValueError("Resume requires identical cases, fixture and implementation.")
        report.setdefault("resumed_utc", []).append(utc())
    atomic_json(args.output, report)
    app = create_app(settings)
    original_candidate_retrieve = service_module.retrieve
    source_md5 = {}
    pending_queries = {}
    originals = []

    try:
        async with app.router.lifespan_context(app):
            database, service = app.state.database, app.state.openrouter_rag
            if service is None:
                raise RuntimeError("OpenRouter RAG service is unavailable.")
            report["preflight"] = {"index_coverage": await index_coverage(database), "revisions": await revision_snapshot(database)}
            atomic_json(args.output, report)
            print(json.dumps({"stage": "preflight", "questions": len(cases), **report["preflight"]["index_coverage"]}), flush=True)

            def before_query(conn, cursor, statement, parameters, context, executemany):
                lowered = statement.lower().strip()
                if lowered.startswith(("insert", "update", "delete", "create", "alter", "drop", "truncate")):
                    raise RuntimeError("Evaluation refuses database writes.")
                run = CURRENT.get()
                if run is None:
                    return
                kind = ("keyword" if "keyword_candidates" in lowered else
                        "neighbor" if "chunk_index =" in lowered else
                        "semantic" if "<=>" in lowered else "catalog")
                values = list(parameters.values()) if isinstance(parameters, dict) else list(parameters or [])
                item = {"kind": kind, "start": round(time.monotonic() - run["clock_start"], 6),
                        "connection": id(conn), "openrouter_filter": "openrouter" in [v for v in values if isinstance(v, str)],
                        "bge_m3_filter": "baai/bge-m3" in [v for v in values if isinstance(v, str)]}
                run["database_queries"].append(item)
                if RETRIEVAL.get() is not None:
                    RETRIEVAL.get()["database_queries"].append(item)
                pending_queries[id(context)] = item

            def after_query(conn, cursor, statement, parameters, context, executemany):
                item = pending_queries.pop(id(context), None)
                if item is not None:
                    item["end"] = round(time.monotonic() - CURRENT.get()["clock_start"], 6)
                    item["seconds"] = round(item["end"] - item["start"], 4)

            event.listen(database.engine.sync_engine, "before_cursor_execute", before_query)
            event.listen(database.engine.sync_engine, "after_cursor_execute", after_query)

            async def response_hook(response):
                call = CALL.get()
                if call is None:
                    return
                payload = json.loads(response.request.content)
                attempt = {"http_status": response.status_code, "model": payload.get("model"),
                           "provider_preferences": payload.get("provider"),
                           "response_format": payload.get("response_format", {}).get("type")}
                if response.status_code >= 400:
                    await response.aread()
                    try:
                        error = response.json().get("error", {})
                        attempt["error_code"] = error.get("code")
                        attempt["provider_name"] = error.get("metadata", {}).get("provider_name")
                    except (ValueError, AttributeError, TypeError):
                        pass
                call["transport_attempts"].append(attempt)

            service.client.http.event_hooks["response"].append(response_hook)
            original_post = service.client.post

            async def post(path, payload):
                run = CURRENT.get()
                model = payload.get("model")
                if str(model).startswith(("openai/", "gpt-")):
                    raise RuntimeError("Unexpected OpenAI model in Llama evaluation.")
                call = {"path": path, "requested_model": model, "stage": STAGE.get(),
                        "schema": payload.get("response_format", {}).get("json_schema", {}).get("name"),
                        "transport_attempts": []}
                run["api_calls"].append(call)
                token = CALL.set(call)
                started = time.monotonic()
                try:
                    result = await original_post(path, payload)
                    call.update(returned_model=result.get("model"), served_provider=result.get("provider"),
                                usage=result.get("usage"), response_id=result.get("id"))
                    if path == "embeddings":
                        call["vector_dimensions"] = [len(x.get("embedding", [])) for x in result.get("data", [])]
                    elif path == "rerank":
                        call["ranking"] = result.get("results")
                    else:
                        call["response"] = result
                    return result
                except Exception as error:
                    call.update(error_type=type(error).__name__, error_detail=str(error) if type(error).__name__ == "ProviderError" else None)
                    raise
                finally:
                    call["seconds"] = round(time.monotonic() - started, 3)
                    CALL.reset(token)

            service.client.post = post

            if app.state.rag is not None:
                async def forbidden_post(path, payload):
                    report["other_provider_calls"].append({"path": path, "model": payload.get("model")})
                    raise RuntimeError("OpenAI calls are prohibited in this Llama baseline.")
                app.state.rag.client.post = forbidden_post

            async def candidate_retrieve(*a, **kw):
                result = await original_candidate_retrieve(*a, **kw)
                record = RETRIEVAL.get()
                record["candidates"] = dump(result.passages)
                record["candidate_metadata"] = {key: value for key, value in result.model_dump(mode="json").items() if key != "passages"}
                return result

            service_module.retrieve = candidate_retrieve
            original_retrieve = service.retrieve

            async def retrieve(question, *a, **kw):
                run = CURRENT.get()
                record = {"question": question, "database_queries": [], "top_k": kw.get("top_k", 5)}
                run["retrievals"].append(record)
                token, stage_token = RETRIEVAL.set(record), STAGE.set(f"retrieval_{len(run['retrievals'])}")
                started = time.monotonic()
                try:
                    found = await original_retrieve(question, *a, **kw)
                    record["result"] = found.model_dump(mode="json")
                    return found
                except Exception as error:
                    record["error_type"] = type(error).__name__
                    raise
                finally:
                    record["seconds"] = round(time.monotonic() - started, 3)
                    record["semantic_keyword_overlap"] = intervals_overlap(record["database_queries"])
                    RETRIEVAL.reset(token)
                    STAGE.reset(stage_token)

            service.retrieve = retrieve
            original_answer = service.generator.answer

            async def answer(question, sources):
                run = CURRENT.get()
                record = {"question": question, "sources": {key: p.model_dump(mode="json") for key, p in sources.items()},
                          "context_tokens": sum(len(ENCODING.encode(p.text, disallowed_special=())) for p in sources.values())}
                for passage in sources.values():
                    source_md5[passage.chunk_id] = hashlib.md5(passage.text.encode("utf-8")).hexdigest()
                run["generation_rounds"].append(record)
                token = STAGE.set(f"answer_{len(run['generation_rounds'])}")
                started = time.monotonic()
                try:
                    output = await original_answer(question, sources)
                    record["answer"] = output.model_dump(mode="json")
                    return output
                except Exception as error:
                    record["error_type"] = type(error).__name__
                    raise
                finally:
                    record["seconds"] = round(time.monotonic() - started, 3)
                    STAGE.reset(token)

            service.generator.answer = answer
            original_ask = service.ask

            async def ask(question, **kw):
                result = await original_ask(question, **kw)
                CURRENT.get()["grounded_result"] = result.model_dump(mode="json")
                return result

            service.ask = ask
            done = {run["case_id"] for run in report["results"]}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://evaluation.local") as http:
                for case in cases:
                    if case["id"] in done:
                        continue
                    run = {"case_id": case["id"], "question": case["question"], "service": type(service).__name__,
                           "api_calls": [], "retrievals": [], "generation_rounds": [], "database_queries": [],
                           "clock_start": time.monotonic()}
                    token = CURRENT.set(run)
                    print(json.dumps({"stage": "start", "case": case["id"]}), flush=True)
                    try:
                        async with asyncio.timeout(360):
                            response = await http.post("/api/v1/workspace/chat", json={"provider": "openrouter", "mode": "chat", "history": [], "message": case["question"]})
                        run["http_status"] = response.status_code
                        run["workspace_response"] = response.json()
                        result = run.get("grounded_result")
                        if result:
                            answer_value, sources = result["answer"], result["sources"]
                            citations = answer_value["summary_citation_ids"] + [cid for s in answer_value["sections"] for cid in s["citation_ids"]]
                            run["checks"] = {
                                "all_citations_resolve": set(citations) <= sources.keys(),
                                "retrieval_provider_matches": all(r.get("result", {}).get("provider") == "openrouter" for r in run["retrievals"] if "result" in r),
                                "coverage": answer_value["coverage"], "source_count": len(sources),
                                "missing_topics": answer_value["missing_topics"],
                                "returned_writer_models": sorted({c["returned_model"] for c in run["api_calls"] if c["requested_model"] == service.generator.model and c.get("returned_model")}),
                                "semantic_keyword_overlap": any(r["semantic_keyword_overlap"] for r in run["retrievals"]),
                            }
                    except Exception as error:
                        run["error_type"] = type(error).__name__
                    finally:
                        run["seconds"] = round(time.monotonic() - run.pop("clock_start"), 3)
                        CURRENT.reset(token)
                        report["results"].append(run)
                        atomic_json(case_dir / f"{case['id']}.json", {"case": case, "result": run})
                        atomic_json(args.output, report)
                        print(json.dumps({"stage": "result", "case": case["id"], "status": run.get("http_status"), "seconds": run["seconds"], "api_calls": len(run["api_calls"]), **run.get("checks", {}), "error_type": run.get("error_type")}), flush=True)

            report["postflight"] = {"index_coverage": await index_coverage(database), "revisions": await revision_snapshot(database)}
            report["postflight"]["revisions_unchanged"] = report["preflight"]["revisions"] == report["postflight"]["revisions"]
            for run in report["results"]:
                for round_ in run["generation_rounds"]:
                    for passage in round_["sources"].values():
                        from uuid import UUID
                        source_md5[UUID(passage["chunk_id"])] = hashlib.md5(passage["text"].encode("utf-8")).hexdigest()
            async with database.sessions() as session:
                rows = (await session.execute(select(TranscriptChunk.id, TranscriptChunk.content).where(TranscriptChunk.id.in_(list(source_md5))))).all() if source_md5 else []
            observed = {key: hashlib.md5(content.encode("utf-8")).hexdigest() for key, content in rows}
            report["postflight"]["all_used_source_text_unchanged"] = observed == source_md5
            report["postflight"]["checked_chunks"] = len(source_md5)
            report["code_sha256_after"] = hashes()
            report["code_unchanged"] = report["code_sha256_before"] == report["code_sha256_after"]
            report["finished_utc"] = utc()
    except Exception as error:
        report["run_error_type"] = type(error).__name__
        report["stopped_utc"] = utc()
        raise
    finally:
        service_module.retrieve = original_candidate_retrieve
        atomic_json(args.output, report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("llama_rag_baseline_questions_20.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append")
    parser.add_argument("--resume", action="store_true")
    asyncio.run(main(parser.parse_args()))
