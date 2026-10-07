from io import StringIO
from pathlib import Path
from typing import get_args, get_type_hints

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.models import ChunkEmbedding
from app.rag.embeddings import EmbeddingSpec


@pytest.mark.parametrize("provider,model,dimensions", [
    ("openai", "text-embedding-3-small", 1536),
    ("openrouter", "baai/bge-m3", 1024),
])
def test_supported_embedding_providers(provider, model, dimensions):
    spec = EmbeddingSpec(provider, model, dimensions)
    assert spec.provider == provider
    assert spec.model == model
    assert spec.dimensions == dimensions


@pytest.mark.parametrize("provider", ["ollama", "unknown", ""])
def test_unsupported_embedding_providers_are_rejected(provider):
    with pytest.raises(ValueError):
        EmbeddingSpec(provider, "model", 1024)


def test_provider_type_matches_supported_providers():
    assert set(get_args(get_type_hints(EmbeddingSpec)["provider"])) == {"openai", "openrouter"}


def test_chunk_embeddings_constraint_accepts_only_current_providers():
    sql = str(CreateTable(ChunkEmbedding.__table__).compile(dialect=postgresql.dialect()))
    assert "CONSTRAINT ck_chunk_embeddings_provider CHECK (provider IN ('openai', 'openrouter'))" in sql
    assert "ollama" not in sql
    assert "vector_dims(embedding) = dimensions" in sql
    assert "uq_chunk_embeddings_config" in sql


@pytest.mark.parametrize("direction,providers", [
    ("upgrade", "'openai', 'openrouter'"),
    ("downgrade", "'openai', 'ollama'"),
])
def test_provider_migration_replaces_constraint_without_changing_data(direction, providers):
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"), output_buffer=output)
    if direction == "upgrade":
        command.upgrade(config, "0004_search_indexes:0005_openrouter_embeddings", sql=True)
    else:
        command.downgrade(config, "0005_openrouter_embeddings:0004_search_indexes", sql=True)
    sql = output.getvalue()
    drop = "ALTER TABLE app_data.chunk_embeddings DROP CONSTRAINT ck_chunk_embeddings_provider"
    add = f"ALTER TABLE app_data.chunk_embeddings ADD CONSTRAINT ck_chunk_embeddings_provider CHECK (provider IN ({providers}))"
    assert drop in sql
    assert add in sql
    assert sql.index(drop) < sql.index(add)
    assert "DELETE FROM" not in sql
    assert "UPDATE app_data.chunk_embeddings" not in sql
    assert "DROP TABLE" not in sql
    assert "NOT VALID" not in sql
