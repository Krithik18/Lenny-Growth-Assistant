"""OpenRouter RAG wiring with the shared grounded-answer/refinement flow."""

import asyncio
import logging

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import Database
from app.ingestion.chunker import TranscriptChunker
from app.llm.client import OpenRouterClient, ProviderError
from app.llm.openrouter_provider import OpenRouterAnswerProvider
from app.rag.openrouter_embeddings import OpenRouterEmbeddings
from app.rag.openrouter_rerank import rerank
from app.rag.openrouter_retrieval import retrieve
from app.rag.service import RAGService
from app.schemas.retrieval import RetrievalResult
from app.rag.query_intent import balance_people
from app.rag.context import build_context
from app.rag.answer_fallback import fallback_answer
from app.schemas.answer import AnswerResult

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 60
GENERATION_TIMEOUT = 40


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

    async def ask(self, question, *, context_budget=4000):
        if not 500 <= context_budget <= 12000:
            raise ValueError("context_budget must be from 500 to 12000")
        sources, answer = {}, None
        try:
            # One request-wide budget includes optional refinement. Cancellation is
            # allowed to propagate; provider/database outages become usable responses.
            async with asyncio.timeout(REQUEST_TIMEOUT):
                retrieval = await self.retrieve(question, top_k=20)
                sources = build_context(retrieval.passages, token_budget=context_budget)
                answer = await asyncio.wait_for(self.generator.answer(question, sources), GENERATION_TIMEOUT)
                if sources and answer.missing_topics:
                    found = await asyncio.gather(*(
                        self.retrieve(topic[:2000], top_k=10, hybrid=True)
                        for topic in answer.missing_topics[:2]
                    ), return_exceptions=True)
                    groups = []
                    for result in found:
                        if isinstance(result, (ProviderError, SQLAlchemyError, TimeoutError)):
                            continue
                        if isinstance(result, BaseException):
                            raise result
                        groups.append(result.passages)
                    seen = {p.chunk_id for p in sources.values()}
                    candidates = []
                    for rank in range(10):
                        for group in groups:
                            if rank < len(group) and group[rank].chunk_id not in seen:
                                candidates.append(group[rank])
                                seen.add(group[rank].chunk_id)
                    extra = build_context(candidates, token_budget=2000) if candidates else {}
                    if extra:
                        expanded = dict(sources)
                        for passage in extra.values():
                            expanded[f"S{len(expanded) + 1}"] = passage
                        revised = await asyncio.wait_for(self.generator.answer(question, expanded), GENERATION_TIMEOUT)
                        order = {"unsupported": 0, "partial": 1, "complete": 2}
                        if order[revised.coverage] >= order[answer.coverage]:
                            answer, sources = revised, expanded
        except (ProviderError, SQLAlchemyError, TimeoutError) as error:
            logger.warning("OpenRouter RAG returning best available response after %s", type(error).__name__)
            if answer is None:
                answer = fallback_answer(question, sources)
        cited = set(answer.summary_citation_ids) | {cid for section in answer.sections for cid in section.citation_ids}
        return AnswerResult(question=question, model=self.generator.model, answer=answer,
                            sources={sid: source for sid, source in sources.items() if sid in cited})

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
