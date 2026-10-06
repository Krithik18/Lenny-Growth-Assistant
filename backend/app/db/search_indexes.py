"""Stable SQL expressions shared by search queries and migration metadata."""
from pgvector.sqlalchemy import Vector
from sqlalchemy import and_, case, cast, literal_column


def openai_search_vector(table):
    columns = table.c
    compatible = and_(
        columns.provider == literal_column("'openai'"),
        columns.model == literal_column("'text-embedding-3-small'"),
        columns.dimensions == literal_column("1536"),
        columns.input_version == literal_column("'raw-chunk-v1'"),
    )
    # CASE protects the dimension cast even if PostgreSQL evaluates it before
    # WHERE. Future local vectors remain in their own embedding space.
    return cast(case((compatible, columns.embedding)), Vector(1536))
