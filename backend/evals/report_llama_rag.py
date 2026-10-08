"""Analyze completed live records without additional API calls."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(report):
    runs = report["results"]
    calls = [call for run in runs for call in run["api_calls"]]
    searches = [r for run in runs for r in run["retrievals"]]
    hybrid = [r for r in searches if {"semantic", "keyword"} <= {q["kind"] for q in r["database_queries"]}]
    queries = [q for run in runs for q in run["database_queries"] if q["kind"] in {"semantic", "keyword", "neighbor"}]
    return {
        "completed": len(runs), "planned": len(report["cases"]),
        "http_statuses": dict(Counter(str(r.get("http_status", "error")) for r in runs)),
        "coverage": dict(Counter(r.get("checks", {}).get("coverage", "error") for r in runs)),
        "api_calls": len(calls), "requested_models": dict(Counter(c["requested_model"] for c in calls)),
        "returned_models": dict(Counter(c["returned_model"] for c in calls if c.get("returned_model"))),
        "served_providers": dict(Counter(c["served_provider"] for c in calls if c.get("served_provider"))),
        "upstream_http_statuses": dict(Counter(str(a["http_status"]) for c in calls for a in c.get("transport_attempts", []))),
        "reported_cost_usd": round(sum((c.get("usage") or {}).get("cost", 0) or 0 for c in calls), 8),
        "median_seconds": round(statistics.median(r["seconds"] for r in runs), 3) if runs else None,
        "max_seconds": max((r["seconds"] for r in runs), default=None),
        "retrieval_rounds": len(searches), "hybrid_rounds": len(hybrid),
        "hybrid_overlap_rounds": sum(r["semantic_keyword_overlap"] for r in hybrid),
        "all_chunk_queries_filter_openrouter_bge_m3": all(q["openrouter_filter"] and q["bge_m3_filter"] for q in queries),
        "other_provider_calls": report["other_provider_calls"],
        "rerank_fallback_rounds": sum(r.get("result", {}).get("ranking_diagnostics", {}).get("fallback", False) for r in searches),
        "refined_questions": [r["case_id"] for r in runs if len(r["generation_rounds"]) > 1],
        "all_returned_citations_resolve": all(r["checks"]["all_citations_resolve"] for r in runs if "checks" in r),
        "postflight": {k: v for k, v in report.get("postflight", {}).items() if k != "revisions"},
        "code_unchanged": report.get("code_unchanged"), "finished": bool(report.get("finished_utc")),
    }


def packets(path, report):
    output = path.with_suffix("") / "review_packets"
    output.mkdir(parents=True, exist_ok=True)
    definitions = {case["id"]: case for case in report["cases"]}
    for run in report["results"]:
        case_path = path.with_suffix("") / (run["case_id"] + ".json")
        final = run.get("grounded_result", {})
        used = {p["chunk_id"] for p in final.get("sources", {}).values()}
        extra, seen = [], set(used)
        for round_ in run["generation_rounds"]:
            for source_id, passage in round_["sources"].items():
                if passage["chunk_id"] not in seen:
                    seen.add(passage["chunk_id"])
                    extra.append({"source_id_in_round": source_id, **passage})
        value = {
            "case": definitions[run["case_id"]],
            "raw_case_sha256": hashlib.sha256(case_path.read_bytes()).hexdigest(),
            "http_status": run.get("http_status"), "seconds": run["seconds"],
            "answer": final.get("answer"), "cited_sources": final.get("sources", {}),
            "uncited_generation_context": extra, "checks": run.get("checks"),
            "public_error": run.get("workspace_response", {}).get("detail"),
            "generation_rounds": [{"context_tokens": x["context_tokens"], "source_count": len(x["sources"]),
                                   "answer": x.get("answer"), "error_type": x.get("error_type")} for x in run["generation_rounds"]],
            "retrievals": [{"question": r["question"], "candidate_count": len(r.get("candidates", [])),
                            "ranking_diagnostics": r.get("result", {}).get("ranking_diagnostics"),
                            "scope_decision": r.get("result", {}).get("scope_decision"),
                            "requested_people": r.get("result", {}).get("requested_people"),
                            "excluded_people": r.get("result", {}).get("excluded_people"),
                            "blocked_reason": r.get("result", {}).get("blocked_reason"),
                            "ranked_guests": [p.get("guest") for p in r.get("result", {}).get("passages", [])],
                            "semantic_keyword_overlap": r["semantic_keyword_overlap"]} for r in run["retrievals"]],
            "calls": [{k: v for k, v in c.items() if k not in {"response", "ranking"}} for c in run["api_calls"]],
        }
        (output / (run["case_id"] + ".json")).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--packets", action="store_true")
    parser.add_argument("--case")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    report = load(args.report)
    if args.packets:
        print(str(packets(args.report, report)))
    if args.case:
        run = next(r for r in report["results"] if r["case_id"] == args.case)
        if args.trace:
            print(json.dumps({"question": run["question"], "retrievals": [{"scope": r.get("result", {}).get("scope_decision"), "people": r.get("result", {}).get("requested_people"), "blocked": r.get("result", {}).get("blocked_reason"), "candidates": len(r.get("candidates", [])), "ranked": len(r.get("result", {}).get("passages", []))} for r in run["retrievals"]]}, ensure_ascii=True))
            for call in run["api_calls"]:
                if call["path"] != "chat/completions":
                    continue
                response = call.get("response", {})
                print(json.dumps({"model": call["requested_model"], "stage": call["stage"], "schema": call.get("schema"), "error": call.get("error_detail"), "content": [x.get("message", {}).get("content") for x in response.get("choices", [])]}, ensure_ascii=True))
        else:
            print(json.dumps({"question": run["question"], "result": run.get("grounded_result"), "error": run.get("workspace_response", {}).get("detail")}, ensure_ascii=True))
    else:
        print(json.dumps(summarize(report), ensure_ascii=True))
