"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings
from app.db.session import Database
from app.api.routes.rag import router as rag_router
from app.llm.client import OpenAIClient
from app.rag.service import RAGService
from app.api.routes.workspace import router as workspace_router
from fastapi.staticfiles import StaticFiles
from pathlib import Path


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database = Database(settings) if settings.database_url.get_secret_value() else None
        application.state.database = database
        application.state.settings = settings
        client = OpenAIClient(settings.openai_api_key.get_secret_value()) if settings.openai_api_key.get_secret_value() else None
        application.state.rag = RAGService(database, client) if database and client else None
        try:
            yield
        finally:
            if client is not None:
                await client.close()
            if database is not None:
                await database.close()

    application = FastAPI(
        title=settings.app_name,
        description="Backend for podcast-grounded growth advice, essays, and artifacts.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(health_router)
    application.include_router(rag_router)
    application.include_router(workspace_router)
    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend.is_dir():
        application.mount("/", StaticFiles(directory=frontend, html=True), name="workspace")
    return application


app = create_app()
