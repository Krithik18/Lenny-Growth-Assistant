"""Initial application schema. Frozen SQL; independent of future ORM changes."""
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public""")
    op.execute("""SET LOCAL search_path TO public, extensions, app_data""")
    op.execute("""DO $$ BEGIN IF to_regclass('auth.users') IS NULL THEN RAISE EXCEPTION 'Supabase auth.users is required before this migration'; END IF; END $$""")
    op.execute("""CREATE TABLE app_data.episodes (
	title TEXT NOT NULL, 
	guest TEXT, 
	description TEXT, 
	youtube_url TEXT, 
	video_id VARCHAR(100), 
	published_at DATE, 
	duration_seconds INTEGER, 
	repository_path TEXT NOT NULL, 
	active_revision_id UUID, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_episodes PRIMARY KEY (id), 
	CONSTRAINT ck_episodes_duration CHECK (duration_seconds >= 0), 
	CONSTRAINT uq_episodes_video_id UNIQUE (video_id), 
	CONSTRAINT uq_episodes_repository_path UNIQUE (repository_path)
)""")
    op.execute("""CREATE TABLE app_data.ingestion_runs (
	source_commit VARCHAR(64) NOT NULL, 
	status VARCHAR(20) DEFAULT 'running' NOT NULL, 
	episodes_processed INTEGER DEFAULT '0' NOT NULL, 
	episodes_failed INTEGER DEFAULT '0' NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	error_summary TEXT, 
	id UUID NOT NULL, 
	CONSTRAINT pk_ingestion_runs PRIMARY KEY (id), 
	CONSTRAINT ck_ingestion_runs_status CHECK (status IN ('running', 'completed', 'failed')), 
	CONSTRAINT ck_ingestion_runs_counts CHECK (episodes_processed >= 0 AND episodes_failed >= 0)
)""")
    op.execute("""CREATE TABLE app_data.profiles (
	id UUID NOT NULL, 
	display_name VARCHAR(200), 
	preferred_provider VARCHAR(30), 
	preferred_model VARCHAR(200), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_profiles PRIMARY KEY (id), 
	CONSTRAINT ck_profiles_provider CHECK (preferred_provider IN ('openai', 'ollama'))
)""")
    op.execute("""CREATE TABLE app_data.conversations (
	user_id UUID NOT NULL, 
	title VARCHAR(300) DEFAULT 'New chat' NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_conversations PRIMARY KEY (id), 
	CONSTRAINT fk_conversations_user_id_profiles FOREIGN KEY(user_id) REFERENCES app_data.profiles (id) ON DELETE CASCADE
)""")
    op.execute("""CREATE INDEX ix_conversations_user_id ON app_data.conversations (user_id)""")
    op.execute("""CREATE TABLE app_data.episode_revisions (
	episode_id UUID NOT NULL, 
	source_commit VARCHAR(64) NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	transcript_text TEXT NOT NULL, 
	status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
	ingestion_run_id UUID, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_episode_revisions PRIMARY KEY (id), 
	CONSTRAINT uq_episode_revisions_episode_id UNIQUE (episode_id, source_commit), 
	CONSTRAINT uq_revisions_id_episode UNIQUE (id, episode_id), 
	CONSTRAINT ck_episode_revisions_status CHECK (status IN ('pending', 'processing', 'ready', 'failed')), 
	CONSTRAINT fk_episode_revisions_episode_id_episodes FOREIGN KEY(episode_id) REFERENCES app_data.episodes (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_episode_revisions_ingestion_run_id_ingestion_runs FOREIGN KEY(ingestion_run_id) REFERENCES app_data.ingestion_runs (id) ON DELETE SET NULL
)""")
    op.execute("""CREATE INDEX ix_episode_revisions_episode_id ON app_data.episode_revisions (episode_id)""")
    op.execute("""CREATE TABLE app_data.artifacts (
	conversation_id UUID NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	type VARCHAR(20) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_artifacts PRIMARY KEY (id), 
	CONSTRAINT ck_artifacts_type CHECK (type IN ('code', 'essay', 'document')), 
	CONSTRAINT fk_artifacts_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES app_data.conversations (id) ON DELETE CASCADE
)""")
    op.execute("""CREATE INDEX ix_artifacts_conversation_id ON app_data.artifacts (conversation_id)""")
    op.execute("""CREATE TABLE app_data.messages (
	conversation_id UUID NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	content TEXT DEFAULT '' NOT NULL, 
	mode VARCHAR(20) DEFAULT 'answer' NOT NULL, 
	status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
	sequence_number INTEGER NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_messages PRIMARY KEY (id), 
	CONSTRAINT uq_messages_conversation_id UNIQUE (conversation_id, sequence_number), 
	CONSTRAINT uq_messages_id_conversation UNIQUE (id, conversation_id), 
	CONSTRAINT ck_messages_role CHECK (role IN ('user', 'assistant')), 
	CONSTRAINT ck_messages_mode CHECK (mode IN ('answer', 'essay', 'code')), 
	CONSTRAINT ck_messages_status CHECK (status IN ('pending', 'streaming', 'completed', 'failed', 'cancelled')), 
	CONSTRAINT ck_messages_sequence CHECK (sequence_number >= 0), 
	CONSTRAINT fk_messages_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES app_data.conversations (id) ON DELETE CASCADE
)""")
    op.execute("""CREATE TABLE app_data.transcript_chunks (
	episode_revision_id UUID NOT NULL, 
	chunk_index INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	speaker TEXT, 
	start_seconds INTEGER, 
	end_seconds INTEGER, 
	token_count INTEGER NOT NULL, 
	embedding VECTOR, 
	embedding_model VARCHAR(200), 
	embedding_dimensions INTEGER, 
	chunking_version VARCHAR(100) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_transcript_chunks PRIMARY KEY (id), 
	CONSTRAINT uq_transcript_chunks_episode_revision_id UNIQUE (episode_revision_id, chunking_version, chunk_index), 
	CONSTRAINT ck_transcript_chunks_position_size CHECK (chunk_index >= 0 AND token_count > 0), 
	CONSTRAINT ck_transcript_chunks_timestamps CHECK (start_seconds >= 0 AND end_seconds >= start_seconds), 
	CONSTRAINT ck_transcript_chunks_embedding_metadata CHECK ((embedding IS NULL AND embedding_model IS NULL AND embedding_dimensions IS NULL) OR (embedding IS NOT NULL AND embedding_model IS NOT NULL AND embedding_dimensions IS NOT NULL AND embedding_dimensions > 0 AND vector_dims(embedding) = embedding_dimensions)), 
	CONSTRAINT fk_transcript_chunks_episode_revision_id_episode_revisions FOREIGN KEY(episode_revision_id) REFERENCES app_data.episode_revisions (id) ON DELETE RESTRICT
)""")
    op.execute("""CREATE TABLE app_data.artifact_versions (
	artifact_id UUID NOT NULL, 
	message_id UUID, 
	version_number INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	language VARCHAR(100), 
	format VARCHAR(100) DEFAULT 'markdown' NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_artifact_versions PRIMARY KEY (id), 
	CONSTRAINT uq_artifact_versions_artifact_id UNIQUE (artifact_id, version_number), 
	CONSTRAINT ck_artifact_versions_version CHECK (version_number > 0), 
	CONSTRAINT fk_artifact_versions_artifact_id_artifacts FOREIGN KEY(artifact_id) REFERENCES app_data.artifacts (id) ON DELETE CASCADE, 
	CONSTRAINT fk_artifact_versions_message_id_messages FOREIGN KEY(message_id) REFERENCES app_data.messages (id) ON DELETE SET NULL
)""")
    op.execute("""CREATE TABLE app_data.generations (
	user_message_id UUID NOT NULL, 
	assistant_message_id UUID, 
	client_request_id UUID NOT NULL, 
	provider VARCHAR(30) NOT NULL, 
	model VARCHAR(200) NOT NULL, 
	status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
	prompt_version VARCHAR(100), 
	input_tokens INTEGER, 
	output_tokens INTEGER, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	error_code VARCHAR(100), 
	error_message TEXT, 
	id UUID NOT NULL, 
	CONSTRAINT pk_generations PRIMARY KEY (id), 
	CONSTRAINT uq_generations_user_message_id UNIQUE (user_message_id, client_request_id), 
	CONSTRAINT ck_generations_provider CHECK (provider IN ('openai', 'ollama')), 
	CONSTRAINT ck_generations_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')), 
	CONSTRAINT ck_generations_tokens CHECK (input_tokens >= 0 AND output_tokens >= 0), 
	CONSTRAINT ck_generations_timing CHECK (finished_at >= started_at), 
	CONSTRAINT fk_generations_user_message_id_messages FOREIGN KEY(user_message_id) REFERENCES app_data.messages (id) ON DELETE CASCADE, 
	CONSTRAINT fk_generations_assistant_message_id_messages FOREIGN KEY(assistant_message_id) REFERENCES app_data.messages (id) ON DELETE SET NULL
)""")
    op.execute("""CREATE INDEX ix_generations_user_message_id ON app_data.generations (user_message_id)""")
    op.execute("""CREATE TABLE app_data.message_sources (
	message_id UUID NOT NULL, 
	chunk_id UUID NOT NULL, 
	citation_number INTEGER NOT NULL, 
	quoted_text TEXT, 
	id UUID NOT NULL, 
	CONSTRAINT pk_message_sources PRIMARY KEY (id), 
	CONSTRAINT uq_message_sources_message_id UNIQUE (message_id, citation_number), 
	CONSTRAINT uq_sources_message_chunk UNIQUE (message_id, chunk_id), 
	CONSTRAINT ck_message_sources_citation CHECK (citation_number > 0), 
	CONSTRAINT fk_message_sources_message_id_messages FOREIGN KEY(message_id) REFERENCES app_data.messages (id) ON DELETE CASCADE, 
	CONSTRAINT fk_message_sources_chunk_id_transcript_chunks FOREIGN KEY(chunk_id) REFERENCES app_data.transcript_chunks (id) ON DELETE RESTRICT
)""")
    op.execute("""CREATE INDEX ix_message_sources_chunk_id ON app_data.message_sources (chunk_id)""")
    op.execute("""ALTER TABLE app_data.episodes ADD CONSTRAINT fk_episodes_active_revision FOREIGN KEY(active_revision_id, id) REFERENCES app_data.episode_revisions (id, episode_id)""")
    op.execute("""ALTER TABLE app_data.profiles ADD CONSTRAINT fk_profiles_auth_user FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE""")
    op.execute("""REVOKE ALL ON SCHEMA app_data FROM PUBLIC, anon, authenticated""")
    op.execute("""ALTER TABLE app_data.episodes ENABLE ROW LEVEL SECURITY""")
    op.execute("""REVOKE ALL ON TABLE app_data.episodes FROM PUBLIC, anon, authenticated""")
    op.execute("""ALTER TABLE app_data.ingestion_runs ENABLE ROW LEVEL SECURITY""")
    op.execute("""REVOKE ALL ON TABLE app_data.ingestion_runs FROM PUBLIC, anon, authenticated""")
    op.execute("""ALTER TABLE app_data.profiles ENABLE ROW LEVEL SECURITY""")
    op.execute("""REVOKE ALL ON TABLE app_data.profiles FROM PUBLIC, anon, authenticated""")
    op.execute("""ALTER TABLE app_data.conversations ENABLE ROW LEVEL SECURITY""")
    op.execute("""REVOKE ALL ON TABLE app_data.conversations FROM PUBLIC, anon, authenticated""")
    op.execute("""ALTER TABLE app_data.episode_revisions ENABLE ROW LEVEL SECURITY""")
    op.execute("""REVOKE ALL ON TABLE app_data.episode_revisions FROM PUBLIC, anon, authenticated""")
    op.execute("""ALTER TABLE app_data.artifacts ENABLE ROW LEVEL SECURITY""")
    op.execute("""REVOKE ALL ON TABLE app_data.artifacts FROM PUBLIC, anon, authenticated""")
    op.execute("""ALTER TABLE app_data.messages ENABLE ROW LEVEL SECURITY""")
    op.execute("""REVOKE ALL ON TABLE app_data.messages FROM PUBLIC, anon, authenticated""")
    op.execute("""ALTER TABLE app_data.transcript_chunks ENABLE ROW LEVEL SECURITY""")
    op.execute("""REVOKE ALL ON TABLE app_data.transcript_chunks FROM PUBLIC, anon, authenticated""")
    op.execute("""ALTER TABLE app_data.artifact_versions ENABLE ROW LEVEL SECURITY""")
    op.execute("""REVOKE ALL ON TABLE app_data.artifact_versions FROM PUBLIC, anon, authenticated""")
    op.execute("""ALTER TABLE app_data.generations ENABLE ROW LEVEL SECURITY""")
    op.execute("""REVOKE ALL ON TABLE app_data.generations FROM PUBLIC, anon, authenticated""")
    op.execute("""ALTER TABLE app_data.message_sources ENABLE ROW LEVEL SECURITY""")
    op.execute("""REVOKE ALL ON TABLE app_data.message_sources FROM PUBLIC, anon, authenticated""")


def downgrade():
    # Destructive: removes application records. Supabase auth and pgvector are retained.
    op.execute("ALTER TABLE app_data.episodes DROP CONSTRAINT fk_episodes_active_revision")
    op.drop_table("message_sources", schema="app_data")
    op.drop_table("generations", schema="app_data")
    op.drop_table("artifact_versions", schema="app_data")
    op.drop_table("transcript_chunks", schema="app_data")
    op.drop_table("messages", schema="app_data")
    op.drop_table("artifacts", schema="app_data")
    op.drop_table("episode_revisions", schema="app_data")
    op.drop_table("conversations", schema="app_data")
    op.drop_table("profiles", schema="app_data")
    op.drop_table("ingestion_runs", schema="app_data")
    op.drop_table("episodes", schema="app_data")
