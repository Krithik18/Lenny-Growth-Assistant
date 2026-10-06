"""Read-only indexing progress for the approved archive and active configuration."""
import asyncio
import json
from sqlalchemy import text
from app.core.config import get_settings
from app.db.session import Database
from app.ingestion.chunker import TranscriptChunker
from app.ingestion.source import ARCHIVE_SHA256


async def main():
    database = Database(get_settings())
    try:
        async with database.sessions() as session:
            row = (await session.execute(text("""
                SELECT count(DISTINCT e.id) AS episodes, count(c.id) AS chunks,
                       count(v.id) AS embeddings, sum(c.token_count) AS input_tokens,
                       count(c.id)-count(v.id) AS remaining
                FROM app_data.episodes e JOIN app_data.episode_revisions r ON r.id=e.active_revision_id
                JOIN app_data.transcript_chunks c ON c.episode_revision_id=r.id
                LEFT JOIN app_data.chunk_embeddings v ON v.chunk_id=c.id AND v.provider='openai'
                  AND v.model='text-embedding-3-small' AND v.dimensions=1536 AND v.input_version='raw-chunk-v1'
                WHERE r.source_archive_sha256=:sha AND r.status='ready' AND c.chunking_version=:version
            """), {"sha":ARCHIVE_SHA256, "version":TranscriptChunker().version})).mappings().one()
            print(json.dumps(dict(row)), flush=True)
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())
