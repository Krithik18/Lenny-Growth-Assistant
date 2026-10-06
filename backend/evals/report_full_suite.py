"""Summarize saved measurements without conflating retrieval and answer quality."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics

OUT = Path(__file__).parent / "results"


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def main():
    index = read("full_index.json")
    cases = read("full_cases.json")
    retrieval = read("full_retrieval.json")
    answers = read("full_answers.json")
    broad = read("broad_answers.json")
    regression = read("database_retrieval_full.json")
    api = read("full_api.json")
    lines = ["# Full transcript evaluation", "", "## Indexed knowledge", "",
        f"- Approved ZIP: `{index['archive_sha256']}`.",
        f"- Transcript files fully indexed: **{index['episodes']} / 303**.",
        f"- Chunks: **{index['chunks']:,}**; compatible OpenAI embeddings: **{index['embeddings']:,}**.",
        f"- Distinct transcript bodies: {cases['unique_transcript_bodies']} (exact duplicates remain traceable to their ZIP members).",
        "- Embeddings: text-embedding-3-small, 1,536 dimensions. Answers and automated evaluation: gpt-6-luna only.",
        "- Archive filenames and source metadata are preserved, including existing inconsistencies.",
        "", "## Retrieval only", "",
        "One source-derived question per transcript file. Labels were generated from deterministic transcript excerpts;",
        "evidence anchors were verified against the source. These are synthetic evaluation labels, not independent human gold.",
        "An exact anchor in a duplicate source counts as a hit. A miss may still retrieve other valid evidence.",
        "This stage tests initial semantic retrieval separately from generation and missing-topic refinement.", ""]
    summary = retrieval["summary"]
    lines += [f"Completed: {summary['completed']} / {summary['cases']}; errors: {summary['errors']}.", "",
        "| Metric | Result |", "|---|---:|",
        f"| Expected evidence in top 5 | {summary['hit_at_5']:.1%} |",
        f"| Expected evidence in top 20 | {summary['hit_at_20']:.1%} |",
        f"| Expected evidence in 2,000-token initial context | {summary['context_hit']:.1%} |",
        f"| MRR within top 20 | {summary['mrr_at_20']:.3f} |",
        f"| Median embedding + database retrieval time | {summary['median_seconds']:.2f} seconds |", "",
        "| Requested question type | Cases | Hit at 5 | Hit at 20 |", "|---|---:|---:|---:|"]
    groups = defaultdict(list)
    for row in retrieval["results"]:
        if "error" not in row:
            groups[row["category"]].append(row)
    for category, rows in sorted(groups.items()):
        lines.append(f"| {category} | {len(rows)} | {statistics.mean(r['hit_at_5'] for r in rows):.1%} | {statistics.mean(r['hit_at_20'] for r in rows):.1%} |")
    lines += ["", "## Answer checks", "",
        "Forty questions, selected deterministically across the eight requested categories before examining retrieval results.",
        "Each is run twice: with a fixed reference excerpt, and through the real retrieval-and-answer service.",
        "The scores below are advisory GPT-6 Luna judgments. Using the same model as judge can introduce bias;",
        "they must not be presented as human-certified accuracy. Check individual answers and evidence in the JSON reports.", "",
        "Selected source checks and interpretation: [source_review.md](source_review.md). Some judge flags conflate",
        "reference-detail omissions with unsupported claims; preserve raw judgments rather than treating them as factual verdicts.", "",
        "| Stage | Completed | Grounded | Addresses question | Expected points | Appropriate evidence limits |",
        "|---|---:|---:|---:|---:|---:|"]
    for mode, row in answers["summary"].items():
        lines.append(f"| {mode} | {row['completed']}/{row['planned']} | {row['grounded']:.1%} | {row['addresses_question']:.1%} | {row['expected_points_covered']:.1%} | {row['correct_abstention']:.1%} |")
    valid = [r for r in broad["results"] if "review" in r]
    lines += ["", "## Broader user scenarios", "",
        "Thirty authored prompts cover comparisons, multipart questions, practical advice, definitions, frameworks,",
        "examples, numerical facts/calculations, false premises, out-of-domain questions, instruction overrides,",
        "ambiguity, partial evidence, Spanish, typos, code requests, essay requests, exhaustive lists, current facts,",
        "quotes, summaries, and step-by-step processes.", "",
        f"Completed: {len(valid)}/30. Advisory rubric passes: {sum(r['review']['fulfills_rubric'] for r in valid)}/{len(valid)}.",
        f"Advisory grounded judgments: {sum(r['review']['grounded'] for r in valid)}/{len(valid)}.", "",
        "| Scenario | Coverage | Rubric | Grounded |", "|---|---|---|---|"]
    for row in sorted(broad["results"], key=lambda r:r["id"]):
        if "error" in row:
            lines.append(f"| {row['id']} | Error | {row['error']} | — |")
        else:
            lines.append(f"| {row['id']} | {row['result']['answer']['coverage']} | {'pass' if row['review']['fulfills_rubric'] else 'review'} | {'pass' if row['review']['grounded'] else 'review'} |")
    lines += ["", "## Cases requiring review", ""]
    for row in answers["results"]:
        if "error" in row:
            lines.append(f"- {row['id']} ({row['mode']}): {row['error']}")
        elif not all(row["judgment"][key] for key in ("grounded", "addresses_question", "expected_points_covered", "correct_abstention")):
            lines.append(f"- {row['id']} ({row['mode']}): {row['judgment']['explanation']}")
    for row in valid:
        if not all(row["review"][key] for key in ("grounded", "fulfills_rubric", "citation_support")):
            lines.append(f"- {row['id']}: {row['review']['explanation']}")
    lines += ["", "## Operational checks", "",
        "- Local backend suite: 54 passed.",
        f"- Original ten retrieval regressions against the full archive: {regression['exact_anchor_hits']}/10 exact-anchor hits at five (the earlier five-file pilot scored 9/10). Corpus expansion changes competing results.",
        f"- Embedding-table RLS enabled: {regression['embedding_table_rls']}.",
        f"- Running API: health ready; retrieval HTTP {api['retrieve_status']}; answer HTTP {api['ask_status']}; invalid request HTTP {api['invalid_request_status']}.",
        f"- Chesky multipart API answer: {api['result']['answer']['coverage']}, using {api['result']['model']}.",
        "- Migration 0004 applied. Alembic reports no new upgrade operations; query-plan check confirms use of the HNSW index.",
        "- The saved EXPLAIN was taken during concurrent evaluation and is a diagnostic snapshot, not an isolated latency benchmark.",
        "", "## Limits", "",
        "- Testing covers every transcript with one question, not every passage or possible question.",
        "- Full ingestion broadens source coverage; it does not guarantee perfect retrieval or factual answers.",
        "- Citation validation checks source IDs; the semantic judgments above are fallible model evaluations.",
        "- Source metadata errors cannot be corrected reliably without additional source verification.",
        "- Initial context remains bounded; exhaustive corpus questions and multi-turn references need additional product work.",
        "- HNSW approximate vector and GIN keyword indexes are used; recall and performance need monitoring under production traffic.",
        "- Reports are snapshots; model output can vary between runs.", ""]
    (OUT / "full_evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    print(OUT / "full_evaluation.md")


if __name__ == "__main__":
    main()
