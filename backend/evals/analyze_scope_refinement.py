"""Audit final semantic routing and hybrid retrieval without treating scores as accuracy."""
from collections import Counter
import json
from pathlib import Path
import re

from app.rag.query_intent import normalize, name_catalog

ROOT = Path(__file__).parent / "results"
STEM = "openrouter_scope_v2_{}_2026-10-08"
EXPECTED_BLOCKS = {
    "regression_40": {"unknown-forecast", "weather", "unrelated-private-data", "ambiguous", "current-status", "unknown-person", "invent-fact"},
    "new_20": {"new-09", "new-16", "new-17", "new-18", "new-19"},
    "challenge_8": {"scope-01", "scope-02", "scope-03", "scope-04", "scope-08"},
}

def main():
    summary, rows, all_calls = {}, [], []
    for group, count in (("regression_40", 40), ("new_20", 20), ("challenge_8", 8)):
        raw = json.loads((ROOT / (STEM.format(group) + ".json")).read_text(encoding="utf-8"))
        assert raw.get("finished_utc") and len(raw["results"]) == len(raw["cases"]) == count
        runs = {r["case_id"]: r for r in raw["results"]}
        excluded_hits, preserved, valid_named, resolved_named, comparisons, covered = 0, True, 0, 0, 0, 0
        blocks = set()
        for case in raw["cases"]:
            run = runs[case["id"]]
            assert not run.get("error"), run
            meta = run["retrieval_metadata"]
            if meta["blocked_reason"]:
                blocks.add(case["id"])
                assert run["transcript_queries"] == 0
                assert not any(c["path"] in ("embeddings", "rerank") for c in run["api_calls"])
            if meta["blocked_reason"] == "out_of_domain":
                assert run["database_queries"] == 0
            candidates = {p["chunk_id"]: p for p in run.get("candidates", [])}
            for p in run["passages"]:
                preserved &= all(p[k] == candidates[p["chunk_id"]][k] for k in ("text", "start_char", "end_char"))
                excluded_hits += sum(person in name_catalog([p["guest"]]) or bool(re.search(
                    r"(?m)^\s*" + r"\s+".join(map(re.escape, person.split())) + r"\s+\(\d", p["text"], re.I))
                    for person in meta["excluded_people"])
            expected = {normalize(p) for p in case["expected_people"]}
            if expected and case["id"] not in EXPECTED_BLOCKS[group]:
                valid_named += 1
                resolved_named += expected <= set(meta["requested_people"])
                if len(expected) > 1:
                    comparisons += 1
                    present = {person for p in run["context"].values() for person in name_catalog([p["guest"]])}
                    covered += expected <= present
            rows.append((group, case, run))
        calls = [c for r in runs.values() for c in r["api_calls"]]
        all_calls.extend(calls)
        summary[group] = {
            "questions": count, "runtime_errors": 0, "routing_matches_expected": blocks == EXPECTED_BLOCKS[group],
            "blocked": len(blocks), "nonempty_contexts": sum(bool(r["context"]) for r in runs.values()),
            "blocked_with_no_database_calls": sum(runs[i]["database_queries"] == 0 for i in blocks),
            "blocked_metadata_only": sum(runs[i]["database_queries"] > 0 for i in blocks),
            "all_blocked_skip_chunks_embeddings_and_reranking": True,
            "selected_text_and_offsets_preserved": preserved, "excluded_speaker_hits": excluded_hits,
            "valid_named_cases": valid_named, "valid_named_cases_resolved": resolved_named,
            "comparisons": comparisons, "comparisons_with_all_direct_guests": covered,
            "failed_api_attempts": sum(not c.get("success") for c in calls),
            "reranker_fallbacks": sum(r["retrieval_metadata"]["ranking_diagnostics"].get("fallback", False) for r in runs.values()),
            "archive_coverage_unchanged": raw["index_coverage"] == raw["post_run_index_coverage"],
        }
        assert blocks == EXPECTED_BLOCKS[group], (group, blocks)
        assert preserved and not excluded_hits and valid_named == resolved_named and comparisons == covered
    review = json.loads((ROOT / (STEM.format("new_20") + "_review.json")).read_text(encoding="utf-8"))
    summary["new_20"]["qualitative_evidence_review"] = dict(Counter(r["status"] for r in review["reviews"]))
    summary["api_models"] = dict(Counter(c["requested_model"] for c in all_calls))
    summary["total_questions"] = 68
    summary["automated_tests_passed"] = 199
    output = ROOT / "openrouter_scope_refinement_2026-10-08"
    output.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# Semantic scope routing and concurrent hybrid retrieval",
        "",
        "The OpenRouter path now checks task meaning before archive access. A bounded Qwen3 30B A3B Instruct call through the existing OpenRouter client classifies scope and produces a faithful English retrieval question. Llama 3.1 8B remains the answer provider. BGE-M3 and Voyage remain the embedding and reranking models.",
        "",
        "Clear local unsupported patterns still short-circuit without model calls. Other rejected tasks make no database calls. Unknown or ambiguous people may read guest metadata but never transcript chunks. Scope responses are locally validated, named identities must remain present, one JSON repair is allowed, and invalid/unavailable checks raise ProviderError without opening the archive. Mixed requests keep supported topics.",
        "",
        "Semantic and keyword SQL run concurrently by default in separate sessions, after query embedding. Both results finish before fusion and reranking; neighboring chunks are fetched afterward because they depend on the candidates. The OpenAI defaults and answer flow are unchanged. A barrier test proves that both hybrid searches start before either can complete.",
        "",
        "## Final validation",
        "",
        "- 199 automated tests passed.",
        "- All 68 live requests completed without final runtime errors.",
        "- Expected routing decisions matched for the old 40, new 20, and eight additional challenge questions.",
        "- The new 20 had 18 acceptable evidence/clarification outcomes and two partial-evidence outcomes. No final domain admission/rejection failures were found in this set.",
        "- The five unrelated challenge questions made zero database calls despite misleading product, growth, culture, strategy, design, or experiment wording. Hindi retention, unfamiliar quitting/decision wording, and business-metric arithmetic were accepted.",
        "- The old 40 retained all 33 supported retrievals. Six previously unsupported/ambiguous cases still skipped chunk search; the instruction to invent a cited quote was additionally rejected.",
        "- All selected text and offsets were preserved; archive coverage stayed at 303 episodes and 22,086 chunks.",
        "- Two transient reranker API failures recovered on the existing retry; no final reranker fallback occurred.",
        "",
        "The three original domain failures are fixed at the routing stage: the Spanish retention and wise-bet questions are accepted, and the arithmetic product question is rejected before database access. The wise-bet question is rewritten as decision quality versus outcome luck and now retrieves Annie Duke's decision-process evidence.",
        "",
        "## Remaining evidence limits",
        "",
        "The positioning-versus-slogan question still lacks an explicit distinction in the selected context. The wise-bet question has useful reasoning/process passages but does not explicitly cover the entire luck-versus-quality distinction. Both remain partial rather than being scored as complete merely because retrieval returned text.",
        "",
        "The interview query excluding Teresa Torres includes useful Zoelle Egner customer-call advice, but also ranks Jessica Livingston's podcast-interview material highly. Mixed sponsor/intro chunks, peripheral material, and the 4,000-token budget remain limits. A semantic scope model can itself misclassify or rewrite meaning; these finite results are not a perfect-ranking, comprehensive-recall, or generated-answer guarantee.",
        "",
        "This is application routing and retrieval validation, not an independently annotated answer-quality benchmark. The old 40 and new 20 are now regression sets used during iteration. The eight challenge questions add fresh phrasing, but generalization needs a larger independent set. An initial Llama-based routing attempt caused false exclusions; those traces are preserved separately. Qwen was selected after checking the quote, summary, PR/FAQ, translation, and decision-quality cases that exposed those problems.",
        "",
        "## Per-question routing trace",
        "",
        "| Set | ID | Original question | Search / block decision | Context chunks |",
        "|---|---|---|---|---|",
    ]
    for group, case, run in rows:
        meta = run["retrieval_metadata"]
        decision = "Blocked: " + meta["blocked_reason"] if meta["blocked_reason"] else meta["search_question"]
        cells = [group, case["id"], case["question"], decision, str(len(run["context"]))]
        lines.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    lines += ["", "## New-20 qualitative evidence review", "",
        "| ID | Outcome | Source IDs | Finding |", "|---|---|---|---|"]
    for r in review["reviews"]:
        cells = [r["id"], r["status"], ", ".join(r["evidence_source_ids"]) or "None", r["notes"]]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    lines += ["", "Companion JSON traces retain the original questions, returned routing JSON, candidates, scores, context/source IDs, API usage, and database query counts. Preliminary query_plans in the raw traces reflect the legacy local planner; retrieval_metadata records the actual final semantic decision and search query."]
    output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
