"""Offline validation; these checks do not replace applying migrations to PostgreSQL."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

from app.core.config import Settings
from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import database_url, get_session


def test_expected_tables_compile_for_postgresql():
    expected = {"profiles", "conversations", "messages", "generations", "episodes",
                "episode_revisions", "transcript_chunks", "message_sources",
                "artifacts", "artifact_versions", "ingestion_runs"}
    assert {table.name for table in Base.metadata.tables.values()} == expected
    for table in Base.metadata.sorted_tables:
        sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert f"CREATE TABLE app_data.{table.name}" in sql


def test_url_normalization_and_secret_masking():
    raw = "postgresql://user:p%40ss@localhost:5432/db?sslmode=require"
    url = database_url(raw)
    assert url.drivername == "postgresql+asyncpg"
    assert url.password == "p@ss"
    assert url.query["ssl"] == "require"
    assert "sslmode" not in url.query
    assert raw not in repr(Settings(_env_file=None, database_url=raw))


@pytest.mark.parametrize("raw", ["", "sqlite:///file.db", "https://user:secret@project.example/db"])
def test_invalid_database_urls_do_not_expose_credentials(raw):
    with pytest.raises(ValueError) as error:
        database_url(raw)
    assert "secret" not in str(error.value)


def test_missing_database_dependency_is_503():
    async def check():
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=None)))
        with pytest.raises(HTTPException) as error:
            await anext(get_session(request))
        assert error.value.status_code == 503
    asyncio.run(check())


@pytest.mark.parametrize("fails", [False, True])
def test_session_cleanup_rolls_back_without_auto_commit(fails):
    async def check():
        session = MagicMock()
        session.in_transaction.return_value = True
        session.rollback = AsyncMock()
        session.commit = AsyncMock()
        manager = AsyncMock()
        manager.__aenter__.return_value = session
        database = SimpleNamespace(sessions=lambda: manager)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=database)))
        dependency = get_session(request)
        assert await anext(dependency) is session
        if fails:
            with pytest.raises(RuntimeError):
                await dependency.athrow(RuntimeError("operation failed"))
        else:
            await dependency.aclose()
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
        manager.__aexit__.assert_awaited_once()
    asyncio.run(check())
