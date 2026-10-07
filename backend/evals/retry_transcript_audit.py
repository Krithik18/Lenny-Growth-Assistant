"""Resume failed stages only; preserve all first-attempt failures and successful outputs."""

import argparse
import asyncio
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

from app.core.config import get_settings
from app.db.session import Database
from app.llm.client import OpenAIClient
from app.rag.context import build_context
from app.rag.service import RAGService
from app.schemas.retrieval import RetrievedPassage
from evals.full_suite import structured
from evals.transcript_audit import AuditReview, JUDGE, TRACE, point_issue, record_post, record_sql, save

OUT = Path(__file__).parent / "results"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="full303_rerank_concurrent_20261007_resumed")
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    directory = (args.work_dir or OUT) / args.run
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    configuration = metadata["configuration"]
    if not configuration["reranking"] or not configuration["concurrent_search"]:
        raise ValueError("Retry configuration must match the audited service")
    cases = json.loads((OUT / "full_cases.json").read_text(encoding="utf-8"))["cases"]
    settings = get_settings()
    database = Database(settings)
    client = OpenAIClient(settings.openai_api_key.get_secret_value())
    record_post(client)
    record_sql(database)
    recorded_post = client.post

    async def review_with_more_output_room(path, payload):
        if payload.get("text", {}).get("format", {}).get("name") == "AuditReview":
            # The original judge occasionally consumed all 1,800 tokens on
            # reasoning. Only the evaluator's limit changes; answer limit stays fixed.
            payload = {**payload, "max_output_tokens": 4000}
        return await recorded_post(path, payload)

    client.post = review_with_more_output_room
    service = RAGService(database, client, reranking=True, concurrent_search=True)
    semaphore = asyncio.Semaphore(4)
    retried = 0

    async def one(case):
        nonlocal retried
        path = directory / f"{case['id']}.json"
        row = json.loads(path.read_text(encoding="utf-8"))
        missing = [b for b in configuration["context_budgets"] if "review" not in row.get("budgets", {}).get(str(b), {})
                   or "error" in row.get("budgets", {}).get(str(b), {})]
        if not missing and "error" not in row:
            return
        async with semaphore:
            retried += 1
            stamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
            history = {"at_ist": stamp, "retrieval_error": row.get("error"),
                       "budget_errors": {str(b): row.get("budgets", {}).get(str(b), {}).get("error") for b in missing},
                       "judge_retry_output_limit": 4000}
            row.setdefault("retry_history", []).append(history)
            token = TRACE.set(row["trace"])
            try:
                row.pop("error", None)
                if "ranked_passages" not in row:
                    started = time.monotonic()
                    found = await service.retrieve(case["question"], top_k=20)
                    row["retrieval_seconds"] = time.monotonic() - started
                    row["ranked_passages"] = [p.model_dump(mode="json") for p in found.passages]
                    row["hit_at_5"] = any(case["evidence_quote"] in p.text for p in found.passages[:5])
                    row["hit_at_20"] = any(case["evidence_quote"] in p.text for p in found.passages)
                    save(path, row)
                for budget in missing:
                    result = row.setdefault("budgets", {}).setdefault(str(budget), {
                        "budget": budget, "trace": {"provider_calls": [], "sql_calls": []}})
                    budget_token = TRACE.set(result["trace"])
                    try:
                        result.pop("error", None)
                        passages = [RetrievedPassage.model_validate(p) for p in row["ranked_passages"]]
                        sources = build_context(passages, token_budget=budget)
                        result["sources"] = {k: p.model_dump(mode="json") for k, p in sources.items()}
                        result["context_hit"] = any(case["evidence_quote"] in p.text for p in sources.values())
                        import tiktoken
                        encoding = tiktoken.get_encoding("cl100k_base")
                        result["used_context_tokens"] = sum(len(encoding.encode(p.text, disallowed_special=())) for p in sources.values())
                        if "answer" not in result:
                            started = time.monotonic()
                            result["answer"] = (await service.generator.answer(case["question"], sources)).model_dump()
                            result["answer_seconds"] = time.monotonic() - started
                            save(path, row)
                        review = await structured(client, JUDGE, {
                            "question": case["question"], "expected_points": list(enumerate(case["expected_points"])),
                            "reference_excerpt": case["excerpt"], "retrieved_top20": row["ranked_passages"],
                            "provided_context": result["sources"], "answer": result["answer"]}, AuditReview)
                        if sorted(p.point_index for p in review.points) != list(range(len(case["expected_points"]))):
                            raise ValueError("Judge must assess every point exactly once")
                        result["review"] = review.model_dump()
                        result["point_issues"] = [point_issue(p.model_dump()) for p in review.points]
                    except Exception as error:
                        result["error"] = type(error).__name__
                    finally:
                        TRACE.reset(budget_token)
                    save(path, row)
                print(f"Retried {case['id']}: budgets={missing}", flush=True)
            except Exception as error:
                row["error"] = type(error).__name__
            finally:
                save(path, row)
                TRACE.reset(token)

    try:
        async with asyncio.TaskGroup() as group:
            for case in cases:
                group.create_task(one(case))
    finally:
        await client.close()
        await database.close()
    print(f"Retried failed stages in {retried} cases; first-attempt errors preserved in retry_history", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
