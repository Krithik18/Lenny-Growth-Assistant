"""Read approved transcript members directly from ZIP; never extract or fetch URLs."""

from collections.abc import Iterator
from hashlib import file_digest
from pathlib import Path, PurePosixPath
from stat import S_ISLNK
from zipfile import ZipFile

from app.ingestion.source import ARCHIVE_PATH, ARCHIVE_SHA256

MAX_MEMBER_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


def read_transcripts(path: Path = ARCHIVE_PATH) -> Iterator[tuple[str, str]]:
    # Hash and read the same open file; never trust ZIP-provided instructions or scripts.
    with path.open("rb") as source:
        if file_digest(source, "sha256").hexdigest() != ARCHIVE_SHA256:
            raise ValueError("Archive does not match the approved knowledge source.")
        source.seek(0)
        with ZipFile(source) as archive:
            members = []
            seen = set()
            for info in archive.infolist():
                parts = PurePosixPath(info.filename).parts
                if info.is_dir() or len(parts) not in (3, 4):
                    continue
                if parts[-3] != "episodes" or parts[-1] != "transcript.md":
                    continue
                if ".." in parts or "\\" in info.filename or PurePosixPath(info.filename).is_absolute():
                    raise ValueError("Unsafe transcript path in archive.")
                if S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                    raise ValueError("Linked or encrypted transcripts are not supported.")
                member_path = "/".join(parts[-3:])
                if member_path in seen or info.file_size > MAX_MEMBER_BYTES:
                    raise ValueError("Duplicate or oversized transcript member.")
                seen.add(member_path)
                members.append((member_path, info))
            if not members or sum(info.file_size for _, info in members) > MAX_TOTAL_BYTES:
                raise ValueError("Archive has no transcripts or exceeds the corpus size limit.")
            for member_path, info in sorted(members, key=lambda pair: pair[0]):
                with archive.open(info) as member:
                    data = member.read(MAX_MEMBER_BYTES + 1)
                if len(data) > MAX_MEMBER_BYTES:
                    raise ValueError("Transcript exceeds the size limit.")
                yield member_path, data.decode("utf-8-sig")
