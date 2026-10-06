from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_sql(direction):
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"), output_buffer=output)
    if direction == "upgrade":
        command.upgrade(config, "head", sql=True)
    else:
        command.downgrade(config, "head:base", sql=True)
    return output.getvalue()


def test_initial_migration_security_and_dependencies():
    sql = migration_sql("upgrade")
    tables = ["profiles", "conversations", "messages", "generations", "episodes",
              "episode_revisions", "transcript_chunks", "message_sources",
              "artifacts", "artifact_versions", "ingestion_runs"]
    for table in tables:
        assert f"CREATE TABLE app_data.{table}" in sql
        assert f"ALTER TABLE app_data.{table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"REVOKE ALL ON TABLE app_data.{table}" in sql
    assert "CREATE TABLE auth.users" not in sql
    assert "REFERENCES auth.users(id)" in sql
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert sql.index("CREATE SCHEMA") < sql.index("CREATE TABLE app_data.alembic_version")
    assert sql.index("CREATE TABLE app_data.episode_revisions") < sql.index("ADD CONSTRAINT fk_episodes_active_revision")


def test_downgrade_preserves_auth_and_extension():
    sql = migration_sql("downgrade")
    assert "DROP TABLE app_data.profiles" in sql
    assert "DROP TABLE auth.users" not in sql
    assert "DROP EXTENSION" not in sql
    assert sql.index("DROP CONSTRAINT fk_episodes_active_revision") < sql.index("DROP TABLE app_data.episode_revisions")


def test_archive_members_can_share_video_metadata():
    sql = migration_sql("upgrade")
    assert "DROP CONSTRAINT uq_episodes_video_id" in sql
    assert "CREATE INDEX ix_episodes_video_id" in sql
