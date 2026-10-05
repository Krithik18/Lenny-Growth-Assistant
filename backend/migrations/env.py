"""Alembic configuration for the app_data schema; never manage Supabase auth tables."""

import asyncio

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.base import Base, SCHEMA
from app.db import models  # noqa: F401 -- register tables
from app.db.session import database_url


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == SCHEMA
    return True


def include_object(obj, name, type_, reflected, compare_to):
    # This external FK is maintained explicitly in the initial migration.
    return not (type_ == "foreign_key_constraint" and name == "fk_profiles_auth_user")


def configure(connection=None, url=None):
    context.configure(
        connection=connection, url=url, target_metadata=Base.metadata,
        include_schemas=True, include_name=include_name, include_object=include_object,
        version_table_schema=SCHEMA, compare_type=True,
        literal_binds=connection is None,
    )


def run(connection):
    # Alembic creates its version table before invoking upgrade().
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    connection.commit()
    configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    raw = get_settings().database_url.get_secret_value()
    if not raw:
        raise RuntimeError("Set DATABASE_URL in backend/.env before running migrations.")
    engine = create_async_engine(database_url(raw), poolclass=pool.NullPool, hide_parameters=True)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    # Offline SQL generation requires no credentials or database connection.
    configure(url="postgresql+asyncpg://localhost/placeholder")
    with context.begin_transaction():
        context.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
        context.run_migrations()
else:
    asyncio.run(run_online())
