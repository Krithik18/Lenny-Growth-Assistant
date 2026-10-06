"""Allow distinct archive members to reference the same source video."""
from alembic import op

revision = "0003_archive_video_ids"
down_revision = "0002_zip_retrieval"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("uq_episodes_video_id", "episodes", schema="app_data", type_="unique")
    op.create_index("ix_episodes_video_id", "episodes", ["video_id"], schema="app_data")


def downgrade():
    # PostgreSQL refuses this if duplicates exist; never silently delete source data.
    op.create_unique_constraint("uq_episodes_video_id", "episodes", ["video_id"], schema="app_data")
    op.drop_index("ix_episodes_video_id", table_name="episodes", schema="app_data")
