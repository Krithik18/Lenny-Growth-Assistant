"""Reorder existing evidence with OpenRouter without replacing source text."""

import asyncio
import logging
import time
import math
import re

from app.llm.client import OpenRouterClient, ProviderError
from app.schemas.retrieval import RetrievedPassage
from app.rag.query_intent import balance_people, plan_query, normalize, guest_name

logger = logging.getLogger(__name__)
MODEL = "voyageai/rerank-2.5-lite"


def ranking_document(passage):
    return f"Episode: {passage.title}\nEpisode guest (not necessarily every speaker): {passage.guest}\nTranscript:\n{passage.text}"


def evidence_penalty(passage):
    """Soft penalty: keep mixed ad/evidence chunks rather than deleting useful text."""
    text = passage.text.casefold()
    sponsor = len(re.findall(r"(?:our sponsor|this episode is brought|sponsored by|get started for free|wix\.com|notion\.com|subscribe and follow)", text))
    introduction = bool(re.search(r"(?:today my guest|in our conversation|this episode is for you)", text))
    return min(.10, sponsor * .025 + introduction * .035)


def select_evidence(question, passages, scores):
    intent = plan_query(question, [p.guest for p in passages if p.guest])
    if not scores:
        if not any(evidence_penalty(p) for p in passages):
            return balance_people(passages, question)
        return balance_people(sorted(passages, key=evidence_penalty), question)
    best = max(scores.values())
    if best < .15:
        return []
    floor = max(.10, best * .35)
    # These are conservative ranking heuristics, not calibrated probabilities.
    # Direct-guest preference is soft; strong third-party and compilation evidence stays.
    useful = [p for p in passages if scores[p.chunk_id] >= floor]
    # A single-person query can have a small, clearly separated relevant cluster.
    # Keep at least three passages for context; leave broad/comparison queries alone.
    if len(intent.people) == 1 and best >= .6:
        by_score = sorted(useful, key=lambda p: scores[p.chunk_id], reverse=True)
        for index in range(3, min(8, len(by_score))):
            upper, lower = (scores[by_score[i].chunk_id] for i in (index - 1, index))
            if upper - lower >= .15 and lower <= best * .65:
                useful = by_score[:index]
                break
    def quality(p):
        direct = guest_name(p.guest) in intent.people
        return scores[p.chunk_id] - evidence_penalty(p) + (.035 if direct else 0)
    useful.sort(key=quality, reverse=True)
    return balance_people(useful, question)


class RankingError(ValueError):
    """A safe diagnostic code, never the provider's raw response."""


def parse_order(result, count):
    """The API returns results in relevance order; require every input once."""
    if not isinstance(result, dict) or not isinstance(result.get("results"), list):
        raise RankingError("malformed_response")
    items = result["results"]
    if any(not isinstance(item, dict) or type(item.get("index")) is not int for item in items):
        raise RankingError("malformed_ranking")
    order = [item["index"] for item in items]
    if len(order) != count:
        raise RankingError("wrong_length")
    if len(set(order)) != count:
        raise RankingError("duplicate_ids")
    if set(order) != set(range(count)):
        raise RankingError("unknown_ids")
    return order


async def rerank(
    client: OpenRouterClient,
    question: str,
    passages: list[RetrievedPassage],
    *,
    diagnostics=None,
) -> list[RetrievedPassage]:
    """Return original passage objects in relevance order, or input order on failure.

    Like the OpenAI reranker, allow two attempts with a 30-second timeout each.
    Never replace evidence or its retrieval metadata with provider-returned text.
    """
    if diagnostics is not None:
        diagnostics.update(attempts=[], fallback=False, candidate_count=len(passages))
    if len(passages) < 2:
        return passages
    payload = {
        "model": MODEL,
        "query": question,
        "documents": [ranking_document(p) for p in passages],
        "top_n": len(passages),
    }
    for attempt in range(2):
        started = time.monotonic()
        record = {"attempt": attempt + 1}
        try:
            async with asyncio.timeout(30):
                result = await client.post("rerank", payload)
            order = parse_order(result, len(passages))
            record.update(valid=True, order=order)
            ranked = [passages[i] for i in order]
            scores = {}
            for item in result["results"]:
                score = item.get("relevance_score")
                if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                    scores = {}
                    break
                scores[passages[item["index"]].chunk_id] = score
            # Responses without usable scores preserve their valid provider ordering.
            selected = select_evidence(question, ranked, scores) if scores else balance_people(ranked, question)
            if diagnostics is not None:
                diagnostics.update(scores={str(key): value for key, value in scores.items()},
                    selected_count=len(selected), low_relevance_rejected=len(ranked) - len(selected))
            return selected
        except (ProviderError, TimeoutError, RankingError) as error:
            reason = str(error) if isinstance(error, RankingError) else type(error).__name__
            record.update(valid=False, reason=reason)
            logger.warning("OpenRouter reranking attempt %s failed: %s", attempt + 1, reason)
        finally:
            record["seconds"] = time.monotonic() - started
            if diagnostics is not None:
                diagnostics["attempts"].append(record)
    if diagnostics is not None:
        diagnostics["fallback"] = True
    logger.warning("OpenRouter reranking unavailable; preserving candidate order")
    return select_evidence(question, passages, {})
