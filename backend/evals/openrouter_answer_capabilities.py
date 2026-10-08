"""Inspect public endpoint capabilities; never accesses credentials."""
import asyncio
import argparse
import json
from pathlib import Path
import httpx


async def main(model, output):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"https://openrouter.ai/api/v1/models/{model}/endpoints")
        response.raise_for_status()
        data = response.json()
        catalog = await client.get("https://openrouter.ai/api/v1/models")
        catalog.raise_for_status()
        data["model_metadata"] = next(m for m in catalog.json()["data"] if m["id"] == model)
    output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps({k: data["model_metadata"].get(k) for k in ["id", "reasoning", "supported_parameters"]}))
    for endpoint in data.get("data", {}).get("endpoints", []):
        print(json.dumps({k: endpoint.get(k) for k in ["provider_name", "name", "supported_parameters"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="meta-llama/llama-3.1-8b-instruct")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.model, args.output))
