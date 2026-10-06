"""Index the primary OpenAI embedding space and English transcript keywords."""
from alembic import op

revision = "0004_search_indexes"
down_revision = "0003_archive_video_ids"
branch_labels = None
depends_on = None


def upgrade():
    # Building a graph can exceed Supabase's default statement timeout. These
    # settings apply only inside this migration transaction, not application traffic.
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute("SET LOCAL maintenance_work_mem = '256MB'")
    op.execute("""CREATE INDEX ix_embeddings_openai_hnsw ON app_data.chunk_embeddings
      USING hnsw ((CASE WHEN provider='openai' AND model='text-embedding-3-small'
      AND dimensions=1536 AND input_version='raw-chunk-v1'
      THEN embedding ELSE NULL END::vector(1536)) vector_cosine_ops)""")
    op.execute("""CREATE INDEX ix_chunks_english_search ON app_data.transcript_chunks
      USING gin (to_tsvector('english'::regconfig, content))""")
    op.execute("ANALYZE app_data.chunk_embeddings")
    op.execute("ANALYZE app_data.transcript_chunks")


def downgrade():
    op.drop_index("ix_chunks_english_search", table_name="transcript_chunks", schema="app_data")
    op.drop_index("ix_embeddings_openai_hnsw", table_name="chunk_embeddings", schema="app_data")
