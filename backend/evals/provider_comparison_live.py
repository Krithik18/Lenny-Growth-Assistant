"""Live paired workspace evaluation; no mocks or cached model responses."""

import asyncio
import argparse
from contextvars import ContextVar
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.ingestion.chunker import TranscriptChunker
from app.ingestion.source import ARCHIVE_SHA256
from app.main import create_app


OUT = Path(__file__).parent / "results" / "provider_comparison_2026-10-07.json"
CASE_IDS = ["activation-plan", "pmf-number", "discovery-definition", "strategy-framework",
            "positioning", "experimentation-risk", "comparison-pmf", "false-premise",
            "partial-weather", "invent-fact"]
current_run = ContextVar("evaluation_run", default=None)
current_call = ContextVar("evaluation_call", default=None)


def instrument(service):
    original_post = service.client.post
    original_retrieve = service.retrieve
    original_ask = service.ask

    async def response_hook(response):
        call = current_call.get()
        if call is not None:
            call.update(http_status=response.status_code, endpoint=str(response.request.url))

    service.client.http.event_hooks["response"].append(response_hook)

    async def post(path, payload):
        run = current_run.get()
        call = {"path": path, "requested_model": payload.get("model")}
        run["api_calls"].append(call)
        token = current_call.set(call)
        start = time.monotonic()
        try:
            result = await original_post(path, payload)
            if isinstance(result, dict):
                call.update(returned_model=result.get("model"), served_provider=result.get("provider"),
                            usage=result.get("usage"), response_id=result.get("id"))
                if path == "embeddings":
                    call["vector_dimensions"] = [len(item.get("embedding", [])) for item in result.get("data", [])]
                elif path == "rerank":
                    call["ranking"] = result.get("results")
                else:
                    call["response"] = result
            return result
        except Exception as error:
            call["error_type"] = type(error).__name__
            raise
        finally:
            call["seconds"] = round(time.monotonic() - start, 3)
            current_call.reset(token)

    async def retrieve(question, *args, **kwargs):
        started = time.monotonic()
        found = await original_retrieve(question, *args, **kwargs)
        current_run.get()["retrievals"].append({
            "question": question, "seconds": round(time.monotonic() - started, 3),
            "provider": found.provider, "embedding_model": found.embedding_model,
            "passages": [p.model_dump(mode="json") for p in found.passages],
        })
        return found

    async def ask(question, **kwargs):
        result = await original_ask(question, **kwargs)
        current_run.get()["grounded_result"] = result.model_dump(mode="json")
        return result

    service.client.post = post
    service.retrieve = retrieve
    service.ask = ask


async def index_coverage(database):
    async with database.sessions() as session:
        rows = (await session.execute(text("""
            SELECT e.repository_path AS member, count(DISTINCT c.id) AS chunks,
              count(v.id) FILTER (WHERE v.provider='openai' AND v.model='text-embedding-3-small'
                AND v.dimensions=1536 AND v.input_version='raw-chunk-v1') AS openai,
              count(v.id) FILTER (WHERE v.provider='openrouter' AND v.model='baai/bge-m3'
                AND v.dimensions=1024 AND v.input_version='raw-chunk-v1') AS openrouter
            FROM app_data.episodes e JOIN app_data.episode_revisions r ON r.id=e.active_revision_id
            JOIN app_data.transcript_chunks c ON c.episode_revision_id=r.id
            LEFT JOIN app_data.chunk_embeddings v ON v.chunk_id=c.id
            WHERE r.source_archive_sha256=:sha AND r.status='ready' AND c.chunking_version=:version
            GROUP BY e.repository_path ORDER BY e.repository_path
        """), {"sha": ARCHIVE_SHA256, "version": TranscriptChunker().version})).mappings().all()
    return {"episodes": len(rows), "chunks": sum(r["chunks"] for r in rows),
            "openai_embeddings": sum(r["openai"] for r in rows),
            "openrouter_embeddings": sum(r["openrouter"] for r in rows),
            "same_coverage_per_episode": all(r["openai"] == r["openrouter"] == r["chunks"] > 0 for r in rows)}


async def main(output=OUT, case_ids=CASE_IDS, providers=("openai", "openrouter")):
    settings = get_settings()
    if not all([settings.database_url.get_secret_value(), settings.openai_api_key.get_secret_value(),
                settings.openrouter_api_key.get_secret_value()]):
        raise RuntimeError("Database and both provider API keys must be configured.")
    if output.exists():
        raise RuntimeError("Results already exist; choose a new output path for a new paid run.")
    authored = json.loads(Path(__file__).with_name("broad_questions.json").read_text(encoding="utf-8"))
    cases = [next(case for case in authored if case["id"] == case_id) for case_id in case_ids]
    app = create_app(settings)
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "method":
              "Real workspace route via ASGI transport, live database and real external provider HTTP calls; no mocks/caches.",
              "archive_sha256": ARCHIVE_SHA256, "cases": cases, "results": []}

    def save():
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    async with app.router.lifespan_context(app):
        report["index_coverage"] = await index_coverage(app.state.database)
        print(json.dumps({"stage": "preflight", **report["index_coverage"]}), flush=True)
        if not report["index_coverage"]["same_coverage_per_episode"]:
            raise RuntimeError("Embedding spaces have unequal episode coverage; comparison halted.")
        services = {"openai": app.state.rag, "openrouter": app.state.openrouter_rag}
        services = {provider: services[provider] for provider in providers}
        for service in services.values():
            instrument(service)
        save()
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://evaluation.local") as http:
            async def one(case, provider):
                run = {"case_id": case["id"], "provider": provider,
                       "service": type(services[provider]).__name__, "api_calls": [], "retrievals": []}
                token = current_run.set(run)
                started = time.monotonic()
                try:
                    async with asyncio.timeout(360):
                        response = await http.post("/api/v1/workspace/chat", json={
                            "message": case["question"], "provider": provider, "mode": "chat", "history": [],
                        })
                    run["http_status"] = response.status_code
                    run["workspace_response"] = response.json()
                    result = run.get("grounded_result")
                    if result:
                        answer, sources = result["answer"], result["sources"]
                        ids = answer["summary_citation_ids"] + [cid for s in answer["sections"] for cid in s["citation_ids"]]
                        run["checks"] = {
                            "all_citations_resolve": set(ids) <= sources.keys(),
                            "retrieval_provider_matches": all(r["provider"] == provider for r in run["retrievals"]),
                            "source_count": len(sources), "coverage": answer["coverage"],
                            "missing_topics": answer["missing_topics"],
                            "words": len(re.findall(r"\S+", answer["summary"] + " " + " ".join(s["content"] for s in answer["sections"]))),
                        }
                except Exception as error:
                    run["error_type"] = type(error).__name__
                finally:
                    run["seconds"] = round(time.monotonic() - started, 3)
                    current_run.reset(token)
                    report["results"].append(run)
                    save()
                    print(json.dumps({"stage": "result", "case": case["id"], "provider": provider,
                          "status": run.get("http_status"), "seconds": run["seconds"],
                          "calls": len(run["api_calls"]), **run.get("checks", {}),
                          "error_type": run.get("error_type")}), flush=True)
            for case in cases:
                print(json.dumps({"stage": "start_pair", "case": case["id"]}), flush=True)
                await asyncio.gather(*(one(case, provider) for provider in services))
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    save()
    print(f"Saved {len(report['results'])} live results to {output}", flush=True)


async def verify_coverage():
    """Recheck exact chunk coverage without making additional paid model calls."""
    app = create_app(get_settings())
    async with app.router.lifespan_context(app):
        coverage = await index_coverage(app.state.database)
    report = json.loads(OUT.read_text(encoding="utf-8"))
    report["post_run_index_coverage"] = coverage
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(coverage), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-coverage", action="store_true", help="Read-only index verification; no model calls.")
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--case", action="append", dest="case_ids", choices=CASE_IDS)
    parser.add_argument("--provider", action="append", choices=("openai", "openrouter"))
    args = parser.parse_args()
    asyncio.run(verify_coverage() if args.verify_coverage else main(
        args.output, args.case_ids or CASE_IDS, args.provider or ("openai", "openrouter")))
