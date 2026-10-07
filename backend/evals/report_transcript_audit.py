"""Build a complete, reproducible Markdown report from the all-transcript audit."""

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

OUT = Path(__file__).parent / "results"


def pct(value):
    return f"{100 * value:.1f}%"


def complete(result):
    points = [p for p in result["review"]["points"] if p["reference_supported"]]
    return bool(points) and all(p["answer_covered"] for p in points)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="full303_rerank_concurrent_20261007_resumed")
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    directory = (args.work_dir or OUT) / args.run
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    if summary["retrieval_completed"] != 303 or any(s["completed"] != 303 for s in summary["by_budget"].values()):
        raise ValueError("Finish all 303 cases at every budget before producing the final report")
    cases = sorted([json.loads(p.read_text(encoding="utf-8")) for p in directory.glob("*.json")
                    if p.stem not in {"metadata", "summary", "progress", "index_status", "comparison", "reference_cases"}], key=lambda r: r["id"])
    if len(cases) != 303:
        raise ValueError("Require exactly one completed result per transcript")
    references = json.loads((OUT / "full_cases.json").read_text(encoding="utf-8"))
    (directory / "reference_cases.json").write_text(json.dumps(references, indent=2, ensure_ascii=False), encoding="utf-8")
    questions = ["# Questions tested across all 303 transcripts", "",
        "Each question was tested with the same retrieved evidence at 2,000, 4,000, and 6,000 context tokens.", ""]
    for index, row in enumerate(sorted(references["cases"], key=lambda r: r["id"]), 1):
        questions += [f"## {index}. {row['id']}", "", row["question"], "", "Expected answer points:", ""]
        questions.extend(f"- {point}" for point in row["expected_points"])
        questions += ["", f"[Evidence and answers at each budget]({row['id']}.json)", ""]
    (directory / "questions.md").write_text("\n".join(questions), encoding="utf-8")
    budgets = sorted(map(int, summary["by_budget"]))
    baseline = str(budgets[0])
    # Reference support should not depend on budget, but fallible judges can
    # disagree. Use one shared set of unanimously supported points for paired
    # completeness comparisons, and keep the original per-budget stats intact.
    common_points = {}
    for row in cases:
        reviews = [{p["point_index"]: p for p in row["budgets"][str(b)]["review"]["points"]} for b in budgets]
        common_points[row["id"]] = [i for i in reviews[0] if all(r[i]["reference_supported"] for r in reviews)]

    def comparable_complete(row, budget):
        indices = common_points[row["id"]]
        points = {p["point_index"]: p for p in row["budgets"][str(budget)]["review"]["points"]}
        return bool(indices) and all(points[i]["answer_covered"] for i in indices)

    comparable_cases = [r for r in cases if common_points[r["id"]]]
    comparable_rates = {str(b): statistics.mean(comparable_complete(r, b) for r in comparable_cases) for b in budgets}
    complete_grounded_rates = {str(b): statistics.mean(comparable_complete(r, b)
        and r["budgets"][str(b)]["review"]["grounded"]
        and r["budgets"][str(b)]["review"]["addresses_question"] for r in comparable_cases) for b in budgets}
    ranking_groups = {}
    for name, successful in (("successful_reranking", True), ("reranking_fallback", False)):
        group = [r for r in comparable_cases if any(c["kind"] == "evidence_order" and c.get("valid_ranking", False)
            for c in r["trace"]["provider_calls"]) == successful]
        ranking_groups[name] = {"cases": len(group), "completeness_by_budget": {
            str(b): statistics.mean(comparable_complete(r, b) for r in group) if group else None for b in budgets}}
    stages = {}
    for kind in ("embedding", "evidence_order"):
        calls = [c for row in cases for c in row["trace"]["provider_calls"] if c["kind"] == kind]
        stages[kind] = {"calls": len(calls), "median_seconds": statistics.median(c["seconds"] for c in calls)}
    for kind in ("semantic", "keyword", "neighbors"):
        calls = [c for row in cases for c in row["trace"]["sql_calls"] if c["kind"] == kind]
        stages[kind] = {"calls": len(calls), "median_seconds": statistics.median(c["seconds"] for c in calls)}
    paired = {}
    for budget in map(str, budgets[1:]):
        transitions = Counter((comparable_complete(r, baseline), comparable_complete(r, budget)) for r in comparable_cases)
        paired[budget] = {"improved": transitions[False, True], "regressed": transitions[True, False],
                          "complete_at_both": transitions[True, True], "incomplete_at_both": transitions[False, False]}
    usage = {}
    for budget in map(str, budgets):
        calls = [c for row in cases for c in row["budgets"][budget]["trace"]["provider_calls"]
                 if c["kind"] == "grounded_answer" and c.get("usage")]
        usage[budget] = {"answer_calls_with_usage": len(calls), "input_tokens": sum(c["usage"].get("input_tokens", 0) for c in calls),
                        "output_tokens": sum(c["usage"].get("output_tokens", 0) for c in calls),
                        "median_context_tokens": statistics.median(row["budgets"][budget]["used_context_tokens"] for row in cases)}
    inconsistent_reference = []
    inconsistent_retrieval = []
    for row in cases:
        assessments = [{p["point_index"]: p for p in row["budgets"][str(b)]["review"]["points"]} for b in budgets]
        if any(len({review[i]["reference_supported"] for review in assessments}) > 1 for i in assessments[0]):
            inconsistent_reference.append(row["id"])
        if any(len({review[i]["retrieved_supported"] for review in assessments}) > 1 for i in assessments[0]):
            inconsistent_retrieval.append(row["id"])
    comparison = {"paired_completeness": paired, "comparable_cases": len(comparable_cases),
                  "comparable_completeness_by_budget": comparable_rates,
                  "complete_grounded_by_budget": complete_grounded_rates,
                  "stage_timings": stages, "answer_usage_by_budget": usage,
                  "reference_judge_disagreements": inconsistent_reference,
                  "retrieval_judge_disagreements": inconsistent_retrieval}
    comparison["ranking_groups"] = ranking_groups
    failures = Counter((c["kind"], c["status"]) for row in cases
        for trace in [row["trace"], *(r["trace"] for r in row["budgets"].values())]
        for c in trace["provider_calls"] if c["status"] != "completed")
    retries = sum(bool(row.get("retry_history")) for row in cases)
    stage_retry_errors = Counter(error for row in cases for attempt in row.get("retry_history", [])
        for error in attempt["budget_errors"].values() if error)
    comparison["provider_failed_attempts"] = [{"kind": kind, "status": status, "count": count}
        for (kind, status), count in sorted(failures.items())]
    comparison["cases_with_stage_retries"] = retries
    comparison["failed_budget_stages_before_retry"] = dict(stage_retry_errors)
    (directory / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    best_budget = max(budgets, key=lambda b: comparable_rates[str(b)])
    baseline_rate = comparable_rates[baseline]
    lines = ["# Full 303-transcript audit and context-budget comparison", "",
        f"Started: {metadata['started_at_ist']} (India time).", "",
        "## Main findings", "",
        "- Completed all 303 questions at all three budgets: 909 evaluated answers, with reranking enabled.",
        "- Comparable answer completeness: " + "; ".join(f"{b:,} tokens = {pct(comparable_rates[str(b)])}" for b in budgets) + ".",
        "- Complete, grounded, and addresses the question: " + "; ".join(f"{b:,} tokens = {pct(complete_grounded_rates[str(b)])}" for b in budgets) + ".",
        f"- The highest observed completeness was at {best_budget:,} tokens, {100 * (comparable_rates[str(best_budget)] - baseline_rate):.1f} percentage points above 2,000. Automated judgments are advisory.",
        f"- Exact source evidence reached the returned top 20 for {pct(summary['hit_at_20'])} of questions. More context cannot restore evidence absent from these results.",
        f"- Reranking fell back in {summary['rerank_fallback_cases']}/303 cases; missing details also occurred when evidence was already in context.",
        "- Application defaults remain unchanged. Review evidence selection, ranking failures, and generation omissions before choosing a new default.", "",
        "## Scope and configuration", "",
        "- One source-derived question for each of all 303 transcript files; 909 initial answers across three budgets.",
        "- Live index checked: 303 episodes, 22,086 chunks, and 22,086 compatible embeddings.",
        "- All reference anchors and excerpts verified against the approved ZIP before testing.",
        "- Reranking enabled; semantic and keyword SQL searches execute concurrently on separate connections.",
        "- GPT-6 Luna generates, reranks, and judges; text-embedding-3-small uses 1,536 dimensions.",
        "- Retrieve/rerank once per question, then reuse the same returned top 20 for 2,000/4,000/6,000-token contexts.",
        "- Initial answers only: missing-topic refinement is disabled for this controlled comparison. The application default is not changed by this audit.",
        "- Four question jobs run concurrently; three budgets per question run concurrently. Timings are under this development workload.", "",
        "[All 303 test questions](questions.md) · [Original source-derived reference labels and excerpts](reference_cases.json)", "",
        "## What is working", "",
        "The complete approved collection is searchable, and every test question's reference anchor exists in its source. "
        "Search and reranking preserve source IDs and original text; the answering provider validates citation IDs. "
        "That citation validation checks identity, not whether every claim is semantically supported.", "",
        f"Expected exact evidence appeared in the first five results for **{pct(summary['hit_at_5'])}** of questions "
        f"and in the first 20 for **{pct(summary['hit_at_20'])}**. Alternative valid passages can still answer a question when the exact anchor is absent.", "",
        "## Context-budget results", "",
        "| Metric | " + " | ".join(f"{b:,} tokens" for b in budgets) + " |",
        "|---|" + "---:|" * len(budgets)]
    metrics = [("Completed questions", lambda s: f"{s['completed']}/303"),
        ("Exact evidence in supplied context", lambda s: pct(s["context_hit"])),
        ("All expected points covered (per-budget judge)", lambda s: pct(s["all_expected_points_covered"])),
        ("Claims grounded in cited evidence", lambda s: pct(s["advisory_judgments"]["grounded"])),
        ("Addresses the question", lambda s: pct(s["advisory_judgments"]["addresses_question"])),
        ("Appropriate evidence limits", lambda s: pct(s["advisory_judgments"]["correct_abstention"])),
        ("Median answer generation", lambda s: f"{s['median_answer_seconds']:.2f} s"),
        ("Median retrieval + initial answer", lambda s: f"{s['median_initial_response_seconds']:.2f} s"),
        ("Silent reference-point omissions", lambda s: str(s["silent_incomplete_cases"]))]
    for label, value in metrics:
        lines.append("| " + label + " | " + " | ".join(value(summary["by_budget"][str(b)]) for b in budgets) + " |")
    lines.append("| Completeness using the same valid reference points | " + " | ".join(pct(comparable_rates[str(b)]) for b in budgets) + " |")
    lines.append("| Complete, grounded, and addresses the question | " + " | ".join(pct(complete_grounded_rates[str(b)]) for b in budgets) + " |")
    lines += ["", "Completeness measures all source-supported reference points; it is stricter than the model's own coverage flag. "
              f"The comparable completeness row uses {len(comparable_cases)} questions with at least one reference point "
              "supported by the judges at every budget, applying that same point set to all budgets. "
              "Silent omissions mean the answer marked itself complete while the judge identified missing reference details; "
              "not every such detail necessarily represents a separate requested subquestion.", "",
              "### Paired improvements and regressions", "",
              "| Larger budget versus 2,000 | Became complete | Became incomplete | Complete at both | Incomplete at both |",
              "|---|---:|---:|---:|---:|"]
    for budget, counts in paired.items():
        lines.append(f"| {int(budget):,} | {counts['improved']} | {counts['regressed']} | {counts['complete_at_both']} | {counts['incomplete_at_both']} |")
    lines += ["", "### Completeness by reranking outcome", "",
        "| Ranking outcome | Comparable questions | " + " | ".join(f"{b:,} tokens" for b in budgets) + " |",
        "|---|---:|" + "---:|" * len(budgets)]
    for name, stats in ranking_groups.items():
        values = [pct(stats["completeness_by_budget"][str(b)]) if stats["cases"] else "n/a" for b in budgets]
        lines.append("| " + name.replace("_", " ") + f" | {stats['cases']} | " + " | ".join(values) + " |")
    lines += ["", "These are different sets of questions, so their rates are diagnostic; they do not establish the causal benefit of reranking."]
    lines += ["", "The paired results show individual changes, not just averages. Model output and judging can vary; "
              "a larger budget is not guaranteed to improve every answer.", "",
              "A reviewed example is [Asha Sharma's planning question](asha-sharma.json): the 2,000-token context "
              "excluded the passage describing quarterly OKRs and four-to-six-week squad goals, and the answer flagged "
              "those details as unavailable. The 4,000-token context included that passage and the answer covered them. "
              "This is a context-selection improvement; the underlying retrieval was identical. Its reranking response "
              "was invalid and the service used candidate order, so it also illustrates the need to repair evidence "
              "ordering before relying on larger contexts to compensate.", "",
              "## What went wrong", "",
              "Each omitted expected point is assigned to the earliest observed failure stage. Counts below are points, "
              "not unique questions, and the same question can have several failure types.", "",
              "| Failure stage | " + " | ".join(f"{b:,} tokens" for b in budgets) + " |",
              "|---|" + "---:|" * len(budgets)]
    labels = {"retrieval_gap": "Supported in source, absent from returned top 20",
              "context_selection_gap": "In top 20, excluded from supplied context",
              "generation_omission": "Available in context, omitted from answer",
              "reference_label_needs_review": "Synthetic reference point not supported by reference excerpt"}
    for issue, label in labels.items():
        lines.append("| " + label + " | " + " | ".join(str(summary["by_budget"][str(b)]["point_issue_counts"].get(issue, 0)) for b in budgets) + " |")
    lines += ["", f"Reranking fell back to candidate order in **{summary['rerank_fallback_cases']} / 303 cases**. "
              "Timeouts and invalid ranking responses are preserved in the per-case trace. Keeping reranking enabled does not mean every call succeeded.", "",
              f"Failed stages were retried in **{retries} cases**, reusing successful answers and retrieval. "
              "Incomplete evaluator responses were retried with a 4,000-token evaluator output limit; "
              "the application answer output limit stayed at 1,800 tokens. These operational failures are not counted as evidence gaps.", "",
              "Recorded budget-stage errors before the final retry pass: " +
              (", ".join(f"{name}: {count}" for name, count in sorted(stage_retry_errors.items())) or "none") +
              ". ProviderError can indicate a provider request failure or an answer validation failure; the request traces identify the affected stage. RuntimeError generally records an incomplete evaluation response. "
              "Earlier interrupted attempts remain in their original result directories; provider traces are retained in the recovered cases.", "",
              "### Evidence gaps and response wording", "",
              "These source-derived questions deliberately have evidence in the approved archive. A retrieval or context gap "
              "must not be described as proof that the information is absent from all transcripts. Appropriate response wording "
              "is 'I could not find support for this detail in the retrieved evidence,' while answering the supported parts. "
              "Existing partial/unsupported flags and missing_topics are checked, but the current assistant can miss a gap "
              "and incorrectly label an incomplete answer complete. This audit measures that behavior before remediation.", "",
              "Genuine corpus-wide absence is not established by these tests. Verifying that would require separate questions "
              "and a broader source investigation; no absence claim is inferred from a search miss.", "",
              "### Representative cases to inspect", ""]
    for issue, label in labels.items():
        chosen = [r for r in cases if issue in r["budgets"][baseline]["point_issues"]][:4]
        if chosen:
            lines += [f"**{label}:**", ""]
            for row in chosen:
                result = row["budgets"][baseline]
                explanations = [p["explanation"] for p in result["review"]["points"]
                                if row["budgets"][baseline]["point_issues"][result["review"]["points"].index(p)] == issue]
                lines.append(f"- [{row['id']}]({row['id']}.json): {' '.join(explanations)}")
            lines.append("")
    lines += ["## Latency and token usage", "",
              f"Median retrieval (including reranking): **{summary['median_retrieval_seconds']:.2f} seconds**.", "",
              "| Component | Median observed duration |", "|---|---:|"]
    for kind, stats in stages.items():
        lines.append(f"| {kind} | {stats['median_seconds']:.2f} s |")
    lines += ["", "Component medians do not add to the overall median. Semantic and keyword searches overlap; "
              "SQL timings include database round-trip time. Context-budget response timings exclude the judge but were "
              "measured while other evaluations were active. They are not isolated production latency benchmarks.", "",
              "| Budget | Median actual transcript tokens supplied | Answer input tokens total | Answer output tokens total |",
              "|---|---:|---:|---:|"]
    for budget, stats in usage.items():
        lines.append(f"| {int(budget):,} | {stats['median_context_tokens']:.0f} | {stats['input_tokens']:,} | {stats['output_tokens']:,} |")
    lines += ["", "Usage totals above cover answer-generation calls only; reranking and automated evaluation also consume tokens. "
              "No monetary cost is inferred from unverified model pricing. Answer output limit remains 1,800 tokens.", "",
              "## Interpretation limits", "",
              "- One question per transcript is coverage of files, not every passage or possible user question.",
              "- Synthetic reference labels and same-model judging are advisory; the point classifications are not independent human findings.",
              f"- Judges disagreed across budgets about reference support in {len(inconsistent_reference)} cases and about support "
              f"in the unchanged top-20 retrieval in {len(inconsistent_retrieval)} cases. These require source review.",
              "- Source anchors are deterministically verified, but exact-anchor misses can have valid alternative evidence.",
              "- HNSW retrieval is approximate. Duplicate source files remain traceable; identical text consumes one selection slot.",
              "- No assertion that missing information is absent from the entire corpus is made.",
              "- App defaults and response behavior were not changed by this experiment; remediation follows review of these results.", "",
              "Two attempts stopped on Windows checkpoint filesystem errors in the OneDrive folder. Completed stages were preserved "
              "and resumed in a working directory outside OneDrive after improving task cleanup. Interruptions/client-closed errors are "
              "operational failures, not transcript retrieval misses. Completed-stage timing data is retained; retry calls "
              "remain visible in the traces.", "",
              "## All 303 cases", "",
              "Every link contains the question, reference points, ranked passages, each budget's actual evidence/answer/judgment, and request timing/usage traces.", "",
              "| Transcript/test case | " + " | ".join(f"{b:,}: completeness / issues" for b in budgets) + " |",
              "|---|" + "---|" * len(budgets)]
    for row in cases:
        cells = []
        for budget in map(str, budgets):
            result = row["budgets"][budget]
            issues = sorted(set(result["point_issues"]) - {"covered"})
            if not result["review"]["grounded"]:
                issues.append("grounding")
            cells.append(("complete" if complete(result) else "incomplete") + ("; " + ", ".join(issues) if issues else ""))
        lines.append(f"| [{row['id']}]({row['id']}.json) | " + " | ".join(cells) + " |")
    lines += ["", "## Reproduce or resume", "", "```powershell",
              f".\\.venv\\Scripts\\python.exe -m evals.transcript_audit --run {args.run} --workers 4 --budgets 2000 4000 6000",
              f".\\.venv\\Scripts\\python.exe -m evals.report_transcript_audit --run {args.run}", "```", "",
              "Run from backend. Completed stages are reused; failed stages resume. Code/configuration hashes prevent "
              "silently mixing different implementations in the same run. Raw failures and retries remain in traces.", ""]
    output = directory / "report.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
