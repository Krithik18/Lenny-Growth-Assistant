"""Test a 2,400-token first-attempt allowance on the 16 saved retry cases."""

import asyncio
from collections import Counter
import json
from pathlib import Path
import statistics
import time

from app.core.config import get_settings
from app.llm.client import OpenAIClient
from app.rag.rerank import rerank
from app.schemas.retrieval import RetrievedPassage


def write_report(out, summary, results):
    lines = ["# Reranker output allowance comparison", "", "Tested **2,400 output tokens on the first attempt** for the 16 questions that needed retries in the previous run. Each question reused its exact saved candidate pool. The answer context budget remained 2,000 tokens.", "", f"The earlier runs took a median of {summary['median_previous_two_attempt_seconds']:.2f} seconds across both attempts; the 2,400-token first-attempt runs took {summary['median_seconds']:.2f} seconds. This paired timing is consistent with retries causing extra latency for these cases. The API responses in the new run were complete on the first attempt. The run does not prove that output-token exhaustion caused every prior incomplete response because the earlier API diagnostics did not retain a detailed incomplete reason.", "", "The reranker produced a different ordering on each question compared with the earlier completed run. That shows ranking order varies between calls; this comparison evaluates response completion and latency, not answer quality or relevance improvement.", "", "| Measure | Result |", "|---|---:|"]
    lines += [f"| {key.replace('_', ' ')} | {value} |" for key, value in summary.items()]
    lines += ["", "## Per-question results", "", "| Question | Candidates | First attempt | Attempts | Fallback | Seconds | Same order |", "|---|---:|---|---:|---|---:|---|"]
    for row in sorted(results, key=lambda x: x["id"]):
        attempt = row["diagnostics"]["attempts"][0]
        question = row["question"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {question} | {row['candidate_count']} | {'valid' if attempt['valid'] else attempt.get('reason')} | {len(row['diagnostics']['attempts'])} | {row['diagnostics']['fallback']} | {row['seconds']:.2f} | {row['same_order_as_first_run']} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main():
    base = Path(__file__).parent / "results/rerank_fix_49_20261007"
    out = Path(__file__).parent / "results/rerank_allowance_2400_16_20261007"
    out.mkdir(parents=True, exist_ok=False)
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in base.glob("*.json")
             if p.name not in {"metadata.json", "summary.json"}]
    selected = [row for row in cases if len(row["diagnostics"]["attempts"]) == 2]
    assert len(selected) == 16
    settings = get_settings()
    client = OpenAIClient(settings.openai_api_key.get_secret_value())
    results = []
    semaphore = asyncio.Semaphore(3)

    async def run(row):
        async with semaphore:
            candidates = [RetrievedPassage.model_validate(p) for p in row["candidates"]]
            diagnostics = {}
            started = time.monotonic()
            ranked = await rerank(client, row["question"], candidates, diagnostics=diagnostics,
                                  initial_output_tokens=2400)
            elapsed = time.monotonic() - started
            assert len(ranked) == len(candidates) and {p.chunk_id for p in ranked} == {p.chunk_id for p in candidates}
            result = {"id": row["id"], "question": row["question"], "candidate_count": len(candidates),
                "diagnostics": diagnostics, "seconds": elapsed,
                "ranked_chunk_ids": [str(p.chunk_id) for p in ranked],
                "first_run_attempts": row["diagnostics"]["attempts"],
                "same_order_as_first_run": [str(p.chunk_id) for p in ranked] == row["ranked_chunk_ids"]}
            (out / f"{row['id']}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            results.append(result)
            print(f"{len(results)}/16 {row['id']} attempts={len(diagnostics['attempts'])} fallback={diagnostics['fallback']}", flush=True)

    try:
        async with asyncio.TaskGroup() as group:
            for row in selected:
                group.create_task(run(row))
    finally:
        await client.close()
    summary = {"questions": len(results), "initial_allowance": 2400,
        "valid_first_attempt": sum(r["diagnostics"]["attempts"][0]["valid"] for r in results),
        "needed_retry": sum(len(r["diagnostics"]["attempts"]) > 1 for r in results),
        "remaining_fallbacks": sum(r["diagnostics"]["fallback"] for r in results),
        "first_attempt_reasons": dict(Counter(r["diagnostics"]["attempts"][0].get("reason")
                                               for r in results if not r["diagnostics"]["attempts"][0]["valid"])),
        "median_seconds": statistics.median(r["seconds"] for r in results),
        "same_ranking_order_as_first_run": sum(r["same_order_as_first_run"] for r in results),
        "candidate_pools": "Reused exact saved candidate pools from the 49-question reranking regression."}
    summary["median_previous_two_attempt_seconds"] = statistics.median(
        sum(attempt["seconds"] for attempt in r["first_run_attempts"]) for r in results)
    summary["median_seconds_saved"] = (summary["median_previous_two_attempt_seconds"] - summary["median_seconds"])
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(out, summary, results)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
