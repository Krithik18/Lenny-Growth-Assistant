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
        async def errors(response):
            if response.status_code < 400:
                return
            await response.aread()
            detail = response.json().get("error", {})
            key = app.state.settings.openrouter_api_key.get_secret_value()
            message = str(detail.get("message", ""))[:500].replace(key, "[redacted]")
            print(json.dumps({"http_error": response.status_code, "message": message,
                              "provider": detail.get("metadata", {}).get("provider_name"),
                              "retry_after": response.headers.get("retry-after")}), flush=True)
        service.client.http.event_hooks["response"].append(errors)

        async def recorded(path, payload):
            if args.exclude_coreweave and payload.get("structured_outputs"):
                payload = {key: value for key, value in payload.items() if key != "structured_outputs"}
                payload["provider"] = {**payload.get("provider", {}), "ignore": ["CoreWeave"]}
            result = await post(path, payload)
            if payload.get("max_tokens") == 6000:
                responses.append(result)
                print(json.dumps({"choices": [{"finish_reason": choice.get("finish_reason"),
                    "characters": len(choice.get("message", {}).get("content") or "")}
                    for choice in result.get("choices", [])], "provider": result.get("provider"), "usage": result.get("usage")}), flush=True)
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
    parser.add_argument("--exclude-coreweave", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("evals/results/workspace_openrouter_artifact_diagnostic_2026-10-08.json"))
    asyncio.run(run(parser.parse_args()))
