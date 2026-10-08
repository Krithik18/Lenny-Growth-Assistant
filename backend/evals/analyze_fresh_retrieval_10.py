"""Review a frozen ten-question retrieval run, retaining failures and partial coverage."""
from collections import Counter
import json
from pathlib import Path
import re
from app.rag.openrouter_scope import ScopeDecision
from app.rag.query_intent import normalize

ROOT = Path(__file__).parent
BASE = ROOT / "results" / "openrouter_retrieval_fresh_10_2026-10-08"

def main():
    raw = json.loads(BASE.with_suffix(".json").read_text(encoding="utf-8"))
    review = json.loads(BASE.with_name(BASE.name + "_review.json").read_text(encoding="utf-8"))
    assert raw.get("finished_utc") and len(raw["cases"]) == len(raw["results"]) == 10
    previous = [c for f in ("retrieval_questions_40.json", "retrieval_questions_new_20.json", "retrieval_scope_challenge_8.json")
                for c in json.loads((ROOT / f).read_text(encoding="utf-8"))]
    assert not {c["question"] for c in previous} & {c["question"] for c in raw["cases"]}
    runs = {r["case_id"]: r for r in raw["results"]}
    notes = {r["id"]: r for r in review["reviews"]}
    assert runs.keys() == notes.keys()
    calls = [c for r in runs.values() for c in r["api_calls"]]
    preserved = True
    for run in runs.values():
        candidates = {p["chunk_id"]: p for p in run.get("candidates", [])}
        for p in run.get("passages", []):
            preserved &= all(p[k] == candidates[p["chunk_id"]][k] for k in ("text", "start_char", "end_char"))
    failed = runs["fresh-10"]
    invalid_names = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", failed["question"])
    decisions = [ScopeDecision.model_validate_json(c["scope_response"][0]["message"]["content"]) for c in failed["api_calls"]]
    assert all(d.in_scope and "Julie Zhuo" in d.search_question for d in decisions)
    missing = [[name for name in invalid_names if normalize(name) not in normalize(d.search_question)] for d in decisions]
    summary = {
        "questions": 10, "exact_overlap_with_previous_68": 0,
        "qualitative_review": dict(Counter(r["status"] for r in notes.values())),
        "useful_evidence_cases": 6, "appropriate_domain_rejections": 2,
        "partial_comparisons": 1, "local_validation_failures": 1,
        "runtime_errors": sum(bool(r.get("error")) for r in runs.values()),
        "api_models": dict(Counter(c["requested_model"] for c in calls)),
        "failed_api_attempts": sum(not c.get("success") for c in calls),
        "reranker_fallbacks": sum(r.get("retrieval_metadata", {}).get("ranking_diagnostics", {}).get("fallback", False) for r in runs.values()),
        "out_of_domain_database_calls": sum(runs[i]["database_queries"] for i in ("fresh-08", "fresh-09")),
        "out_of_domain_transcript_calls": sum(runs[i]["transcript_queries"] for i in ("fresh-08", "fresh-09")),
        "selected_text_and_offsets_preserved": preserved,
        "archive_coverage_unchanged": raw["index_coverage"] == raw["post_run_index_coverage"],
        "identity_guard_bug": {"regex_matches": invalid_names, "missing_matches_per_valid_response": missing},
        "archive_metadata_audit": {"active_approved_guest_names_containing_fitzpatrick": []},
    }
    BASE.with_name(BASE.name + "_analysis.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# Ten fresh OpenRouter retrieval questions",
        "",
        "Ran the unchanged current Qwen scope router, BGE-M3 hybrid retrieval with concurrent semantic/keyword search, Voyage reranker, and 4,000-token context selection. Questions and rubrics were saved before the run; none exactly overlap the prior 68. No answer-generation calls or archive writes were made.",
        "",
        "## Outcome",
        "",
        "- Eight acceptable results: six with useful evidence and two appropriate out-of-domain rejections.",
        "- One partial comparison: Teresa Torres evidence was retrieved, but Rob Fitzpatrick's side was missing.",
        "- One failure: a local identity-preservation check rejected two otherwise valid Qwen routing responses.",
        "- There were zero failed HTTP/API attempts and no reranker fallbacks. The runtime failure was a local ProviderError.",
        "- The derivative and antibiotic-dose questions both made zero database, embedding, or reranking calls despite relevant-looking terms.",
        "- Stored passage text and offsets were preserved; archive coverage remained 303 episodes and 22,086 chunks.",
        "",
        "## Failure and partial result",
        "",
        "The Julie Zhuo delegation-and-football question was correctly split by Qwen: it retained delegation advice and removed the sports score. The local capitalized-name regex matched Explain Julie Zhuo as a name. Since the rewrite began What is Julie Zhuo's advice, the validator decided that this supposed name was missing and rejected it twice. It never opened the archive. This is a reproducible validator bug, not evidence that Qwen misunderstood the scope.",
        "",
        "A separate read-only metadata audit found no active approved guest name containing Fitzpatrick. The comparison therefore has direct Teresa Torres evidence only. This confirms a guest-coverage limit; it does not prove that no other transcript ever mentions Rob or his book. The missing side must be disclosed rather than synthesizing Rob's advice without a source.",
        "",
        "No production fix or successful retry was substituted into this test. The original failed trace is preserved. The immediate follow-up is to fix identity extraction so instruction verbs are not treated as names, with tests that still reject genuine guest changes.",
        "",
        "## Per-question evidence assessment",
        "",
        "| ID | Question | Outcome | Reviewed context sources | Finding |",
        "|---|---|---|---|---|",
    ]
    for case in raw["cases"]:
        note = notes[case["id"]]
        cells = [case["id"], case["question"], note["status"], ", ".join(note["evidence_source_ids"]) or "None", note["notes"]]
        lines.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    lines += ["", "Pass means selected evidence addresses the requested topic, or an appropriate rejection occurred. It does not mean exhaustive episode coverage or that a generated answer would attribute every claim correctly. In particular, some payment-recovery advice is spoken by host Lenny, not Patrick Campbell. This qualitative coding-agent review is not independent blind annotation.",
              "", "The companion raw JSON retains original questions, scope outputs, API traces, candidate passages, ranking scores, selected context, and query counts. Source IDs refer to each question's own context. The review and analysis JSON files retain the assessments and reproduced validator failure."]
    BASE.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
