"""ZIP provenance, passage offsets, and separate embedding providers.

Prepared only; apply explicitly after reviewing the ingestion flow.
Legacy vector columns are retained without alteration; new retrieval never uses them.
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0002_zip_retrieval"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL search_path TO public, extensions, app_data")
    op.add_column("episode_revisions", sa.Column("source_archive_sha256", sa.String(64), nullable=True), schema="app_data")
    op.create_index("ix_episode_revisions_source_archive_sha256", "episode_revisions", ["source_archive_sha256"], schema="app_data")
    op.add_column("transcript_chunks", sa.Column("start_char", sa.Integer(), nullable=True), schema="app_data")
    op.add_column("transcript_chunks", sa.Column("end_char", sa.Integer(), nullable=True), schema="app_data")
    op.create_check_constraint(op.f("ck_transcript_chunks_char_offsets"), "transcript_chunks", "start_char >= 0 AND end_char > start_char", schema="app_data")
    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("input_version", sa.String(100), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_chunk_embeddings"),
        sa.ForeignKeyConstraint(["chunk_id"], ["app_data.transcript_chunks.id"], ondelete="CASCADE", name="fk_chunk_embeddings_chunk_id_transcript_chunks"),
        sa.UniqueConstraint("chunk_id", "provider", "model", "dimensions", "input_version", name="uq_chunk_embeddings_config"),
        sa.CheckConstraint("provider IN ('openai', 'ollama')", name=op.f("ck_chunk_embeddings_provider")),
        sa.CheckConstraint("dimensions > 0 AND vector_dims(embedding) = dimensions", name=op.f("ck_chunk_embeddings_dimensions")),
        schema="app_data",
    )
    op.create_index("ix_chunk_embeddings_config", "chunk_embeddings", ["provider", "model", "dimensions", "input_version"], schema="app_data")
    op.execute("ALTER TABLE app_data.chunk_embeddings ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE app_data.chunk_embeddings FROM PUBLIC, anon, authenticated")


def downgrade():
    op.drop_table("chunk_embeddings", schema="app_data")
    op.drop_constraint(op.f("ck_transcript_chunks_char_offsets"), "transcript_chunks", type_="check", schema="app_data")
    op.drop_column("transcript_chunks", "end_char", schema="app_data")
    op.drop_column("transcript_chunks", "start_char", schema="app_data")
    op.drop_index("ix_episode_revisions_source_archive_sha256", table_name="episode_revisions", schema="app_data")
    op.drop_column("episode_revisions", "source_archive_sha256", schema="app_data")
