"""Retrieval and generation remain independently callable stages."""

from app.ingestion.chunker import TranscriptChunker
from app.llm.openai_provider import OpenAIAnswerProvider
from app.rag.context import build_context
from app.rag.openai_embeddings import OpenAIEmbeddings
from app.rag.retrieval import retrieve
from app.schemas.answer import AnswerResult
from app.llm.client import ProviderError
from sqlalchemy.exc import SQLAlchemyError


class RAGService:
    def __init__(self, database, client):
        self.database = database
        self.embeddings = OpenAIEmbeddings(client)
        self.generator = OpenAIAnswerProvider(client)

    async def retrieve(self, question, top_k=5):
        return await retrieve(self.database, self.embeddings, question, TranscriptChunker().version, top_k)

    async def ask(self, question):
        retrieval = await self.retrieve(question, top_k=20)
        sources = build_context(retrieval.passages)
        answer = await self.generator.answer(question, sources)
        if sources and answer.missing_topics:
            # One bounded follow-up round. Preserve existing evidence and look for up to
            # two missing aspects, rather than repeatedly searching the broad question.
            try:
                candidates = []
                seen = {passage.chunk_id for passage in sources.values()}
                groups = []
                for topic in answer.missing_topics[:2]:
                    found = await self.retrieve(topic[:2000], top_k=5)
                    groups.append(found.passages)
                for rank in range(5):
                    for group in groups:
                        if rank < len(group) and group[rank].chunk_id not in seen:
                            candidates.append(group[rank])
                            seen.add(group[rank].chunk_id)
                extra = build_context(candidates, token_budget=2000)
                if extra:
                    expanded = dict(sources)
                    for passage in extra.values():
                        expanded[f"S{len(expanded) + 1}"] = passage
                    revised = await self.generator.answer(question, expanded)
                    order = {"unsupported": 0, "partial": 1, "complete": 2}
                    if order[revised.coverage] >= order[answer.coverage]:
                        answer, sources = revised, expanded
            except (ProviderError, SQLAlchemyError, TimeoutError):
                # A failed optional refinement must not discard a valid first answer.
                pass
        cited = set(answer.summary_citation_ids) | {
            citation for section in answer.sections for citation in section.citation_ids}
        return AnswerResult(question=question, model=self.generator.model, answer=answer,
                            sources={key: value for key, value in sources.items() if key in cited})
