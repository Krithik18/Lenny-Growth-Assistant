"""Provider contract only. OpenAI and Ollama adapters are separate future stages."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal, Protocol, Sequence


@dataclass(frozen=True)
class EmbeddingSpec:
    provider: Literal["openai", "ollama"]
    model: str
    dimensions: int
    input_version: str = "raw-chunk-v1"

    def __post_init__(self):
        if self.provider not in ("openai", "ollama") or not self.model or self.dimensions < 1 or not self.input_version:
            raise ValueError("Embedding provider, model, dimensions, and input version are required.")


class EmbeddingProvider(Protocol):
    spec: EmbeddingSpec

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector per document in input order."""
        ...

    async def embed_query(self, question: str) -> list[float]:
        """Use the compatible query preprocessing for this provider's input version."""
        ...


def validate_vectors(vectors: Sequence[Sequence[float]], expected_count: int, spec: EmbeddingSpec) -> None:
    if len(vectors) != expected_count:
        raise ValueError("Embedding result count does not match input count.")
    for vector in vectors:
        if len(vector) != spec.dimensions or not all(isfinite(value) for value in vector):
            raise ValueError("Embedding dimensions or values are invalid.")
        if not any(value != 0 for value in vector):
            raise ValueError("Zero vectors cannot be used for cosine retrieval.")
