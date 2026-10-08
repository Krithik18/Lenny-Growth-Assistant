"""Exercise the real HTTP workspace, including history built from real artifacts."""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

CASES = {
    "calculator": ("Build a simple calculator.", "simple-artifact"),
    "growth_question": ("What are the most effective ways to grow a product?", "podcast-qa"),
    "growth_essay": ("Write an essay on product growth.", "ship30-essay"),
    "growth_calculator": ("Build a simple HTML growth calculator with starting users, monthly growth percentage and months.", "simple-artifact"),
    "retention_question": ("What does Lenny's Podcast teach about improving product retention?", "podcast-qa"),
    "ship30_essay": ("Give me something about improving user activation in Ship30for30 style.", "ship30-essay"),
}


def turn_history(records, structured):
    history = []
    for record in records:
        data = record["response"]
        if record["status"] != 200 or not isinstance(data, dict) or not isinstance(data.get("message"), str):
            continue
        history.append({"role": "user", "content": record["request"]["message"]})
        assistant = {"role": "assistant", "content": data["message"]}
        if data.get("skill"):
            assistant["skill"] = data["skill"]
        artifact = data.get("artifact")
        if artifact:
            if structured:
                assistant["artifact"] = artifact
            else:
                assistant["content"] += "\n\n" + artifact["content"]
        assistant["content"] = assistant["content"][:16000]
        history.append(assistant)
    return history[-8:]


async def run(args):
    semaphore = asyncio.Semaphore(2)
    results = []
    async with httpx.AsyncClient(base_url=args.url, timeout=300) as client:
        health = {}
        for name in ("live", "ready"):
            result = await client.get("/health/" + name)
            health[name] = {"status": result.status_code, "body": result.json()}
        print(json.dumps({"health": health}), flush=True)

        async def check(provider, case_id, message, skill, history=None):
            request = {"provider": provider, "message": message, "history": history or []}
            start = asyncio.get_running_loop().time()
            async with semaphore:
                try:
                    response = await client.post("/api/v1/workspace/chat", json=request)
                    try:
                        data = response.json()
                    except ValueError:
                        data = {"detail": response.text[:200]}
                    status = response.status_code
                except httpx.HTTPError as error:
                    status, data = 0, {"detail": type(error).__name__}
            artifact = data.get("artifact") or {}
            passed = status == 200 and data.get("skill") == skill
            if passed and skill != "podcast-qa":
                passed = bool(artifact.get("content")) and artifact.get("language") == ("markdown" if skill == "ship30-essay" else "html")
            if passed and skill == "podcast-qa":
                passed = bool(data.get("sources")) and data.get("coverage") in ("complete", "partial")
            record = {"id": case_id, "provider": provider, "request": request, "status": status,
                      "expected_skill": skill, "passed": passed, "response": data,
                      "seconds": round(asyncio.get_running_loop().time() - start, 2)}
            results.append(record)
            print(json.dumps({"id": case_id, "provider": provider, "status": status, "passed": passed,
                              "skill": data.get("skill"), "artifact_chars": len(artifact.get("content", "")),
                              "sources": len(data.get("sources", {})), "seconds": record["seconds"],
                              "detail": data.get("detail")}), flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(),
                                               "health": health, "results": results}, indent=2,
                                              ensure_ascii=False), encoding="utf-8")
            return record

        for provider in args.providers:
            records = await asyncio.gather(*(check(provider, case_id, *CASES[case_id]) for case_id in args.cases))
            by_id = {record["id"]: record for record in records}
            if args.history_tests and {"calculator", "growth_essay"} <= by_id.keys():
                history = turn_history([by_id["calculator"]], args.structured_history)
                await check(provider, "essay_after_code", "Write an essay on product growth.", "ship30-essay", history)
                history = turn_history([by_id["calculator"], by_id["growth_essay"]], args.structured_history)
                await check(provider, "question_after_code_and_essay", "How should I prioritize my next product growth experiment?",
                            "podcast-qa", history)
                if args.structured_history:
                    legacy = turn_history([by_id["calculator"], by_id["growth_essay"]], False)
                    await check(provider, "legacy_question_after_code_and_essay",
                                "How should I prioritize my next product growth experiment?", "podcast-qa", legacy)
                    await check(provider, "legacy_essay_after_code_and_essay",
                                "Write an essay on product growth.", "ship30-essay", legacy)
                if args.code_edit:
                    history = turn_history([by_id["calculator"]], args.structured_history)
                    await check(provider, "calculator_edit", "Add a Clear button and make sure keyboard input works.",
                                "simple-artifact", history)
    passed = sum(record["passed"] for record in results)
    print(json.dumps({"passed": passed, "total": len(results), "report": str(args.output)}), flush=True)
    return passed == len(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--providers", nargs="+", choices=["openai", "openrouter"], default=["openai"])
    parser.add_argument("--cases", nargs="+", choices=list(CASES), default=list(CASES))
    parser.add_argument("--history-tests", action="store_true")
    parser.add_argument("--structured-history", action="store_true")
    parser.add_argument("--code-edit", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    raise SystemExit(0 if asyncio.run(run(options)) else 1)
