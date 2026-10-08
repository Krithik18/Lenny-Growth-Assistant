"""Record artifact response metadata without exposing credentials."""

import asyncio
import argparse
import json
from pathlib import Path

from app.api.routes.workspace import WorkspaceRequest, create_essay, respond
from app.main import app


async def run(args):
    responses = []
    async with app.router.lifespan_context(app):
        service = app.state.openrouter_rag
        post = service.client.post

        async def recorded(path, payload):
            result = await post(path, payload)
            if payload.get("max_tokens") == 6000:
                responses.append(result)
                print(json.dumps({"choices": [{"finish_reason": choice.get("finish_reason"),
                    "characters": len(choice.get("message", {}).get("content") or "")}
                    for choice in result.get("choices", [])], "usage": result.get("usage")}), flush=True)
            return result

        service.client.post = recorded
        try:
            if args.grounded_report:
                records = json.loads(args.grounded_report.read_text(encoding="utf-8"))["results"]
                answer = next(record["response"] for record in records if record["id"] == "growth_question" and record["status"] == 200)
                generated = await create_essay(service, "Write an essay on product growth.", answer["message"], answer["sources"])
                output = {**generated.model_dump(), "sources": answer["sources"]}
            else:
                output = await respond(WorkspaceRequest(message="Write an essay on product growth.", provider="openrouter"), service)
            print(json.dumps({"passed": True, "artifact_chars": len(output["artifact"]["content"])}), flush=True)
            args.output.with_suffix(".artifact.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as error:
            print(json.dumps({"passed": False, "error": type(error).__name__, "detail": str(error)}), flush=True)
        args.output.write_text(
            json.dumps(responses, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--grounded-report", type=Path)
    parser.add_argument("--output", type=Path, default=Path("evals/results/workspace_openrouter_artifact_diagnostic_2026-10-08.json"))
    asyncio.run(run(parser.parse_args()))
