from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.models import Profile, Generation


def cleanup_sql(direction):
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"), output_buffer=output)
    if direction == "upgrade":
        command.upgrade(config, "0005_openrouter_embeddings:0006_remove_ollama", sql=True)
    else:
        command.downgrade(config, "0006_remove_ollama:0005_openrouter_embeddings", sql=True)
    return output.getvalue()


@pytest.mark.parametrize("model,column", [(Profile, "preferred_provider"), (Generation, "provider")])
def test_chat_provider_constraints_no_longer_support_ollama(model, column):
    sql = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
    assert f"CHECK ({column} IN ('openai'))" in sql
    assert "ollama" not in sql


def test_cleanup_targets_retired_provider_and_preserves_profiles():
    sql = cleanup_sql("upgrade")
    for table in ("chunk_embeddings", "generations"):
        assert f"DELETE FROM app_data.{table} WHERE provider = 'ollama'" in sql
    assert "SET preferred_provider = NULL, preferred_model = NULL" in sql
    assert "WHERE preferred_provider = 'ollama'" in sql
    assert "DELETE FROM app_data.profiles" not in sql
    assert "DELETE FROM app_data.conversations" not in sql
    assert "DELETE FROM app_data.messages" not in sql
    assert "CHECK (preferred_provider IN ('openai'))" in sql
    assert "CHECK (provider IN ('openai'))" in sql
    assert sql.index("DELETE FROM app_data.generations") < sql.index("DROP CONSTRAINT ck_generations_provider")
    assert sql.index("UPDATE app_data.profiles") < sql.index("DROP CONSTRAINT ck_profiles_provider")


def test_cleanup_downgrade_restores_constraints_without_recreating_data():
    sql = cleanup_sql("downgrade")
    assert "CHECK (provider IN ('openai', 'ollama'))" in sql
    assert "CHECK (preferred_provider IN ('openai', 'ollama'))" in sql
    assert "INSERT INTO app_data.generations" not in sql
    assert "UPDATE app_data.profiles" not in sql
    assert "DELETE FROM" not in sql
