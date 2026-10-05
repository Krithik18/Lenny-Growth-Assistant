"""Separate live answer tests with fixed evidence, then a DB-backed API smoke test."""

import asyncio
import json
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
import httpx
from app.core.config import get_settings
from app.ingestion.fetch import read_transcripts
from app.ingestion.parser import parse_transcript
from app.ingestion.source import ARCHIVE_SHA256
from app.llm.client import OpenAIClient
from app.llm.openai_provider import OpenAIAnswerProvider
from app.main import create_app
from app.schemas.retrieval import RetrievedPassage


async def main():
    settings = get_settings()
    client = OpenAIClient(settings.openai_api_key.get_secret_value())
    cases = json.loads(Path(__file__).with_name("retrieval_cases.json").read_text())
    chosen = [case for case in cases if case["id"] in {"brand-promise", "pmf-survey-options", "pmf-threshold"}]
    members = {f"episodes/{case['episode']}/transcript.md" for case in chosen}
    episodes = {member: parse_transcript(member, text) for member, text in read_transcripts() if member in members}
    results = []
    try:
        provider = OpenAIAnswerProvider(client)
        for case in chosen:
            member = f"episodes/{case['episode']}/transcript.md"
            episode = episodes[member]
            start = episode.transcript.index(case["anchor"])
            # Fixed gold evidence is deliberately independent of vector retrieval.
            passage = RetrievedPassage(
                chunk_id=uuid5(NAMESPACE_URL, case["id"]), episode_id=uuid5(NAMESPACE_URL, member),
                episode_revision_id=uuid5(NAMESPACE_URL, member + ARCHIVE_SHA256),
                title=episode.metadata.title, guest=episode.metadata.guest, source_url=episode.metadata.youtube_url,
                archive_member=member, archive_sha256=ARCHIVE_SHA256,
                text=case["anchor"], start_char=start, end_char=start + len(case["anchor"]),
                start_seconds=None, end_seconds=None, similarity=1,
            )
            answer = await provider.answer(case["question"], {"S1": passage})
            assert not answer.insufficient_evidence
            results.append({"id": case["id"], "question": case["question"], "evidence": passage.text,
                            "answer": answer.model_dump()})
            print(f"Fixed-evidence answer validated: {case['id']}", flush=True)
        unsupported = await provider.answer("What is the exact weather in Mumbai tomorrow?", {"S1": passage})
        assert unsupported.insufficient_evidence and not unsupported.sections, "Unsupported question did not abstain"
        results.append({"id": "unsupported", "answer": unsupported.model_dump()})
        output = Path(__file__).parent / "results" / "openai_answers.json"
        output.write_text(json.dumps({"model": provider.model, "tests": results}, indent=2), encoding="utf-8")
        print("Unsupported question correctly abstained", flush=True)
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)), base_url="http://test") as api:
                question = "What three response choices does Rahul describe for the product-market-fit survey?"
                retrieval = await api.post("/api/v1/rag/retrieve", json={"question": question})
                assert retrieval.status_code == 200, retrieval.text
                assert retrieval.json()["passages"], "No indexed pilot passages found"
                answer = await api.post("/api/v1/rag/ask", json={"question": question})
                assert answer.status_code == 200, answer.text
                assert not answer.json()["answer"]["insufficient_evidence"], "End-to-end answer abstained"
                assert answer.json()["sources"], "End-to-end answer lacks sources"
                results.append({"id": "api-smoke", "retrieval": retrieval.json(), "answer": answer.json()})
        output = Path(__file__).parent / "results" / "openai_answers.json"
        output.write_text(json.dumps({"model": provider.model, "tests": results}, indent=2), encoding="utf-8")
        print(f"Saved {len(results)} answer checks to {output}")
    finally:
        await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"Live answer check failed: {type(error).__name__}: {error}")
        raise SystemExit(1) from None
