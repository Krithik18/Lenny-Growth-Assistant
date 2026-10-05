"""Validated answer contract; sources are resolved by the server."""

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from app.schemas.retrieval import RetrievedPassage


class AnswerSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: str
    content: str
    citation_ids: list[str]


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coverage: Literal["complete", "partial", "unsupported"]
    insufficient_evidence: bool
    summary: str
    summary_citation_ids: list[str]
    sections: list[AnswerSection]
    missing_topics: list[str]


class AnswerResult(BaseModel):
    question: str
    model: str
    answer: GroundedAnswer
    sources: dict[str, RetrievedPassage]


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=12000)
