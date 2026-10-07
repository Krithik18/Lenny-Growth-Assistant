"""Audit final retrieval gates, identity correction, ranking and preserved evidence."""
from collections import Counter
import json
from pathlib import Path
import re
from statistics import median

from app.rag.query_intent import normalize, guest_name, name_catalog
from app.rag.openrouter_rerank import evidence_penalty
from app.schemas.retrieval import RetrievedPassage

ROOT = Path(__file__).with_name("results")
SOURCE = ROOT / "openrouter_retrieval_fixed_v2_40_2026-10-08.json"


def main():
    report = json.loads(SOURCE.read_text(encoding="utf-8"))
    prior = json.loads((ROOT / "openrouter_retrieval_40_2026-10-07.json").read_text(encoding="utf-8"))
    if len(report["cases"]) != 40 or len(report["results"]) != 40 or not report.get("finished_utc"):
        raise RuntimeError("Wait for the final forty-question run to finish.")
    assert report["cases"] == prior["cases"], "Must use the identical old questions."
    runs = {run["case_id"]: run for run in report["results"]}
    old = {run["case_id"]: run for run in prior["results"] if run["enhanced"]}
    cases = []
    for case in report["cases"]:
        run = runs[case["id"]]
        meta = run["retrieval_metadata"]
        context = list(run["context"].values())
        expected = {normalize(name) for name in case["expected_people"]}
        known = bool(expected) and case["category"] != "unknown_entity"
        candidates = {p["chunk_id"]: p for p in run.get("candidates", [])}
        preserved = all(p["chunk_id"] in candidates and p["text"] == candidates[p["chunk_id"]]["text"]
                        and p["start_char"] == candidates[p["chunk_id"]]["start_char"]
                        and p["end_char"] == candidates[p["chunk_id"]]["end_char"] for p in run["passages"])
        direct = {name for p in context for name in name_catalog([p["guest"]])}
        outside = [p for p in context if known and not expected.intersection(name_catalog([p["guest"]]))
                   and not any(" " + name + " " in " " + normalize(p["text"]) + " " for name in expected)]
        excluded_hits = [p for p in run["passages"] if any(
            person in name_catalog([p["guest"]]) or re.search(r"(?m)^\s*" + r"\s+".join(map(re.escape, person.split())) + r"\s+\(\d", p["text"], re.I)
            for person in meta["excluded_people"])]
        item = {"id": case["id"], "question": case["question"], "error": run.get("error"),
            "blocked_reason": meta["blocked_reason"], "database_queries": run["database_queries"],
            "transcript_queries": run["transcript_queries"], "api_calls": len(run["api_calls"]),
            "context_count": len(context), "known_person_question": known,
            "known_identity_resolved": known and expected <= set(meta["requested_people"]),
            "outside_expected_identity": len(outside), "all_requested_direct_guests": known and expected <= direct,
            "comparison": len(expected) > 1, "source_text_and_offsets_preserved": preserved,
            "excluded_speaker_hits": len(excluded_hits), "search_question": meta["search_question"],
            "old_first_passage_penalty": evidence_penalty(RetrievedPassage.model_validate(old[case["id"]]["passages"][0])) if old[case["id"]]["passages"] else 0,
            "new_first_passage_penalty": evidence_penalty(RetrievedPassage.model_validate(run["passages"][0])) if run["passages"] else 0,
            "reranking": meta["ranking_diagnostics"], "seconds": run["seconds"]}
        cases.append(item)
    calls = [call for run in report["results"] for call in run["api_calls"]]
    blocked = [case for case in cases if case["blocked_reason"]]
    known = [case for case in cases if case["known_person_question"]]
    comparisons = [case for case in known if case["comparison"]]
    summary = {"questions": 40, "successful_runs": sum(not case["error"] for case in cases),
        "supported_nonempty_runs": sum(not case["blocked_reason"] and case["context_count"] > 0 for case in cases),
        "blocked_runs": len(blocked), "blocked_without_transcript_queries": sum(case["transcript_queries"] == 0 for case in blocked),
        "blocked_without_database_queries": sum(case["database_queries"] == 0 for case in blocked),
        "blocked_without_api_calls": sum(case["api_calls"] == 0 for case in blocked),
        "known_person_questions": len(known), "known_person_questions_resolved": sum(case["known_identity_resolved"] for case in known),
        "outside_requested_identity_context_passages": sum(case["outside_expected_identity"] for case in known),
        "comparisons": len(comparisons), "comparisons_with_all_direct_guests": sum(case["all_requested_direct_guests"] for case in comparisons),
        "all_selected_chunks_preserved": all(case["source_text_and_offsets_preserved"] for case in cases),
        "excluded_speaker_hits": sum(case["excluded_speaker_hits"] for case in cases),
        "old_first_passages_with_promo_or_intro": sum(case["old_first_passage_penalty"] > 0 for case in cases),
        "new_first_passages_with_promo_or_intro": sum(case["new_first_passage_penalty"] > 0 for case in cases),
        "median_supported_seconds": round(median(case["seconds"] for case in cases if not case["blocked_reason"]), 2),
        "api_paths": dict(Counter(call["path"] for call in calls)),
        "api_failed_attempts": sum(call.get("success") is False for call in calls),
        "rerank_fallbacks": sum(case["reranking"].get("fallback", False) for case in cases),
        "low_relevance_candidates_rejected": sum(case["reranking"].get("low_relevance_rejected", 0) for case in cases),
        "archive_coverage_unchanged": report["index_coverage"] == report["post_run_index_coverage"]}
    analysis = {"summary": summary, "cases": cases}
    SOURCE.with_name(SOURCE.stem + "_analysis.json").write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Revised OpenRouter retrieval and reranking — 8 October 2026", "",
        "The final pipeline was tested on exactly the same forty questions as the previous evaluation. "
        "Real BGE-M3 embedding calls, Voyage reranking, and the unchanged live transcript archive were used. No Llama answers were generated.", "",
        "## Results", "", "| Check | Result |", "| --- | --- |"]
    for label, value in summary.items():
        lines.append(f"| {label.replace('_', ' ')} | {value} |")
    lines.extend(["", "## Per-question checks", "", "| Question | Decision | Transcript queries | Context chunks | Names resolved |", "| --- | --- | ---: | ---: | --- |"])
    for case in cases:
        lines.append(f"| {case['question'].replace('|', '/')} | {case['blocked_reason'] or 'searched'} | {case['transcript_queries']} | {case['context_count']} | {case['known_identity_resolved'] if case['known_person_question'] else '—'} |")
    lines.extend(["", "## Changes and evidence", "",
        "- Full names, unique surnames, context-qualified first names, and conservative two-word spelling corrections are resolved against the archive. The corrected name is used by embeddings and reranking. Multi-guest episode names are split into individual identities.",
        "- Excluded people are handled independently of positive subjects. Their episodes, single-speaker chunks, and explicit speaker lines in compilations are excluded from both semantic and keyword candidates. Other guests' references to the excluded person can remain relevant.",
        "- Clear weather, credentials, current-employment, exact-future-revenue, and ambiguous-reference requests stop before any database call. The unknown-person case reads guest metadata only and stops before embedding or transcript search. Mixed requests retain the supported clause.",
        "- Neighbor expansion includes more semantic and keyword seeds to improve access to continuations. Whole stored chunks and their original source offsets are preserved.",
        "- Voyage scores now drive a conservative relevance filter, with a soft penalty for sponsor/intro text and a small preference for the requested guest's own episode. Comparisons keep evidence from each requested person. Invalid ranking responses still retry; unavailable reranking retains candidates rather than discarding evidence.",
        "- The initial forty-question rerun exposed an April statement inside a compilation surviving episode-only exclusion. That trace is preserved in openrouter_retrieval_fixed_40_2026-10-08.json; speaker-aware exclusion was added and all forty questions were rerun for this final report.", "",
        "## Practical limits", "",
        "The old questions form a regression set, not an independent accuracy benchmark. Identity membership, stored-text preservation, query counts, and ranking scores do not prove that every claim can be supported. "
        "The score floors (best score at least 0.15; candidate floor max(0.10, 0.35 × best)) and small ranking penalties are conservative heuristics, not calibrated probabilities. "
        "Unknown/ambiguous names are not guessed. Domain detection is based on explicit patterns and an English topic vocabulary; unfamiliar wording, multilingual queries, or a superficially relevant term can still be misclassified. "
        "First-name correction requires clear person grammar and an unambiguous catalog match. Sponsor and intro text can remain in mixed chunks, and the 4,000-token context is not an exhaustive episode view. "
        "The upcoming new question set is needed to measure generalization and false exclusions. No perfect-ranking or complete-answer guarantee is implied.", "",
        "Unit/integration validation: 182 selected tests passed. API traces, unfiltered candidates, reranker scores, selected contexts, search decisions, and database query counts are retained in the companion JSON files."])
    SOURCE.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
