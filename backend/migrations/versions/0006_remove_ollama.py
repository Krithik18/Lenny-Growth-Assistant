"""Remove retired provider records and preferences, then restrict generation to OpenAI.

Downgrade restores the old constraints, but cannot recover deleted provider records
or cleared preferences.
"""

from alembic import op

revision = "0006_remove_ollama"
down_revision = "0005_openrouter_embeddings"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DELETE FROM app_data.chunk_embeddings WHERE provider = 'ollama'")
    op.execute("DELETE FROM app_data.generations WHERE provider = 'ollama'")
    op.execute("""UPDATE app_data.profiles
                  SET preferred_provider = NULL, preferred_model = NULL
                  WHERE preferred_provider = 'ollama'""")
    op.drop_constraint(op.f("ck_profiles_provider"), "profiles", schema="app_data", type_="check")
    op.create_check_constraint(op.f("ck_profiles_provider"), "profiles",
                               "preferred_provider IN ('openai')", schema="app_data")
    op.drop_constraint(op.f("ck_generations_provider"), "generations", schema="app_data", type_="check")
    op.create_check_constraint(op.f("ck_generations_provider"), "generations",
                               "provider IN ('openai')", schema="app_data")


def downgrade():
    op.drop_constraint(op.f("ck_generations_provider"), "generations", schema="app_data", type_="check")
    op.create_check_constraint(op.f("ck_generations_provider"), "generations",
                               "provider IN ('openai', 'ollama')", schema="app_data")
    op.drop_constraint(op.f("ck_profiles_provider"), "profiles", schema="app_data", type_="check")
    op.create_check_constraint(op.f("ck_profiles_provider"), "profiles",
                               "preferred_provider IN ('openai', 'ollama')", schema="app_data")
