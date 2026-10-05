"""OpenAI embeddings, independently configured from the answer model."""

from app.llm.client import OpenAIClient, ProviderError
from app.rag.embeddings import EmbeddingSpec, validate_vectors


class OpenAIEmbeddings:
    spec = EmbeddingSpec("openai", "text-embedding-3-small", 1536)

    def __init__(self, client: OpenAIClient):
        self.client = client

    async def embed_documents(self, texts):
        if not texts:
            return []
        payload = await self.client.post("embeddings", {
            "model": self.spec.model, "input": list(texts),
            "dimensions": self.spec.dimensions, "encoding_format": "float",
        })
        try:
            items = sorted(payload["data"], key=lambda item: item["index"])
            if [item["index"] for item in items] != list(range(len(texts))):
                raise ValueError("Invalid indexes")
            vectors = [item["embedding"] for item in items]
            validate_vectors(vectors, len(texts), self.spec)
            return vectors
        except (KeyError, TypeError, ValueError):
            raise ProviderError("OpenAI returned invalid embeddings.") from None

    async def embed_query(self, question):
        return (await self.embed_documents([question]))[0]
