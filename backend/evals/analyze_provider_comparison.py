"""Offline contract/provenance analysis of the saved live comparison."""

from collections import Counter
import json
from pathlib import Path
from statistics import mean, median

from app.rag.context import build_context
from app.schemas.answer import GroundedAnswer
from app.schemas.retrieval import RetrievedPassage
from evals.provider_comparison_live import OUT, CASE_IDS


def content(call):
    result = call.get("response", {})
    if call["path"] == "chat/completions":
        return result.get("choices", [{}])[0].get("message", {}).get("content", "")
    return "".join(p.get("text", "") for item in result.get("output", [])
                   if item.get("type") == "message" for p in item.get("content", [])
                   if p.get("type") == "output_text")


def contexts(run):
    retrieved = run.get("retrievals", [])
    if not retrieved:
        return [{}]
    initial = build_context([RetrievedPassage.model_validate(p) for p in retrieved[0]["passages"]])
    seen = {p.chunk_id for p in initial.values()}
    groups = [[RetrievedPassage.model_validate(p) for p in group["passages"]] for group in retrieved[1:]]
    candidates = []
    for rank in range(10):
        for group in groups:
            if rank < len(group) and group[rank].chunk_id not in seen:
                candidates.append(group[rank])
                seen.add(group[rank].chunk_id)
    expanded = dict(initial)
    for p in build_context(candidates, token_budget=2000).values():
        expanded[f"S{len(expanded) + 1}"] = p
    return [initial, expanded]


def validation_issues(raw, sources):
    try:
        answer = GroundedAnswer.model_validate_json(raw, strict=True)
    except ValueError as error:
        details = []
        if hasattr(error, "errors"):
            details = [".".join(map(str, e["loc"])) + ": " + e["type"]
                       for e in error.errors(include_input=False, include_url=False)]
        return ["schema_or_json_invalid: " + "; ".join(details or [type(error).__name__])]
    issues = []
    if answer.insufficient_evidence != (answer.coverage != "complete"):
        issues.append("coverage_flag_inconsistent")
    if bool(answer.missing_topics) != (answer.coverage != "complete"):
        issues.append("missing_topics_inconsistent")
    if any(not t.strip() for t in answer.missing_topics):
        issues.append("empty_missing_topic")
    if answer.coverage == "unsupported":
        if answer.sections or answer.summary_citation_ids:
            issues.append("unsupported_contains_claims_or_citations")
    else:
        if not answer.summary.strip() or not answer.sections or not answer.summary_citation_ids:
            issues.append("answer_or_summary_citations_missing")
        section_ids = {cid for s in answer.sections for cid in s.citation_ids}
        missing = sorted(set(answer.summary_citation_ids) - section_ids)
        if missing:
            issues.append("summary_citations_absent_from_sections: " + ", ".join(missing))
        if any(not s.heading.strip() or not s.content.strip() or not s.citation_ids for s in answer.sections):
            issues.append("empty_section_or_section_citations")
        unknown = sorted(section_ids - sources.keys())
        if unknown:
            issues.append("unknown_source_ids: " + json.dumps(unknown))
    return issues


def main():
    report = json.loads(OUT.read_text(encoding="utf-8"))
    summary = {"index_coverage": report.get("post_run_index_coverage", report["index_coverage"]), "case_order": CASE_IDS,
               "providers": {}, "rows": []}
    for run in report["results"]:
        evidence = contexts(run)
        answer_index = 0
        diagnostics = []
        stages = []
        for call in run["api_calls"]:
            if call["path"] == "embeddings":
                stage = "embedding"
            elif call["path"] == "rerank":
                stage = "rerank"
            else:
                raw = content(call)
                try:
                    decoded = json.loads(raw)
                except (ValueError, TypeError):
                    decoded = {}
                stage = "rerank" if isinstance(decoded, dict) and "passage_ids" in decoded else "answer"
                if stage == "answer":
                    diagnostics.append({"answer_attempt": answer_index + 1,
                        "issues": validation_issues(raw, evidence[min(answer_index, len(evidence) - 1)]),
                        "raw_answer": decoded})
                    answer_index += 1
            stages.append({"stage": stage, **{key: call.get(key) for key in
                ("path", "requested_model", "returned_model", "served_provider", "endpoint", "http_status", "seconds")}})
        retrieval_provider_matches = all(r["provider"] == run["provider"] for r in run["retrievals"])
        summary["rows"].append({
            "case_id": run["case_id"], "provider": run["provider"], "status": run.get("http_status"),
            "seconds": run["seconds"], "coverage": run.get("checks", {}).get("coverage"),
            "sources": run.get("checks", {}).get("source_count"),
            "retrieval_provider_matches": retrieval_provider_matches,
            "retrieval_seconds": [r["seconds"] for r in run["retrievals"]],
            "answer_diagnostics": diagnostics, "api_stages": stages,
        })
    for provider in ("openai", "openrouter"):
        runs = [r for r in report["results"] if r["provider"] == provider]
        rows = [r for r in summary["rows"] if r["provider"] == provider]
        completed = [r for r in runs if r.get("http_status") == 200]
        calls = [c for r in runs for c in r["api_calls"]]
        answers = [s for r in rows for s in r["api_stages"] if s["stage"] == "answer"]
        summary["providers"][provider] = {
            "requests": len(runs), "successful_workspace_responses": len(completed),
            "status_counts": dict(Counter(str(r.get("http_status")) for r in runs)),
            "coverage_counts": dict(Counter(r.get("checks", {}).get("coverage", "failed") for r in runs)),
            "mean_request_seconds": round(mean(r["seconds"] for r in runs), 2),
            "median_request_seconds": round(median(r["seconds"] for r in runs), 2),
            "median_success_seconds": round(median(r["seconds"] for r in completed), 2) if completed else None,
            "median_first_retrieval_seconds": round(median(r["retrievals"][0]["seconds"] for r in runs if r["retrievals"]), 2),
            "median_answer_api_seconds": round(median(c["seconds"] for c in answers), 2),
            "api_calls": len(calls), "all_upstream_http_200": all(c.get("http_status") == 200 for c in calls),
            "answer_model_confirmed": all(c["requested_model"] == c["returned_model"] for c in answers),
            "retrieval_provider_matches": all(r["retrieval_provider_matches"] for r in rows),
            "resolved_citations_in_successful_responses": all(r.get("checks", {}).get("all_citations_resolve") for r in completed),
            "refinement_requests": sum(len(r["retrievals"]) > 1 for r in runs),
            "reported_cost_usd": round(sum((c.get("usage") or {}).get("cost", 0) for c in calls), 6)
                if provider == "openrouter" else None,
        }
    destination = OUT.with_name(OUT.stem + "_analysis.json")
    destination.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary["providers"], indent=2))
    print(json.dumps([{k: r[k] for k in ("case_id", "provider", "status", "seconds", "coverage", "sources")}
                      | {"issues": [d["issues"] for d in r["answer_diagnostics"]]} for r in summary["rows"]], indent=2))


if __name__ == "__main__":
    main()
