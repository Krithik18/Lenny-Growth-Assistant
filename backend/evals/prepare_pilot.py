"""Explicitly import and embed the five evaluation episodes in Supabase."""

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from app.core.config import get_settings
from app.db.session import Database
from app.ingestion.chunker import TranscriptChunker
from app.ingestion.pipeline import import_archive
from app.llm.client import OpenAIClient
from app.rag.indexing import embed_pending_chunks
from app.rag.openai_embeddings import OpenAIEmbeddings


async def main():
    settings = get_settings()
    database = Database(settings)
    client = OpenAIClient(settings.openai_api_key.get_secret_value())
    try:
        cases = json.loads(Path(__file__).with_name("retrieval_cases.json").read_text())
        members = {f"episodes/{case['episode']}/transcript.md" for case in cases}
        report = await import_archive(database, members=members)
        print(json.dumps(asdict(report)), flush=True)
        if report.failed or report.imported + report.skipped != len(members):
            raise RuntimeError("Pilot import was incomplete")
        count = await embed_pending_chunks(database, OpenAIEmbeddings(client), TranscriptChunker().version)
        print(json.dumps({"new_embeddings": count, "chunking_version": TranscriptChunker().version}), flush=True)
    finally:
        await client.close()
        await database.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"Pilot preparation failed: {type(error).__name__}")
        raise SystemExit(1) from None
