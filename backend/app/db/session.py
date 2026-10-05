"""Async database lifecycle. Services own commits; request cleanup rolls back leftovers."""

from collections.abc import AsyncIterator

from fastapi import HTTPException, Request
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings


def database_url(raw: str) -> URL:
    """Accept standard Supabase PostgreSQL URLs without exposing credentials in errors."""
    try:
        url = make_url(raw)
        if url.drivername not in ("postgres", "postgresql", "postgresql+asyncpg"):
            raise ValueError
        if not url.host or not url.database:
            raise ValueError
        query = dict(url.query)
        if "sslmode" in query:
            query["ssl"] = query.pop("sslmode")
        return url.set(drivername="postgresql+asyncpg", query=query)
    except Exception:
        raise ValueError("DATABASE_URL must be a valid PostgreSQL connection URL.") from None


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_async_engine(
            database_url(settings.database_url.get_secret_value()),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_timeout=settings.database_timeout_seconds,
            connect_args={"timeout": settings.database_timeout_seconds},
            hide_parameters=True,
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    async with database.sessions() as session:
        try:
            yield session
        finally:
            # Never auto-commit after a response: services explicitly commit before returning.
            if session.in_transaction():
                await session.rollback()
