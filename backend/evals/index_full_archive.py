"""Resume approved ZIP import and embeddings; verify coverage per episode."""

import asyncio
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from sqlalchemy import text
from app.core.config import get_settings
from app.db.session import Database
from app.ingestion.chunker import TranscriptChunker
from app.ingestion.pipeline import import_archive, ImportReport
from app.ingestion.source import ARCHIVE_SHA256
from app.llm.client import OpenAIClient, ProviderError
from app.rag.indexing import embed_pending_chunks
from app.rag.openai_embeddings import OpenAIEmbeddings


class RetryingEmbeddings(OpenAIEmbeddings):
    async def embed_documents(self, texts):
        for attempt in range(5):
            try:
                return await super().embed_documents(texts)
            except ProviderError as error:
                if attempt == 4 or not any(code in str(error) for code in ("429", "500", "502", "503", "504", "request failed or")):
                    raise
                print(f"Transient embedding failure; retry {attempt + 1}/4", flush=True)
                await asyncio.sleep(min(30, 2 ** (attempt + 2)))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-failed", action="store_true", help="Retry only members from the last failed import, then embed.")
    parser.add_argument("--skip-import", action="store_true", help="Embed already imported source files after verifying all 303 are present.")
    args = parser.parse_args()
    settings = get_settings()
    database = Database(settings)
    client = OpenAIClient(settings.openai_api_key.get_secret_value())
    try:
        def imported(member, report):
            count = report.imported + report.skipped + report.failed
            if count % 10 == 0:
                print(json.dumps({"stage": "import", "processed": count, **asdict(report)}), flush=True)
        members = None
        if args.resume_failed:
            async with database.sessions() as session:
                errors = await session.scalar(text("SELECT error_summary FROM app_data.ingestion_runs WHERE source_commit=:sha AND status='failed' ORDER BY started_at DESC LIMIT 1"), {"sha": ARCHIVE_SHA256})
            members = {line.split(": ")[0] for line in (errors or "").splitlines() if line.startswith("episodes/")}
            if not members:
                raise RuntimeError("No failed archive members found")
        report = ImportReport(skipped=303) if args.skip_import else await import_archive(database, members=members, progress=imported)
        print(json.dumps({"stage": "import_complete", **asdict(report)}), flush=True)
        if report.failed or report.imported + report.skipped != (len(members) if members else 303):
            raise RuntimeError("Archive import is incomplete; indexing was not started")
        async with database.sessions() as session:
            imported_count = await session.scalar(text("SELECT count(*) FROM app_data.episodes e JOIN app_data.episode_revisions r ON r.id=e.active_revision_id WHERE r.source_archive_sha256=:sha AND r.status='ready'"), {"sha": ARCHIVE_SHA256})
            if imported_count != 303:
                raise RuntimeError("Expected all 303 archive members before embedding")
        version = TranscriptChunker().version
        progress = [0, 0]
        def embedded(shard, count):
            progress[shard] = count
            if sum(progress) % 512 == 0:
                print(json.dumps({"stage": "embedding", "new_embeddings": sum(progress)}), flush=True)
        async with asyncio.TaskGroup() as group:
            workers = [group.create_task(embed_pending_chunks(database, RetryingEmbeddings(client), version,
                       batch_size=64, shards=2, shard_index=shard,
                       progress=lambda count, shard=shard: embedded(shard, count))) for shard in range(2)]
        count = sum(worker.result() for worker in workers)
        async with database.sessions() as session:
            rows = (await session.execute(text("""
                SELECT e.repository_path AS member, count(c.id) AS chunks,
                       count(v.id) AS embeddings, sum(c.token_count) AS embedding_tokens
                FROM app_data.episodes e JOIN app_data.episode_revisions r ON r.id=e.active_revision_id
                JOIN app_data.transcript_chunks c ON c.episode_revision_id=r.id
                LEFT JOIN app_data.chunk_embeddings v ON v.chunk_id=c.id AND v.provider='openai'
                    AND v.model='text-embedding-3-small' AND v.dimensions=1536 AND v.input_version='raw-chunk-v1'
                WHERE r.source_archive_sha256=:sha AND r.status='ready' AND c.chunking_version=:version
                GROUP BY e.repository_path ORDER BY e.repository_path
            """), {"sha": ARCHIVE_SHA256, "version": version})).mappings().all()
        coverage = [dict(row) for row in rows]
        assert len(coverage) == 303 and all(row["chunks"] == row["embeddings"] > 0 for row in coverage)
        result = {"archive_sha256": ARCHIVE_SHA256, "chunking_version": version,
                  "episodes": len(coverage), "chunks": sum(r["chunks"] for r in coverage),
                  "embeddings": sum(r["embeddings"] for r in coverage),
                  "embedding_input_tokens": sum(r["embedding_tokens"] for r in coverage),
                  "new_embeddings_this_run": count, "coverage": coverage}
        output = Path(__file__).parent / "results" / "full_index.json"
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({key: value for key, value in result.items() if key != "coverage"}), flush=True)
    finally:
        await client.close()
        await database.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"Full indexing stopped: {type(error).__name__}: {error if isinstance(error, (ProviderError, AssertionError, RuntimeError)) else 'See saved import progress; credentials omitted'}", flush=True)
        raise SystemExit(1) from None
