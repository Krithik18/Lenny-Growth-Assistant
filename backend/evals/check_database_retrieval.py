"""Verify real PostgreSQL retrieval independently of generation."""

import asyncio
import json
from pathlib import Path
from sqlalchemy import text
from app.core.config import get_settings
from app.db.session import Database
from app.llm.client import OpenAIClient
from app.rag.service import RAGService


async def main():
    settings = get_settings()
    database = Database(settings)
    client = OpenAIClient(settings.openai_api_key.get_secret_value())
    try:
        async with database.sessions() as session:
            counts = (await session.execute(text("SELECT (SELECT count(*) FROM app_data.episodes) AS episodes, "
                "(SELECT count(*) FROM app_data.transcript_chunks) AS chunks, "
                "(SELECT count(*) FROM app_data.chunk_embeddings) AS embeddings"))).mappings().one()
            print(json.dumps(dict(counts)), flush=True)
            assert counts["embeddings"] >= 369, "Pilot indexing is incomplete"
            rls = await session.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid = 'app_data.chunk_embeddings'::regclass"))
            assert rls, "Embedding table RLS is disabled"
        service = RAGService(database, client)
        cases = json.loads(Path(__file__).with_name("retrieval_cases.json").read_text())
        results = []
        for case in cases:
            retrieval = await service.retrieve(case["question"])
            assert retrieval.passages
            # Conservative exact-anchor check, separate from union coverage in local comparison.
            hit = any(case["anchor"] in p.text and p.archive_member == f"episodes/{case['episode']}/transcript.md"
                      for p in retrieval.passages)
            results.append({"id": case["id"], "exact_anchor_hit_at_5": hit,
                            "top5": [str(p.chunk_id) for p in retrieval.passages]})
        report = {"counts": dict(counts), "embedding_table_rls": rls, "questions": results,
                  "exact_anchor_hits": sum(row["exact_anchor_hit_at_5"] for row in results)}
        output = Path(__file__).parent / "results" / "database_retrieval.json"
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
    finally:
        await client.close()
        await database.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"Database retrieval check failed: {type(error).__name__}: {error}")
        raise SystemExit(1) from None
