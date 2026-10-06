"""Summarize the fixed-budget experiment without rewriting the original report."""
import json
from pathlib import Path
import statistics

OUT = Path(__file__).parent / "results"


def main():
    directory = OUT / "evidence_v4_2000"
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    if summary["completed"] != 40 or summary["errors"]:
        raise ValueError("Finish the 40-question experiment before reporting")
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in directory.glob("*.json") if p.name != "summary.json"]
    old = {r["id"]: r for r in json.loads((OUT / "full_retrieval.json").read_text(encoding="utf-8"))["results"]}
    old_median = statistics.median(old[r["id"]]["seconds"] for r in rows)
    initial_latency = statistics.median(r["retrieval_seconds"] + r["answer_seconds"] for r in rows)
    pct = lambda value: f"{value * 100:.1f}%"
    baseline = summary["historical_same_questions"]
    judgments = summary["initial_answer_judgments"]
    lines = ["# Evidence selection at a fixed 2,000-token answer context", "",
        "## Changes", "",
        "- Search semantic and keyword candidates on the first retrieval, preserving the semantic top 20.",
        "- Include immediate neighbors around a bounded set of strong hits to recover continuations.",
        "- Ask GPT-6 Luna to rank up to 50 original passages against the question before context packing.",
        "- Validate the returned ID permutation; preserve original candidate order on failure or timeout.",
        "- Require answer coverage of concrete steps, examples, numbers, and qualifications, and recheck evidence before claiming a gap.",
        "- Rank keyword candidate IDs before loading their vectors; no database migration or reindexing required.", "",
        "## Same-question retrieval comparison", "",
        "40 deterministically selected questions, five per category, identical to the earlier answer subset. "
        "The baseline is historical, not a concurrent control. This is not a rerun of all 303 questions.", "",
        "| Metric | Historical semantic search | New selection |", "|---|---:|---:|",
        *[f"| {label} | {pct(baseline[key])} | {pct(summary[key])} |" for key, label in [
            ("hit_at_5", "Expected evidence in top 5"), ("hit_at_20", "Expected evidence in top 20"),
            ("context_hit", "Expected evidence in 2,000-token context")]],
        f"| Median retrieval time | {old_median:.2f} s | {summary['median_retrieval_seconds']:.2f} s |", "",
        f"Median initial retrieval + answer time: **{initial_latency:.2f} seconds** (excludes evaluation judging). "
        "Runs used two concurrent cases; these are development timings, not isolated production benchmarks. "
        "Reranking adds a model call and reads up to 50 candidate chunks, separate from the answering model's 2,000-token evidence budget.", "",
        "## Initial-answer checks", "",
        "| Advisory automated judgment | Pass rate |", "|---|---:|",
        *[f"| {label} | {pct(judgments[key])} |" for key, label in [
            ("grounded", "Claims grounded in cited evidence"), ("addresses_question", "Addresses question"),
            ("expected_points_covered", "All expected reference points covered"),
            ("correct_abstention", "Appropriate evidence limits")]], "",
        "These checks use the initial answer only, with no second-round evidence expansion. "
        "The existing service may still add up to 2,000 tokens through its optional missing-topic refinement. "
        "The original end-to-end answer report used that service and a different judge rubric, so its percentages "
        "are not a direct before/after answer-quality comparison.", "",
        "The revised rubric separately checks reference completeness and justified abstention. A reference detail "
        "missing from retrieved context still counts against completeness, but an honest statement that it is missing "
        "is not an incorrect abstention. GPT-6 Luna is also the judge; these judgments are advisory, not human-certified accuracy.", "",
        "## Remaining cases for review", ""]
    for row in sorted(rows, key=lambda r: r["id"]):
        if not all(row["judgment"][key] for key in ("grounded", "expected_points_covered", "addresses_question", "correct_abstention")):
            lines.append(f"- **{row['id']}**: {row['judgment']['explanation']}")
    lines += ["", "## Validation and next experiment", "",
        "- Local backend suite: 69 passed. Git whitespace check passed.",
        "- Original evaluation reports are preserved; intermediate runs and raw judgments are separate.",
        "- The default initial answer context remains 2,000 tokens; no larger-budget answer experiment has been run.",
        "- This development subset has been inspected during implementation; use held-out questions and a full-corpus rerun before generalizing.",
        "- Larger contexts cannot recover evidence absent from the candidate pool, and do not guarantee the model will use every detail.", "",
        "For later controlled budget comparisons, reuse the saved ranked evidence:", "", "```powershell",
        ".\\.venv\\Scripts\\python.exe -m evals.evidence_selection --answers --budget 4000 --reuse-ranked-from evidence_v4_2000",
        ".\\.venv\\Scripts\\python.exe -m evals.evidence_selection --answers --budget 6000 --reuse-ranked-from evidence_v4_2000",
        "```", "", "Run from `backend`. These commands are documented for later use; they have not been executed.", ""]
    output = OUT / "evidence_selection.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
