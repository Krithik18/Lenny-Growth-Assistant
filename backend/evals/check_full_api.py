"""Smoke-check the running localhost API after full archive indexing."""
import asyncio
import json
from pathlib import Path
import httpx
from app.ingestion.source import ARCHIVE_SHA256


async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=180) as client:
        health = {}
        for route in ("live", "ready"):
            response = await client.get(f"/health/{route}")
            response.raise_for_status()
            health[route] = response.json()
        invalid = await client.post("/api/v1/rag/ask", json={"question":" "})
        assert invalid.status_code == 422
        question = "How does Brian Chesky approach product management at Airbnb, and what role do designers play?"
        evidence = await client.post("/api/v1/rag/retrieve", json={"question":question})
        evidence.raise_for_status()
        assert evidence.json()["passages"]
        response = await client.post("/api/v1/rag/ask", json={"question":question})
        response.raise_for_status()
        result = response.json()
        assert result["model"] == "gpt-6-luna"
        assert result["answer"]["sections"] and result["sources"]
        assert all(source["archive_sha256"] == ARCHIVE_SHA256 for source in result["sources"].values())
        report = {"health":health, "invalid_request_status":invalid.status_code,
                  "retrieve_status":evidence.status_code, "ask_status":response.status_code,
                  "result":result}
        (Path(__file__).parent / "results" / "full_api.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"health":health, "invalid_request_status":invalid.status_code,
                          "ask_status":response.status_code, "coverage":result["answer"]["coverage"],
                          "model":result["model"]}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
