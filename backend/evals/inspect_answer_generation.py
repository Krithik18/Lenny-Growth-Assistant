"""Print compact saved generation outputs without another model call."""
import argparse
import json
from collections import Counter
from statistics import median
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("path", type=Path)
parser.add_argument("--failures", action="store_true")
parser.add_argument("--case")
parser.add_argument("--sources", action="store_true")
parser.add_argument("--reviews", action="store_true")
parser.add_argument("--summary", action="store_true")
parser.add_argument("--calls", action="store_true")
args = parser.parse_args()
report = json.loads(args.path.read_text(encoding="utf-8"))
cases = {case["id"]: case for case in report["cases"]}
if args.summary:
    results = report["results"]
    calls = [call for result in results for call in result["api_calls"]]
    print(json.dumps({
        "count": len(results), "coverage": dict(Counter(r.get("answer", {}).get("coverage", "error") for r in results)),
        "contract_valid": sum(bool(r.get("final_contract_valid")) for r in results),
        "api_calls": len(calls), "returned_models": dict(Counter(c.get("returned_model") for c in calls)),
        "providers": dict(Counter(c.get("provider") for c in calls)),
        "reported_cost_usd": sum((c.get("usage") or {}).get("cost", 0) or 0 for c in calls),
        "median_seconds": median(r["seconds"] for r in results) if results else None,
        "max_seconds": max((r["seconds"] for r in results), default=0),
        "invalid_responses": sum(c.get("structurally_valid") is False for c in calls),
        "review_rejections": sum(bool(c.get("grounding_issues")) for c in calls),
        "reasoning_tokens": sum(((c.get("usage") or {}).get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0 for c in calls),
        "fixture_sha256": report["fixture_sha256"], "provider_sha256": report.get("provider_sha256"),
    }, ensure_ascii=True))
    raise SystemExit
for result in sorted(report["results"], key=lambda r: r["case_id"]):
    if args.case and result["case_id"] != args.case:
        continue
    print(result["case_id"], json.dumps(result.get("answer", {"error": result.get("error")}), ensure_ascii=True))
    if args.sources:
        print("question", cases[result["case_id"]]["question"])
        for sid, source in cases[result["case_id"]]["sources"].items():
            print(sid, json.dumps({key: source.get(key) for key in ["guest", "text"]}, ensure_ascii=True))
    if args.failures and result.get("error"):
        for call in result["api_calls"]:
            print("rejected", json.dumps(call.get("choices"), ensure_ascii=True)[:5000])
    if args.reviews:
        for call in result["api_calls"]:
            if call.get("grounding_issues"):
                print("review", json.dumps(call["grounding_issues"], ensure_ascii=True))
    if args.calls:
        for call in result["api_calls"]:
            print("call", json.dumps({key: call.get(key) for key in ["stage", "provider", "returned_model", "seconds", "structurally_valid", "grounding_issues", "usage"]}, ensure_ascii=True))
