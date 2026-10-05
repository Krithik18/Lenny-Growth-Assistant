"""Select whole passages within a transcript-token budget, in retrieval order."""

import tiktoken
from app.schemas.retrieval import RetrievedPassage


def build_context(passages: list[RetrievedPassage], token_budget: int = 2000) -> dict[str, RetrievedPassage]:
    encoding = tiktoken.get_encoding("cl100k_base")
    sources = {}
    seen = set()
    used = 0
    for passage in passages:
        if passage.chunk_id in seen:
            continue
        count = len(encoding.encode(passage.text, disallowed_special=()))
        if used + count > token_budget:
            continue
        sources[f"S{len(sources) + 1}"] = passage
        used += count
        seen.add(passage.chunk_id)
    return sources
