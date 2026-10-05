import pytest
from pydantic import ValidationError

from app.ingestion.parser import parse_transcript
from app.ingestion.chunker import TranscriptChunker


def test_heading_fallback_and_empty_video_metadata():
    text = "---\nguest: Guest\nyoutube_url: ''\nvideo_id: ''\n---\n# Source title\n\n## Transcript\n\nGuest (00:14):\nSome evidence."
    episode = parse_transcript("episodes/guest/transcript.md", text)
    assert episode.metadata.title == "Source title"
    assert episode.metadata.youtube_url is None
    assert episode.metadata.video_id is None
    assert episode.transcript == "Guest (00:14):\nSome evidence."


def test_nonempty_unsafe_source_url_still_rejected():
    with pytest.raises(ValidationError):
        parse_transcript("episodes/guest/transcript.md", "---\ntitle: Example\nyoutube_url: javascript:alert(1)\n---\n## Transcript\nText")


def test_short_timestamps_and_speaker_continuation():
    chunks = TranscriptChunker().split("Guest (00:14):\nSome evidence.\n\n(01:09):\nMore evidence.")
    assert chunks[0].speaker == "Guest"
    assert chunks[0].start_seconds == 14
    assert chunks[0].end_seconds == 69
