"""Paired cap-50 versus cap-40 test on 20 previously complete, grounded answers."""

import argparse
import asyncio
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import time

import tiktoken

from app.core.config import get_settings
from app.llm.client import OpenAIClient
from app.llm.openai_provider import OpenAIAnswerProvider
from app.rag.context import build_context
from app.rag.rerank import rerank
from app.schemas.retrieval import RetrievedPassage
from evals.full_suite import structured
from evals.transcript_audit import AuditReview, JUDGE, TRACE, point_issue, record_post


ROOT = Path(__file__).parent


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def select_cases():
    baseline = ROOT / "results/full303_rerank_context_comparison"
    pools = ROOT / "results/rerank_fix_49_20261007"
    references = json.loads((baseline / "reference_cases.json").read_text(encoding="utf-8"))["cases"]
    groups = defaultdict(list)
    for case in references:
        saved = pools / f"{case['id']}.json"
        if not saved.exists():
            continue
        pool = json.loads(saved.read_text(encoding="utf-8"))["candidates"]
        review = json.loads((baseline / f"{case['id']}.json").read_text(encoding="utf-8"))["budgets"]["4000"]["review"]
        if len(pool) > 40 and review["grounded"] and review["addresses_question"] and all(
                p["reference_supported"] and p["answer_covered"] for p in review["points"]):
            groups[case["category"]].append((case, pool))
    selected = []
    while len(selected) < 20:
        before = len(selected)
        for category in sorted(groups):
            if groups[category] and len(selected) < 20:
                selected.append(groups[category].pop(0))
        if len(selected) == before:
            raise ValueError("Insufficient eligible questions")
    return selected


def complete(result):
    review = result.get("review")
    return bool(review and all(p["reference_supported"] and p["answer_covered"] for p in review["points"]))


def good(result):
    return complete(result) and result["review"]["grounded"] and result["review"]["addresses_question"]


def write_report(out, rows):
    arms = {}
    for cap in (50, 40):
        results = [row["arms"][str(cap)] for row in rows]
        timings = [r["rerank_seconds"] for r in results if "rerank_seconds" in r]
        arms[str(cap)] = {
            "questions": len(results), "judged": sum("review" in r for r in results),
            "complete": sum(complete(r) for r in results), "complete_grounded_on_topic": sum(good(r) for r in results),
            "grounded": sum(r.get("review", {}).get("grounded", False) for r in results),
            "errors": sum("error" in r for r in results),
            "rerank_fallbacks": sum(r.get("rerank", {}).get("fallback", False) for r in results),
            "rerank_retries": sum(len(r.get("rerank", {}).get("attempts", [])) > 1 for r in results),
            "median_rerank_seconds": statistics.median(timings) if timings else None,
            "median_stage_seconds": statistics.median([r["stage_seconds"] for r in results if "stage_seconds" in r]) if timings else None,
            "exact_anchor_top20": sum(r.get("anchor_top20", False) for r in results),
            "exact_anchor_context": sum(r.get("anchor_context", False) for r in results),
            "point_issues": dict(Counter(issue for r in results for issue in r.get("point_issues", []))) }
    paired = Counter()
    for row in rows:
        a, b = row["arms"]["50"], row["arms"]["40"]
        if "review" not in a or "review" not in b:
            paired["unjudged_pair"] += 1
        elif complete(a) and complete(b):
            paired["complete_both"] += 1
        elif complete(a):
            paired["regressed_at_40"] += 1
        elif complete(b):
            paired["improved_at_40"] += 1
        else:
            paired["incomplete_both"] += 1
    summary = {"arms": arms, "paired_completeness": dict(paired),
               "historical_complete_questions": 20, "context_budget": 4000, "reranker_output_tokens": 2400}
    supplemental = {}
    for cap in (50, 40):
        results = [row["arms"][str(cap)] for row in rows]
        retried = [r["answer_retry"] for r in results if "answer_retry" in r]
        if retried:
            supplemental[str(cap)] = {"failed_answer_stages_retried": len(retried),
                "retry_errors": sum("error" in r for r in retried),
                "complete_after_answer_retry": sum(complete(r.get("answer_retry", r)) for r in results),
                "complete_grounded_on_topic_after_answer_retry": sum(good(r.get("answer_retry", r)) for r in results)}
    if supplemental:
        summary["supplemental_answer_retries"] = supplemental
    save(out / "summary.json", summary)
    lines = ["# Reranking comparison: 50-candidate cap versus 40", "",
        "20 questions previously judged complete, grounded, and on topic at 4,000 context tokens. Selection uses saved pools from the prior 49-question regression, requires more than 40 candidates, and rotates across available question categories. These questions are not a random sample of all 303 transcripts.", "",
        "Both arms reuse identical saved candidates. Cap 40 takes the first 40 candidates in original retrieval order before reranking; cap 50 retains the full pool (41–49 after deduplication). Both use the current reranker default of 2,400 output tokens, return the top 20, pack 4,000 transcript tokens, and generate a fresh answer. Arm order alternates by question.", "",
        "This tests reranking and one answer-generation pass, using the same protocol as the earlier context-budget audit. No database search is timed and the application's optional missing-topic refinement is not included. No production candidate cap is changed.", "",
        "| Measure | Cap 50 | Cap 40 |", "|---|---:|---:|"]
    for key in arms["50"]:
        lines.append(f"| {key.replace('_', ' ')} | {arms['50'][key]} | {arms['40'][key]} |")
    lines += ["", "Paired completeness: " + json.dumps(dict(paired)), "",
        "## Per-question comparison", "", "| Question | Category | Full pool | Complete at 50 | Complete at 40 | Rerank seconds at 50 | Rerank seconds at 40 |", "|---|---|---:|---|---|---:|---:|"]
    for row in rows:
        question = row["question"].replace("|", "\\|").replace("\n", " ")
        a, b = row["arms"]["50"], row["arms"]["40"]
        lines.append(f"| {question} | {row['category']} | {len(row['candidates'])} | {complete(a)} | {complete(b)} | {a.get('rerank_seconds', 0):.2f} | {b.get('rerank_seconds', 0):.2f} |")
    lines += ["", "## Answer quality issues"]
    for row in rows:
        a, b = row["arms"]["50"], row["arms"]["40"]
        if not good(a) or not good(b):
            lines += ["", f"**{row['id']}**", "", "- Cap 50: " + a.get("review", {}).get("explanation", a.get("error", "No review")),
                      "- Cap 40: " + b.get("review", {}).get("explanation", b.get("error", "No review")), ""]
    lines += ["", "The same model generates and judges answers using synthetic, source-verified reference excerpts. Scores are automated proxies and single-run differences may reflect model variability. Exact-anchor presence is a diagnostic, not a complete semantic relevance measurement. Raw rankings, contexts, answers, reviews, and timings are saved in each question's JSON file."]
    if supplemental:
        lines += ["", "## Supplemental answer-stage retry", "",
            "A failed answer-generation or evaluation stage was retried once using the exact same saved context and ranking. Original failures remain in the first-pass table above; this does not change measured reranking timings or claim the application automatically recovered.", "",
            json.dumps(supplemental, indent=2)]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


async def retry_failed_stages(out):
    client = OpenAIClient(get_settings().openai_api_key.get_secret_value())
    record_post(client)
    generator = OpenAIAnswerProvider(client)
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in out.glob("*.json")
            if p.name not in {"summary.json", "metadata.json"}]
    try:
        for row in rows:
            for cap, original in row["arms"].items():
                if "error" not in original or "sources" not in original or "answer_retry" in original:
                    continue
                result = original["answer_retry"] = {"trace": {"provider_calls": [], "sql_calls": []}}
                token = TRACE.set(result["trace"])
                try:
                    context = {key: RetrievedPassage.model_validate(p) for key, p in original["sources"].items()}
                    answer = await generator.answer(row["question"], context)
                    result["answer"] = answer.model_dump()
                    review = await structured(client, JUDGE, {
                        "question": row["question"], "expected_points": list(enumerate(row["expected_points"])),
                        "reference_excerpt": row["excerpt"], "retrieved_top20": original["ranked_passages"],
                        "provided_context": original["sources"], "answer": result["answer"]}, AuditReview)
                    assert sorted(p.point_index for p in review.points) == list(range(len(row["expected_points"])))
                    result["review"] = review.model_dump()
                    result["point_issues"] = [point_issue(p.model_dump()) for p in review.points]
                except Exception as error:
                    result["error"] = type(error).__name__
                finally:
                    TRACE.reset(token)
                    save(out / f"{row['id']}.json", row)
                print(f"Supplemental {row['id']} cap={cap}: complete={complete(result)}, error={result.get('error')}", flush=True)
    finally:
        await client.close()
    print(json.dumps(write_report(out, rows), indent=2), flush=True)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--retry-failed-stages", action="store_true")
    args = parser.parse_args()
    out = args.work_dir
    if args.retry_failed_stages:
        await retry_failed_stages(out)
        return
    out.mkdir(parents=True, exist_ok=False)
    selected = select_cases()
    save(out / "metadata.json", {"question_ids": [c["id"] for c, _ in selected],
        "context_budget": 4000, "reranker_output_tokens": 2400, "candidate_caps": [50, 40],
        "candidate_count_range": [min(len(p) for _, p in selected), max(len(p) for _, p in selected)],
        "categories": dict(Counter(c["category"] for c, _ in selected)),
        "reranker_sha256": hashlib.sha256((ROOT.parent / "app/rag/rerank.py").read_bytes()).hexdigest()})
    client = OpenAIClient(get_settings().openai_api_key.get_secret_value())
    record_post(client)
    generator = OpenAIAnswerProvider(client)
    semaphore = asyncio.Semaphore(3)
    encoding = tiktoken.get_encoding("cl100k_base")
    rows = []

    async def one(index, case, pool):
        async with semaphore:
            row = {**case, "candidates": pool, "arms": {}}
            path = out / f"{case['id']}.json"
            save(path, row)
            for cap in ((50, 40) if index % 2 == 0 else (40, 50)):
                result = row["arms"][str(cap)] = {"cap": cap, "trace": {"provider_calls": [], "sql_calls": []}}
                token = TRACE.set(result["trace"])
                try:
                    candidates = [RetrievedPassage.model_validate(p) for p in pool[:cap]]
                    result["candidate_count"] = len(candidates)
                    result["rerank"] = {}
                    started = time.monotonic()
                    ranked = await rerank(client, case["question"], candidates, diagnostics=result["rerank"])
                    result["rerank_seconds"] = time.monotonic() - started
                    assert len(ranked) == len(candidates) and {p.chunk_id for p in ranked} == {p.chunk_id for p in candidates}
                    result["ranked_passages"] = [p.model_dump(mode="json") for p in ranked[:20]]
                    context = build_context(ranked[:20], token_budget=4000)
                    result["sources"] = {key: p.model_dump(mode="json") for key, p in context.items()}
                    result["used_context_tokens"] = sum(len(encoding.encode(p.text, disallowed_special=())) for p in context.values())
                    assert result["used_context_tokens"] <= 4000
                    result["anchor_top20"] = any(case["evidence_quote"] in p.text for p in ranked[:20])
                    result["anchor_context"] = any(case["evidence_quote"] in p.text for p in context.values())
                    save(path, row)
                    answer_started = time.monotonic()
                    answer = await generator.answer(case["question"], context)
                    result["answer_seconds"] = time.monotonic() - answer_started
                    result["stage_seconds"] = time.monotonic() - started
                    result["answer"] = answer.model_dump()
                    save(path, row)
                    review = await structured(client, JUDGE, {
                        "question": case["question"], "expected_points": list(enumerate(case["expected_points"])),
                        "reference_excerpt": case["excerpt"], "retrieved_top20": result["ranked_passages"],
                        "provided_context": result["sources"], "answer": result["answer"]}, AuditReview)
                    assert sorted(p.point_index for p in review.points) == list(range(len(case["expected_points"])))
                    result["review"] = review.model_dump()
                    result["point_issues"] = [point_issue(p.model_dump()) for p in review.points]
                except Exception as error:
                    result["error"] = type(error).__name__
                finally:
                    TRACE.reset(token)
                    save(path, row)
                print(f"{case['id']} cap={cap} complete={complete(result)} error={result.get('error')} fallback={result.get('rerank', {}).get('fallback')}", flush=True)
            rows.append(row)
            print(f"Completed {len(rows)}/20 pairs", flush=True)
    try:
        async with asyncio.TaskGroup() as group:
            for index, (case, pool) in enumerate(selected):
                group.create_task(one(index, case, pool))
    finally:
        await client.close()
    summary = write_report(out, rows)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
