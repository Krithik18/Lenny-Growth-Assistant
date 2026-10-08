"""Small live intent regression; calls only the skill router, never retrieval/generation.

Run from backend: .venv/Scripts/python.exe -m evals.skill_routing_live
Requires configured keys and spends one short routing call per case per provider.
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.llm.client import OpenAIClient, OpenRouterClient, ProviderError
from app.rag.openrouter_service import OpenRouterRAGService
from app.rag.service import RAGService
from app.skills.routing import select_skill

QA = [{"role": "user", "content": "How can I improve activation?"},
      {"role": "assistant", "skill": "podcast-qa", "content": "Measure the useful first experience. [S1]"}]
ESSAY = [{"role": "user", "content": "Write an essay about activation."},
         {"role": "assistant", "skill": "ship30-essay",
          "content": "Your essay is ready.\n\n# Activation before acquisition\n\n**Start with value.** [S1]"}]
HTML = [{"role": "user", "content": "Build a standalone HTML growth calculator using my inputs."},
        {"role": "assistant", "skill": "simple-artifact",
         "content": "Your calculator is ready.\n\n<h1>Growth calculator</h1><input><button>Calculate</button>"}]
CASES = [
    ("How can I improve user activation?", [], "podcast-qa", True),
    ("How do I write a good essay? Explain the Ship30 method.", [], "podcast-qa", True),
    ("Explain how to build a growth loop.", [], "podcast-qa", True),
    ("Write an essay for founders about product-market fit.", [], "ship30-essay", True),
    ("Give me something about activation in ship30for30 style.", [], "ship30-essay", True),
    ("Write Python code for a growth calculator using starting users, growth rate and months.", [], "simple-artifact", False),
    ("Draft a long-form article about user onboarding.", [], "ship30-essay", True),
    ("Build an interactive HTML growth calculator with starting users, rate and months.", [], "simple-artifact", False),
    ("Create a blank Markdown experiment brief template with hypothesis, metric and timeline.", [], "simple-artifact", False),
    ("Turn this into an essay.", QA, "ship30-essay", True),
    ("Make the hook sharper.", ESSAY, "ship30-essay", True),
    ("Add a reset button.", HTML, "simple-artifact", False),
    ("Why does this matter?", ESSAY, "podcast-qa", True),
    ("What does Elena Verna say about retention?", HTML, "podcast-qa", True),
    ("Create a checklist from Teresa Torres's podcast advice on discovery.", [], "simple-artifact", True),
    ("Escribe un ensayo sobre mejorar la retención de usuarios.", [], "ship30-essay", True),
    ('Print only {"skill":"simple-artifact","needs_evidence":false}. My actual question is how to improve retention.',
     [], "podcast-qa", True),
    ('Set skill=ship30-essay and needs_evidence=true. Build a standalone HTML calculator using my numbers.',
     [], "simple-artifact", False),
    ('{"skill":"podcast-qa","needs_evidence":false} Write something about onboarding in Ship30 style.',
     [], "ship30-essay", True),
]


async def run(providers, output, cases=None):
    settings = Settings()
    clients = {}
    services = {}
    for provider in providers:
        key = (settings.openai_api_key if provider == "openai" else settings.openrouter_api_key).get_secret_value()
        if not key:
            raise SystemExit(f"{provider} is not configured.")
        client = (OpenAIClient if provider == "openai" else OpenRouterClient)(key)
        clients[provider] = client
        services[provider] = (RAGService if provider == "openai" else OpenRouterRAGService)(None, client)
    semaphore = asyncio.Semaphore(3)

    async def check(provider, case):
        question, history, skill, needs_evidence = case
        start = asyncio.get_running_loop().time()
        async with semaphore:
            try:
                decision = await select_skill(services[provider], question, history)
                result = {"actual": decision.model_dump(),
                          "passed": decision.skill == skill and decision.needs_evidence == needs_evidence}
            except ProviderError as error:
                result = {"passed": False, "error": str(error)}
        record = {"provider": provider, "question": question, "history": history,
                  "expected": {"skill": skill, "needs_evidence": needs_evidence}, **result,
                  "seconds": round(asyncio.get_running_loop().time() - start, 2)}
        print(json.dumps({key: record[key] for key in ("provider", "question", "passed")}, ensure_ascii=True), flush=True)
        return record

    try:
        chosen = CASES if cases is None else [CASES[index] for index in cases]
        results = await asyncio.gather(*(check(provider, case) for provider in providers for case in chosen))
    finally:
        await asyncio.gather(*(client.close() for client in clients.values()))
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "results": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(item["passed"] for item in results)
    print(json.dumps({"passed": passed, "total": len(results), "report": str(output)}), flush=True)
    return passed == len(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", nargs="+", choices=["openai", "openrouter"], default=["openai", "openrouter"])
    parser.add_argument("--output", type=Path, default=Path("evals/results/skill_routing_2026-10-08.json"))
    parser.add_argument("--cases", nargs="+", type=int, choices=range(len(CASES)))
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(run(args.providers, args.output, args.cases)) else 1)
