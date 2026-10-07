"""Local development endpoints while user authentication is deferred."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from app.llm.client import ProviderError
from app.schemas.answer import AnswerResult, QuestionRequest
from app.schemas.retrieval import RetrievalResult

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


def check_rag_access(request: Request):
    if request.app.state.settings.app_env == "production":
        raise HTTPException(403, "RAG endpoints require authentication before production use.")
    if request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "RAG endpoints currently support local development only.")


def get_rag(request: Request):
    check_rag_access(request)
    service = request.app.state.rag
    if service is None:
        raise HTTPException(503, "Configure DATABASE_URL and OPENAI_API_KEY first.")
    return service


async def execute(operation):
    try:
        return await operation
    except ProviderError as error:
        raise HTTPException(502, str(error)) from None
    except SQLAlchemyError:
        raise HTTPException(503, "Knowledge database is unavailable; check migrations and indexing.") from None


@router.post("/retrieve", response_model=RetrievalResult)
async def retrieve_evidence(body: QuestionRequest, service=Depends(get_rag)):
    return await execute(service.retrieve(body.question))


@router.post("/ask", response_model=AnswerResult)
async def ask(body: QuestionRequest, service=Depends(get_rag)):
    return await execute(service.ask(body.question))
