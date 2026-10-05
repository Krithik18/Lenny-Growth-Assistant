"""Parse archive data only; never execute YAML constructors or transcript instructions."""

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import re
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EpisodeMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=1)
    guest: str | None = None
    description: str | None = None
    youtube_url: str | None = None
    video_id: str | None = None
    publish_date: date | None = None
    duration_seconds: int | None = Field(default=None, ge=0)

    @field_validator("youtube_url")
    @classmethod
    def safe_source_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError("Source URL must be an HTTP(S) URL.")
        return value


@dataclass(frozen=True)
class ParsedEpisode:
    member_path: str
    metadata: EpisodeMetadata
    transcript: str
    content_hash: str


def parse_transcript(member_path: str, text: str) -> ParsedEpisode:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    match = re.match(r"\A---\s*\n(.*?)\n---[ \t]*(?:\n|$)", normalized, re.DOTALL)
    if match is None:
        raise ValueError(f"Missing YAML frontmatter: {member_path}")
    raw = yaml.safe_load(match.group(1))
    if not isinstance(raw, dict):
        raise ValueError(f"Metadata must be a mapping: {member_path}")
    metadata = EpisodeMetadata.model_validate(raw)
    body = normalized[match.end():]
    heading = re.search(r"^##\s+Transcript\s*$", body, re.MULTILINE | re.IGNORECASE)
    if heading is None:
        raise ValueError(f"Missing transcript section: {member_path}")
    transcript = body[heading.end():].strip()
    if not transcript:
        raise ValueError(f"Empty transcript: {member_path}")
    return ParsedEpisode(member_path, metadata, transcript, sha256(normalized.encode()).hexdigest())
