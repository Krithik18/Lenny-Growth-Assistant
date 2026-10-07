"""OpenRouter RAG wiring with the shared grounded-answer/refinement flow."""

from app.db.session import Database
from app.ingestion.chunker import TranscriptChunker
from app.llm.client import OpenRouterClient
from app.llm.openrouter_provider import OpenRouterAnswerProvider
from app.rag.openrouter_embeddings import OpenRouterEmbeddings
from app.rag.openrouter_rerank import rerank
from app.rag.openrouter_retrieval import retrieve
from app.rag.service import RAGService
from app.schemas.retrieval import RetrievalResult
from app.rag.query_intent import balance_people


class OpenRouterRAGService(RAGService):
    """Reuse ask/refinement, supplying only OpenRouter retrieval and generation."""

    def __init__(
        self, database: Database, client: OpenRouterClient,
        *, reranking=True, concurrent_search=True,
    ):
        self.database = database
        self.client = client
        self.reranking = reranking
        self.concurrent_search = concurrent_search
        self.embeddings = OpenRouterEmbeddings(client)
        self.generator = OpenRouterAnswerProvider(client)

    async def retrieve(self, question, top_k=5, hybrid=True) -> RetrievalResult:
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be from 1 to 20")
        options = {"hybrid": hybrid, "candidate_pool": True, "concurrent_search": self.concurrent_search}
        if not self.reranking:
            options["rank_fusion"] = True
        result = await retrieve(
            self.database, self.client, question, TranscriptChunker().version,
            20, **options,
        )
        search_question = getattr(result, "search_question", "") or question
        diagnostics = {}
        ranked = await rerank(self.client, search_question, result.passages, diagnostics=diagnostics) if self.reranking else result.passages
        ranked = balance_people(ranked, search_question)
        if hasattr(result, "ranking_diagnostics"):
            result = result.model_copy(update={"ranking_diagnostics": diagnostics})
        return result.model_copy(update={"passages": ranked[:top_k]})
