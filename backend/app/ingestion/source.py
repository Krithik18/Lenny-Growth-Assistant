"""The user-approved knowledge source. No network corpus fallback."""

from pathlib import Path
from app.core.config import get_settings

settings = get_settings()

ARCHIVE_PATH = Path(settings.transcript_archive_path)
ARCHIVE_SHA256 = settings.transcript_archive_sha256