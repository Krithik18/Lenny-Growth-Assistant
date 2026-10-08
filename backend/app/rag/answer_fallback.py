"""Source-preserving responses when a verified synthesis is unavailable."""

import re

from app.llm.openrouter_provider import source_excerpts, ratio_calculations
from app.schemas.answer import AnswerSection, GroundedAnswer


def fallback_answer(question, sources):
    if not sources:
        return GroundedAnswer(
            coverage="unsupported", insufficient_evidence=True,
            summary="I couldn't access enough podcast evidence to answer this question right now. Please try again shortly or narrow the question to a guest or topic.",
            summary_citation_ids=[], sections=[], missing_topics=[question],
        )
    terms = set(re.findall(r"\w{4,}", question.casefold())) - {
        "what", "which", "does", "that", "with", "from", "have", "when", "about", "recommend",
    }
    excerpts = source_excerpts(sources)
    candidates = []
    for sid, items in excerpts.items():
        for item in items:
            text = item["text"].strip()
            if len(text) < 40:
                continue
            score = len(terms & set(re.findall(r"\w{4,}", text.casefold())))
            candidates.append((score, sid, text))
    candidates.sort(key=lambda item: item[0], reverse=True)
    sections, seen = [], set()
    for score, sid, text in candidates:
        if not score or text in seen:
            continue
        # Exact substring only: truncation never adds words or claims.
        if len(text) > 800:
            text = text[:800].rsplit(" ", 1)[0]
        if text in seen:
            continue
        seen.add(text)
        sections.append(AnswerSection(heading=f"Transcript excerpt {len(sections) + 1}",
                                      content=f'> {text.replace(chr(10), chr(10) + "> ")}',
                                      citation_ids=[sid]))
        if len(sections) == 3:
            break
    if not sections:
        return GroundedAnswer(
            coverage="unsupported", insufficient_evidence=True,
            summary="I found podcast passages, but couldn't verify an answer to this specific question. Try naming a guest or asking one part at a time.",
            summary_citation_ids=[], sections=[], missing_topics=[question],
        )
    calculations = ratio_calculations(question)
    arithmetic = " ".join(f"From your numbers, {item['counts']} is {item['percentage']}%." for item in calculations)
    return GroundedAnswer(
        coverage="partial", insufficient_evidence=True,
        summary=(arithmetic + " " if arithmetic else "") + "I couldn't verify a complete answer. Here are verbatim excerpts from the retrieved transcripts that may help; they are not a verified answer to every part of your question.",
        summary_citation_ids=list(dict.fromkeys(cid for s in sections for cid in s.citation_ids)),
        sections=sections, missing_topics=["A verified, complete answer to: " + question],
    )
