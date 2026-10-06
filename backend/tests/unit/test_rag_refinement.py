import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.llm.client import ProviderError
from app.rag.service import RAGService
from app.rag.retrieval import fuse_rankings, unique_passages
from app.schemas.answer import GroundedAnswer, AnswerSection
from app.schemas.retrieval import RetrievedPassage


def passage(text):
    return RetrievedPassage(chunk_id=uuid4(), episode_id=uuid4(), episode_revision_id=uuid4(),
        title="Episode", guest="Guest", source_url=None, archive_member="episodes/example/transcript.md",
        archive_sha256="a" * 64, text=text, start_char=0, end_char=len(text), start_seconds=0,
        end_seconds=1, similarity=.5)


def answer(complete=False):
    return GroundedAnswer(coverage="complete" if complete else "partial", insufficient_evidence=not complete,
        summary="Supported claim", summary_citation_ids=["S1"],
        sections=[AnswerSection(heading="Supported", content="Supported claim", citation_ids=["S1"])],
        missing_topics=[] if complete else ["Designers at Airbnb"])


@pytest.mark.parametrize("failure", [False, True])
def test_refinement_keeps_original_evidence_and_is_bounded(failure):
    async def check():
        service = RAGService(None, None)
        first, second = passage("Initial evidence"), passage("Designers evidence")
        service.retrieve = AsyncMock(side_effect=[SimpleNamespace(passages=[first]),
            ProviderError("Unavailable") if failure else SimpleNamespace(passages=[second, first])])
        service.generator = SimpleNamespace(model="gpt-6-luna", answer=AsyncMock(side_effect=[answer(), answer(True)]))
        result = await service.ask("Multipart question")
        assert result.answer.coverage == ("partial" if failure else "complete")
        assert result.sources["S1"].chunk_id == first.chunk_id
        assert service.retrieve.await_count == 2
        assert service.retrieve.call_args.kwargs["hybrid"] is True
        assert service.generator.answer.await_count == (1 if failure else 2)
        if not failure:
            expanded = service.generator.answer.call_args.args[1]
            assert expanded["S1"].chunk_id == first.chunk_id
            assert expanded["S2"].chunk_id == second.chunk_id
    asyncio.run(check())


def test_rank_fusion_promotes_shared_results_without_duplicate_passages():
    a, b, c = [(SimpleNamespace(id=value),) for value in ("a", "b", "c")]
    assert fuse_rankings([a, b], [b, c], 3) == [b, a, c]
    assert fuse_rankings([a, b], [], 1) == [a]


def test_duplicate_archive_members_consume_one_retrieval_slot():
    first = (SimpleNamespace(id="one", content="Identical passage"),)
    duplicate = (SimpleNamespace(id="two", content="Identical passage"),)
    other = (SimpleNamespace(id="three", content="Different evidence"),)
    assert unique_passages([first, duplicate, other]) == [first, other]


def test_complete_answer_does_not_search_again():
    async def check():
        service = RAGService(None, None)
        service.retrieve = AsyncMock(return_value=SimpleNamespace(passages=[passage("Evidence")]))
        service.generator = SimpleNamespace(model="gpt-6-luna", answer=AsyncMock(return_value=answer(True)))
        await service.ask("Question")
        assert service.retrieve.await_count == 1
        assert service.generator.answer.await_count == 1
    asyncio.run(check())
