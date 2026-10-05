"""Explicit import command; never invoked by FastAPI startup."""

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path

from app.core.config import get_settings
from app.db.session import Database
from app.ingestion.pipeline import import_archive
from app.ingestion.source import ARCHIVE_PATH


async def main() -> int:
    parser = argparse.ArgumentParser(description="Import only the approved Lenny transcript ZIP; no embedding calls.")
    parser.add_argument("--archive", type=Path, default=ARCHIVE_PATH, help="Relocated copy is allowed only if its checksum matches.")
    parser.add_argument("--limit", type=int, default=None, help="Optional sample size; omit to import the full archive.")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.database_url.get_secret_value():
        parser.error("Set DATABASE_URL in backend/.env first.")
    database = Database(settings)
    try:
        report = await import_archive(database, args.archive, args.limit)
        print(json.dumps(asdict(report), indent=2))
        return 1 if report.failed else 0
    finally:
        await database.close()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as error:
        # Avoid accidentally printing connection credentials via a driver traceback.
        print(f"Import failed ({type(error).__name__}); inspect configuration and ingestion_runs.")
        raise SystemExit(1) from None
