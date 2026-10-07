"""Reorder existing evidence with OpenRouter without replacing source text."""

import asyncio
import logging
import time

from app.llm.client import OpenRouterClient, ProviderError
from app.schemas.retrieval import RetrievedPassage

logger = logging.getLogger(__name__)
MODEL = "voyageai/rerank-2.5-lite"


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
        "documents": [p.text for p in passages],
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
            return [passages[i] for i in order]
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
    return passages
