"""Explicit ZIP import. Stores transcript text/chunks; does not call an embedding API."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select, text

from app.db.models import Episode, EpisodeRevision, IngestionRun, TranscriptChunk
from app.db.session import Database
from app.ingestion.chunker import TranscriptChunker
from app.ingestion.fetch import read_transcripts
from app.ingestion.parser import ParsedEpisode, parse_transcript
from app.ingestion.source import ARCHIVE_PATH, ARCHIVE_SHA256


@dataclass
class ImportReport:
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


async def save_episode(database: Database, parsed: ParsedEpisode, chunker: TranscriptChunker, run_id) -> bool:
    chunks = chunker.split(parsed.transcript)
    if not chunks:
        raise ValueError("Transcript produced no chunks.")
    async with database.sessions.begin() as session:
        # Serializes overlapping imports of this episode; released at transaction end.
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": parsed.member_path})
        episode = await session.scalar(select(Episode).where(Episode.repository_path == parsed.member_path))
        if episode is None:
            episode = Episode(id=uuid4(), repository_path=parsed.member_path, title=parsed.metadata.title)
            session.add(episode)
            await session.flush()
        revision = await session.scalar(select(EpisodeRevision).where(
            EpisodeRevision.episode_id == episode.id,
            EpisodeRevision.source_commit == ARCHIVE_SHA256,
        ))
        if revision is None:
            revision = EpisodeRevision(
                id=uuid4(), episode_id=episode.id,
                # Legacy column name: this value is a ZIP checksum, not a Git commit.
                source_commit=ARCHIVE_SHA256, source_archive_sha256=ARCHIVE_SHA256,
                content_hash=parsed.content_hash, transcript_text=parsed.transcript,
                status="processing", ingestion_run_id=run_id,
            )
            session.add(revision)
            await session.flush()
        elif revision.source_archive_sha256 != ARCHIVE_SHA256 or revision.content_hash != parsed.content_hash:
            raise ValueError("Existing revision does not match archive provenance.")
        existing_count = await session.scalar(select(func.count()).select_from(TranscriptChunk).where(
            TranscriptChunk.episode_revision_id == revision.id,
            TranscriptChunk.chunking_version == chunker.version,
        ))
        if existing_count and existing_count != len(chunks):
            raise ValueError("Existing chunk set is incomplete; use a new chunking version after investigation.")
        if not existing_count:
            session.add_all([
                TranscriptChunk(
                    episode_revision_id=revision.id, chunk_index=chunk.index,
                    content=chunk.content, token_count=chunk.token_count,
                    start_char=chunk.start_char, end_char=chunk.end_char,
                    speaker=chunk.speaker, start_seconds=chunk.start_seconds,
                    end_seconds=chunk.end_seconds, chunking_version=chunker.version,
                ) for chunk in chunks
            ])
        meta = parsed.metadata
        episode.title, episode.guest, episode.description = meta.title, meta.guest, meta.description
        episode.youtube_url, episode.video_id = meta.youtube_url, meta.video_id
        episode.published_at, episode.duration_seconds = meta.publish_date, meta.duration_seconds
        revision.status = "ready"  # Text/chunks ready, not a claim that embeddings exist.
        episode.active_revision_id = revision.id
        # Context manager commits chunks and active revision together.
        return not bool(existing_count)


async def import_archive(database: Database, path: Path = ARCHIVE_PATH, limit: int | None = None) -> ImportReport:
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    chunker = TranscriptChunker()
    report = ImportReport()
    run_id = uuid4()
    async with database.sessions.begin() as session:
        session.add(IngestionRun(id=run_id, source_commit=ARCHIVE_SHA256, status="running"))
    try:
        for position, (member_path, content) in enumerate(read_transcripts(path)):
            if limit is not None and position >= limit:
                break
            try:
                parsed = parse_transcript(member_path, content)
                imported = await save_episode(database, parsed, chunker, run_id)
                report.imported += int(imported)
                report.skipped += int(not imported)
            except Exception as error:
                report.failed += 1
                # Do not log raw SQL parameters, transcript contents, or credentials.
                report.errors.append(f"{member_path}: {type(error).__name__}")
            async with database.sessions.begin() as session:
                run = await session.get(IngestionRun, run_id)
                run.episodes_processed = report.imported + report.skipped
                run.episodes_failed = report.failed
        async with database.sessions.begin() as session:
            run = await session.get(IngestionRun, run_id)
            run.status = "failed" if report.failed else "completed"
            run.finished_at = datetime.now(timezone.utc)
            run.error_summary = "\n".join(report.errors) or None
    except Exception as error:
        async with database.sessions.begin() as session:
            run = await session.get(IngestionRun, run_id)
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error_summary = f"Archive import stopped: {type(error).__name__}"
        raise
    return report
