"""Standalone BGE-M3 retrieval over the stored OpenRouter embedding space."""

from app.db.session import Database
from app.llm.client import OpenRouterClient
from app.rag.openrouter_embeddings import OpenRouterEmbeddings
from app.rag.retrieval import retrieve as retrieve_candidates
from app.schemas.retrieval import RetrievalResult


async def retrieve(
    database: Database,
    client: OpenRouterClient,
    question: str,
    chunking_version: str,
    top_k: int = 5,
    hybrid: bool = True,
    candidate_pool: bool = False,
    concurrent_search: bool = False,
    rank_fusion: bool = False,
) -> RetrievalResult:
    """Embed the query with BGE-M3 and reuse filtered search/candidate selection.

    Semantic, keyword, and neighbor candidates must have compatible OpenRouter
    embeddings. This entry point performs no reranking or answer generation.
    """
    return await retrieve_candidates(
        database, OpenRouterEmbeddings(client), question, chunking_version,
        top_k=top_k, hybrid=hybrid, candidate_pool=candidate_pool,
        concurrent_search=concurrent_search, rank_fusion=rank_fusion,
    )
