"""Summarize frozen new-question traces and the saved qualitative evidence review."""
from collections import Counter
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).parent
BASE = ROOT / "results" / "openrouter_retrieval_new_20_2026-10-08"

def main():
    raw = json.loads(BASE.with_suffix(".json").read_text(encoding="utf-8"))
    audit = json.loads(BASE.with_name(BASE.name + "_review.json").read_text(encoding="utf-8"))
    old = json.loads((ROOT / "retrieval_questions_40.json").read_text(encoding="utf-8"))
    assert raw.get("finished_utc") and len(raw["cases"]) == len(raw["results"]) == 20
    assert not {c["question"] for c in old} & {c["question"] for c in raw["cases"]}
    runs = {r["case_id"]: r for r in raw["results"]}
    reviews = {r["id"]: r for r in audit["reviews"]}
    assert set(runs) == set(reviews)
    calls = [c for r in runs.values() for c in r["api_calls"]]
    preserved = True
    for run in runs.values():
        candidates = {p["chunk_id"]: p for p in run.get("candidates", [])}
        for p in run["passages"]:
            source = candidates[p["chunk_id"]]
            preserved &= all(p[k] == source[k] for k in ("text", "start_char", "end_char"))
    summary = {
        "questions": 20, "exact_overlap_with_old_40": 0,
        "completed_without_runtime_error": sum("error" not in r for r in runs.values()),
        "qualitative_review": dict(Counter(r["status"] for r in reviews.values())),
        "useful_evidence_cases": 12, "appropriate_clarification_or_domain_blocks": 4,
        "false_domain_rejections": 2, "false_domain_acceptances": 1,
        "nonempty_contexts": sum(bool(r["context"]) for r in runs.values()),
        "api_models": dict(Counter(c["requested_model"] for c in calls)),
        "failed_api_attempts": sum(not c.get("success") for c in calls),
        "reranker_fallbacks": sum(r["retrieval_metadata"]["ranking_diagnostics"].get("fallback", False) for r in runs.values()),
        "score_floor_rejections": sum(r["retrieval_metadata"]["ranking_diagnostics"].get("low_relevance_rejected", 0) for r in runs.values()),
        "selected_text_and_offsets_preserved": preserved,
        "archive_coverage_unchanged": raw["index_coverage"] == raw["post_run_index_coverage"],
        "median_search_seconds": round(median(r["seconds"] for r in runs.values() if r["api_calls"]), 2),
    }
    BASE.with_name(BASE.name + "_analysis.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# OpenRouter retrieval: 20 new questions",
        "",
        "Tested the existing revised pipeline without tuning it during the run: OpenRouter BGE-M3 embeddings, archive semantic/keyword candidate selection, Voyage reranking, and the initial 4,000-token context. No Llama answers were generated. No archive data was written. All 20 questions differ from the old 40 regression questions.",
        "",
        "The question set and rubrics were saved before the run. This is a new diagnostic set constructed and qualitatively reviewed by the coding agent, not an independently authored, blindly annotated benchmark. A pass requires evidence addressing the topic, or an appropriate clarification/rejection; nonempty results, identity membership, and scores alone are not passes.",
        "",
        "## Results",
        "",
        "- 20/20 runs completed without runtime errors.",
        "- 16 acceptable outcomes: 12 questions with useful supporting evidence and four appropriate ambiguity/unknown-person/domain blocks.",
        "- One partial evidence result: the Spanish positioning-versus-tagline question retrieved related positioning and sales-pitch material but no explicit distinction.",
        "- Three failures: two false domain rejections and one false domain acceptance.",
        "- Live API traces show 14 BGE-M3 embedding calls and 14 Voyage reranking calls. No failed API attempts, reranker fallbacks, or score-floor rejections.",
        "- All selected text and source offsets were preserved; archive coverage stayed at 303 episodes and 22,086 chunks.",
        "",
        "## Failures and limitations",
        "",
        '1. “¿Cómo puedo reducir la pérdida de clientes después de que se registran?” is a valid retention question, but the English vocabulary gate rejected it before search.',
        '2. “How do I separate a wise bet from a lucky win?” is a valid decision-quality question, but unfamiliar wording was also rejected before search.',
        '3. “What is the product of 137 and 29?” was falsely accepted because of the word product. It made three transcript queries and embedding/reranking calls; subscription, sponsor, and naming chunks entered context. Conservative score floors did not reject this unrelated set.',
        "",
        "The Spanish question naming April Dunford resolved her identity but did not retrieve an explicit positioning-versus-tagline distinction. An additional active-April-episode text search found zero chunks containing tagline or slogan. This shows insufficient answer evidence; it does not establish that the reranker discarded a known exact answer.",
        "",
        "Naomi was initially expected by the test author to resolve to Naomi Ionita, but the catalog audit found Naomi Gleit too. Its metadata-only clarification is therefore appropriate. The frozen question and original expectation remain in the dataset. Brian similarly matches Chesky, Tolkin, and Balfour; the system correctly did not guess.",
        "",
        "Useful evidence was found for feedback, pre-mortems, empowered teams, growth motions, strategy versus goals, multi-person decisions, design sprints, misspelled Teresa Torres, interviews excluding Teresa, retention diagnosis, sample ratio mismatch, and the supported PR/FAQ part of a mixed weather request.",
        "",
        "Mixed sponsor text and peripheral passages still enter context. For example, Bill Carr's context includes a Wix sponsor segment, and the Rumelt result includes Jag Duggal paraphrasing Rumelt. These passages must retain their actual speaker attribution. Text preservation does not mean every chunk has complete sentence boundaries or that the context exhausts the episode.",
        "",
        "The three failed questions were not used to modify the pipeline in this evaluation. Next priorities are semantic/multilingual domain detection and an evidence-sufficiency rejection stage. The 20-case outcome is a diagnostic result, not an accuracy probability or a guarantee about generated answers.",
        "",
        "## Per-question evidence review",
        "",
        "| ID | Question | Outcome | Context sources used in review | Finding |",
        "|---|---|---|---|---|",
    ]
    for case in raw["cases"]:
        review = reviews[case["id"]]
        cells = [case["id"], case["question"], review["status"], ", ".join(review["evidence_source_ids"]) or "None", review["notes"]]
        lines.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    lines += ["", "Source IDs above refer to each question's saved context in the companion raw JSON. That file also retains candidate passages, API traces, scores, query plans, and database query counts. The review JSON stores the qualitative assessments and catalog audit separately."]
    BASE.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
