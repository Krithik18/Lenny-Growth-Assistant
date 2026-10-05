"""Import all managed models so Alembic sees the complete schema."""

from app.db.models.chat import Conversation, Generation, Message, Profile
from app.db.models.knowledge import Episode, EpisodeRevision, IngestionRun, MessageSource, TranscriptChunk
from app.db.models.artifacts import Artifact, ArtifactVersion

__all__ = ["Conversation", "Generation", "Message", "Profile", "Episode",
           "EpisodeRevision", "IngestionRun", "MessageSource", "TranscriptChunk",
           "Artifact", "ArtifactVersion"]
