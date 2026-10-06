"""Index expressions must isolate embedding spaces and retain dimension typmods."""
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex
from app.db.models import ChunkEmbedding, TranscriptChunk
from app.db.search_indexes import openai_search_vector


def test_dimension_cast_wraps_safe_case():
    sql = str(openai_search_vector(ChunkEmbedding.__table__).compile(dialect=postgresql.dialect()))
    assert sql.startswith("CAST(CASE WHEN")
    assert "END AS VECTOR(1536)" in sql
    for value in ("'openai'", "'text-embedding-3-small'", "'raw-chunk-v1'"):
        assert value in sql
    assert "%(" not in sql


def test_search_index_metadata_matches_queries():
    indexes = {index.name: str(CreateIndex(index).compile(dialect=postgresql.dialect()))
               for table in (ChunkEmbedding.__table__, TranscriptChunk.__table__) for index in table.indexes}
    assert "USING hnsw" in indexes["ix_embeddings_openai_hnsw"]
    assert "vector_cosine_ops" in indexes["ix_embeddings_openai_hnsw"]
    assert "USING gin (to_tsvector('english'::regconfig" in indexes["ix_chunks_english_search"]
