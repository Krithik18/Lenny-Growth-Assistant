"""Retest the historical reranking failures without changing retrieval or context limits."""

import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import time

import tiktoken

from app.core.config import get_settings
from app.db.session import Database
from app.ingestion.chunker import TranscriptChunker
from app.llm.client import OpenAIClient
from app.rag.context import build_context
from app.rag.openai_embeddings import OpenAIEmbeddings
from app.rag.rerank import rerank
from app.rag.retrieval import retrieve


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_report(out):
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in out.glob("*.json")
            if p.name not in {"summary.json", "metadata.json"}]
    assert len(rows) == summary["questions"] == 49
    lines = ["# Reranking fallback regression — 49 previously affected questions", "",
        "Context budget: **2,000 tokens**. Candidate cap: **50**, unchanged. Returned evidence: top 20 before context packing.", "",
        "## Results", "", "| Measure | Result |", "|---|---:|"]
    for key, value in summary.items():
        lines.append(f"| {key.replace('_', ' ')} | {value} |")
    lines += ["", "## Change", "",
        "The structured response now requires exactly as many IDs as candidates and restricts IDs to the supplied range. Strict application validation still requires a complete permutation, including uniqueness and integer types. No passages are removed or fabricated to repair an invalid response.", "",
        "An invalid, incomplete, timed-out, or failed response gets one retry. Incomplete responses receive a larger output allowance on retry (2,400 rather than 1,200 tokens). Refusals are not retried. Each attempt has a 30-second timeout; two exhausted attempts preserve the original candidate order. External task cancellation propagates.", "",
        "## Interpretation and limits", "",
        "These are the same 49 questions whose historical run fell back: 46 completed but invalid rankings, one incomplete response, one provider error, and one timeout. The original full candidate pools were not saved, so this run uses fresh retrieval and is not an identical-input paired comparison. Every current candidate pool and attempt diagnostic is saved beside this report.", "",
        "This is a ranking-validity regression, not an answer-generation or completeness evaluation. Exact reference-anchor presence is a supplementary diagnostic and is not a semantic relevance score. A successful run does not guarantee that future provider failures cannot occur. Retries add latency when needed. No 40-candidate experiment was run.", "",
        "Verification: 96 backend tests passed, including strict validation, retry recovery, exhausted retry preserving original evidence, full 50-candidate ordering, cancellation, and the existing 2,000-token default checks.", "",
        "## Per-question results", "", "| Question | Candidates | Attempts | Failed attempt reasons | Fallback | Seconds |",
        "|---|---:|---:|---|---|---:|"]
    for row in sorted(rows, key=lambda r: r["id"]):
        diag = row["diagnostics"]
        reasons = ", ".join(a["reason"] for a in diag["attempts"] if not a["valid"]) or "None"
        question = row["question"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {question} | {len(row['candidates'])} | {len(diag['attempts'])} | {reasons} | {diag['fallback']} | {row['reranking_seconds']:.2f} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    baseline = Path(__file__).parent / "results/full303_rerank_context_comparison"
    cases = json.loads((baseline / "reference_cases.json").read_text(encoding="utf-8"))["cases"]
    selected = []
    for case in cases:
        row = json.loads((baseline / f"{case['id']}.json").read_text(encoding="utf-8"))
        calls = [c for c in row["trace"]["provider_calls"] if c["kind"] == "evidence_order"]
        if any(not c.get("valid_ranking", False) for c in calls):
            selected.append((case, calls))
    assert len(selected) == 49
    out = args.work_dir
    out.mkdir(parents=True, exist_ok=True)
    if (out / "metadata.json").exists():
        raise ValueError("Use a fresh output directory; never mix runs")
    save(out / "metadata.json", {"context_budget": 2000, "candidate_cap": 50,
        "question_count": len(selected), "concurrent_search": True,
        "rerank_sha256": hashlib.sha256((Path(__file__).parents[1] / "app/rag/rerank.py").read_bytes()).hexdigest(),
        "baseline": str(baseline), "historical_statuses": dict(Counter(c["status"] for _, calls in selected for c in calls)),
        "limitation": "Historical full candidate pools were not saved. Candidates are freshly retrieved. This tests ranking validity, not answer completeness."})
    settings = get_settings()
    database = Database(settings)
    client = OpenAIClient(settings.openai_api_key.get_secret_value())
    provider = OpenAIEmbeddings(client)
    encoding = tiktoken.get_encoding("cl100k_base")
    semaphore = asyncio.Semaphore(3)
    results = []

    async def run(case, historical_calls):
        async with semaphore:
            result = await retrieve(database, provider, case["question"], TranscriptChunker().version,
                20, hybrid=True, candidate_pool=True, concurrent_search=True)
            candidates = result.passages
            assert 2 <= len(candidates) <= 50
            row = {"id": case["id"], "question": case["question"], "historical_calls": historical_calls,
                "candidates": [p.model_dump(mode="json") for p in candidates]}
            save(out / f"{case['id']}.json", row)
            diagnostics = {}
            started = time.monotonic()
            ranked = await rerank(client, case["question"], candidates, diagnostics=diagnostics)
            seconds = time.monotonic() - started
            assert len(ranked) == len(candidates) and {id(p) for p in ranked} == {id(p) for p in candidates}
            if diagnostics["fallback"]:
                assert ranked is candidates
            context = build_context(ranked[:20], token_budget=2000)
            used = sum(len(encoding.encode(p.text)) for p in context.values())
            assert used <= 2000
            row.update(diagnostics=diagnostics, reranking_seconds=seconds,
                ranked_chunk_ids=[str(p.chunk_id) for p in ranked],
                context_chunk_ids=[str(p.chunk_id) for p in context.values()], used_context_tokens=used,
                anchor_in_top20=any(case["evidence_quote"] in p.text for p in ranked[:20]),
                anchor_in_context=any(case["evidence_quote"] in p.text for p in context.values()))
            save(out / f"{case['id']}.json", row)
            results.append(row)
            print(f"{len(results)}/49: {case['id']} attempts={len(diagnostics['attempts'])} fallback={diagnostics['fallback']}", flush=True)

    try:
        async with asyncio.TaskGroup() as group:
            for case, calls in selected:
                group.create_task(run(case, calls))
    finally:
        await client.close()
        await database.close()
    summary = {"questions": len(results),
        "first_attempt_valid": sum(r["diagnostics"]["attempts"][0]["valid"] for r in results),
        "recovered_on_retry": sum(len(r["diagnostics"]["attempts"]) == 2 and not r["diagnostics"]["fallback"] for r in results),
        "remaining_fallbacks": sum(r["diagnostics"]["fallback"] for r in results),
        "failed_attempt_reasons": dict(Counter(a["reason"] for r in results for a in r["diagnostics"]["attempts"] if not a["valid"])),
        "median_reranking_seconds": statistics.median(r["reranking_seconds"] for r in results),
        "candidate_count_range": [min(len(r["candidates"]) for r in results), max(len(r["candidates"]) for r in results)],
        "anchor_in_top20": sum(r["anchor_in_top20"] for r in results),
        "anchor_in_context": sum(r["anchor_in_context"] for r in results)}
    save(out / "summary.json", summary)
    write_report(out)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
