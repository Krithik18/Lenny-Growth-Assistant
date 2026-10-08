"""Run actual workspace requests while prohibiting calls to the other provider."""

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

import httpx

from app.main import app
from evals.workspace_runtime_live import CASES, turn_history

CASES = {
    **CASES,
    "activation_advice": ("How can a B2B SaaS product improve activation for new users?", "podcast-qa"),
    "growth_metrics": ("How do activation, retention, and acquisition metrics differ?", "podcast-qa"),
    "lenny_discovery": ("Based on Lenny's podcast transcripts, what does Teresa Torres recommend for continuous discovery?", "podcast-qa"),
    "retention_essay": ("Write a short essay about why retention matters more than acquisition for sustainable growth.", "ship30-essay"),
    "ship30_experiments": ("Give me something in Ship30for30 style about learning from failed growth experiments.", "ship30-essay"),
    "tip_calculator": ("Build an interactive HTML tip calculator with bill amount, tip percentage, number of people, and a reset button.", "simple-artifact"),
    "todo_app": ("Write a standalone HTML to-do app where I can add tasks, mark them complete, delete them, and filter completed tasks. Keep data in memory.", "simple-artifact"),
    "general_question": ("What is the capital of France?", "podcast-qa"),
    "short_activation_essay": ("Write a short essay about improving user activation.", "ship30-essay"),
    "essay_200_words": ("Write a 200-word essay about product retention.", "ship30-essay"),
    "essay_over_cap": ("Write a 2000-word essay about product growth.", "ship30-essay"),
}


async def run(args):
    records = []
    async with app.router.lifespan_context(app):
        services = {"openai": app.state.rag, "openrouter": app.state.openrouter_rag}
        calls = []
        selected = None
        originals = {provider: service.client.post for provider, service in services.items()}

        def wrapper(provider):
            async def post(path, payload):
                assert provider == selected, f"Unexpected {provider} request while {selected} was selected"
                model = payload.get("model")
                assert selected != "openrouter" or not str(model).startswith(("openai/", "gpt-")), "OpenAI model used for Llama"
                start = asyncio.get_running_loop().time()
                result = await originals[provider](path, payload)
                calls.append({"provider": provider, "path": path, "model": model,
                              "endpoint_provider": result.get("provider"),
                              "seconds": round(asyncio.get_running_loop().time() - start, 2)})
                return result
            return post

        for provider, service in services.items():
            service.client.post = wrapper(provider)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            for provider in args.providers:
                selected = provider
                responses = {}

                async def check(case_id, message, skill, history=None):
                    calls.clear()
                    request = {"provider": provider, "message": message, "history": history or []}
                    async with asyncio.timeout(300):
                        response = await client.post("/api/v1/workspace/chat", json=request)
                    body = response.json()
                    model = "gpt-6-luna" if provider == "openai" else "meta-llama/llama-3.1-8b-instruct"
                    passed = response.status_code == 200 and body.get("skill") == skill and body.get("model") == model
                    if case_id == "general_question":
                        # This assistant intentionally answers from its podcast corpus.
                        passed = passed and body.get("coverage") == "unsupported" and bool(body.get("message"))
                    elif skill == "podcast-qa":
                        passed = passed and bool(body.get("sources"))
                    else:
                        passed = passed and bool((body.get("artifact") or {}).get("content"))
                    if skill == "ship30-essay" and response.status_code == 200:
                        words = len((body.get("artifact") or {}).get("content", "").split())
                        passed = passed and words <= 1500
                        if case_id == "short_activation_essay":
                            passed = passed and words <= 450
                        elif case_id == "essay_200_words":
                            passed = passed and 170 <= words <= 230
                    record = {"id": case_id, "provider": provider, "request": request, "status": response.status_code,
                              "passed": passed, "response": body, "calls": list(calls)}
                    records.append(record)
                    args.output.write_text(json.dumps({"results": records}, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(json.dumps({"id": case_id, "provider": provider, "status": response.status_code,
                                      "passed": passed, "model": body.get("model"),
                                      "models_called": dict(Counter(call["model"] for call in calls)),
                                      "detail": body.get("detail")}), flush=True)
                    return record

                for case_id in args.cases:
                    responses[case_id] = await check(case_id, *CASES[case_id])
                if args.history_tests and {"calculator", "growth_essay"} <= responses.keys():
                    await check("calculator_edit", "Add a Clear button and make sure keyboard input works.", "simple-artifact",
                                turn_history([responses["calculator"]], True))
                    await check("question_after_artifacts", "How should I prioritize my next product growth experiment?", "podcast-qa",
                                turn_history([responses["calculator"], responses["growth_essay"]], True))
    print(json.dumps({"passed": sum(record["passed"] for record in records), "total": len(records)}), flush=True)
    return all(record["passed"] for record in records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", nargs="+", choices=["openai", "openrouter"], default=["openrouter"])
    parser.add_argument("--cases", nargs="+", choices=list(CASES), default=["calculator", "growth_question", "growth_essay"])
    parser.add_argument("--history-tests", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    asyncio_args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(run(asyncio_args)) else 1)
