"""Separate process liveness from database and schema readiness."""

from typing import Literal

import asyncio

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.schema_version import SCHEMA_REVISION

router = APIRouter(prefix="/health", tags=["Health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["ready", "not_configured", "unavailable", "migration_required"]


@router.get("/live", response_model=LivenessResponse)
async def live() -> LivenessResponse:
    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse, responses={503: {"model": ReadinessResponse}})
async def ready(request: Request, response: Response) -> ReadinessResponse:
    database = getattr(request.app.state, "database", None)
    if database is None:
        response.status_code = 503
        return ReadinessResponse(status="not_ready", database="not_configured")
    try:
        async with asyncio.timeout(request.app.state.settings.database_timeout_seconds):
            async with database.engine.connect() as connection:
                version_table = await connection.scalar(text("SELECT to_regclass('app_data.alembic_version')"))
                revision = None
                if version_table is not None:
                    revision = await connection.scalar(text("SELECT version_num FROM app_data.alembic_version"))
        if revision != SCHEMA_REVISION:
            response.status_code = 503
            return ReadinessResponse(status="not_ready", database="migration_required")
    except (SQLAlchemyError, OSError, TimeoutError):
        response.status_code = 503
        return ReadinessResponse(status="not_ready", database="unavailable")
    return ReadinessResponse(status="ready", database="ready")
