"""Shared ORM metadata; application tables live outside Supabase's public API schema."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "app_data"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA, naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


class IdentityMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class CreatedMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UpdatedMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
