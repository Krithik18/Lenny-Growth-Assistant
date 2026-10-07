"""Replace Ollama with OpenRouter in the chunk embedding provider constraint.

Existing Ollama embeddings must be handled before upgrading. Downgrading requires
handling OpenRouter embeddings first. Neither direction relabels or deletes data.
"""

from alembic import op

revision = "0005_openrouter_embeddings"
down_revision = "0004_search_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(op.f("ck_chunk_embeddings_provider"), "chunk_embeddings",
                       schema="app_data", type_="check")
    op.create_check_constraint(op.f("ck_chunk_embeddings_provider"), "chunk_embeddings",
                               "provider IN ('openai', 'openrouter')", schema="app_data")


def downgrade():
    op.drop_constraint(op.f("ck_chunk_embeddings_provider"), "chunk_embeddings",
                       schema="app_data", type_="check")
    op.create_check_constraint(op.f("ck_chunk_embeddings_provider"), "chunk_embeddings",
                               "provider IN ('openai', 'ollama')", schema="app_data")
