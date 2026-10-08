"""Standalone BGE-M3 retrieval over the stored OpenRouter embedding space."""

from app.db.session import Database
from app.llm.client import OpenRouterClient
from app.rag.openrouter_embeddings import OpenRouterEmbeddings
from app.rag.retrieval import retrieve as retrieve_candidates
from app.schemas.retrieval import RetrievalResult
from app.rag.query_intent import supported_query
from app.rag.openrouter_scope import classify_scope
from pydantic import Field


class OpenRouterRetrievalResult(RetrievalResult):
    search_question: str = ""
    requested_people: list[str] = Field(default_factory=list)
    excluded_people: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    ranking_diagnostics: dict = Field(default_factory=dict)
    scope_decision: dict = Field(default_factory=dict)


async def retrieve(
    database: Database,
    client: OpenRouterClient,
    question: str,
    chunking_version: str,
    top_k: int = 5,
    hybrid: bool = True,
    candidate_pool: bool = False,
    concurrent_search: bool = True,
    rank_fusion: bool = False,
) -> RetrievalResult:
    """Embed the query with BGE-M3 and reuse filtered search/candidate selection.

    Semantic, keyword, and neighbor candidates must have compatible OpenRouter
    embeddings. This entry point performs no reranking or answer generation.
    """
    if not question.strip() or len(question.strip()) > 12000 or not 1 <= top_k <= 20:
        raise ValueError("Provide a nonempty question up to 12000 characters and top_k from 1 to 20.")
    original_question = question.strip()
    search_question, blocked = supported_query(original_question, strict_only=True)
    if blocked:
        return OpenRouterRetrievalResult(question=question.strip(), provider="openrouter",
            embedding_model="baai/bge-m3", passages=[], blocked_reason=blocked)
    # The preliminary gate flattens clauses/newlines. Scope needs the original
    # context boundary to distinguish current identities from old artifact titles.
    decision = await classify_scope(client, original_question)
    if not decision.in_scope:
        return OpenRouterRetrievalResult(question=original_question, provider="openrouter",
            embedding_model="baai/bge-m3", passages=[], blocked_reason=decision.reason,
            scope_decision=decision.model_dump())
    diagnostics = {}
    result = await retrieve_candidates(
        database, OpenRouterEmbeddings(client), decision.search_question, chunking_version,
        top_k=top_k, hybrid=hybrid, candidate_pool=candidate_pool,
        concurrent_search=concurrent_search, rank_fusion=rank_fusion,
        query_aware=True, diagnostics=diagnostics, domain_checked=True,
    )
    return OpenRouterRetrievalResult(**result.model_copy(update={"question": original_question}).model_dump(),
        **diagnostics, scope_decision=decision.model_dump())
