import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from app.core.config import Settings
from app.ingestion.source import ARCHIVE_SHA256
from app.llm.client import OpenRouterClient, ProviderError
from app.rag.indexing import embed_pending_chunks
from app.rag.openai_embeddings import OpenAIEmbeddings
from app.rag.openrouter_embeddings import OpenRouterEmbeddings
from evals import index_full_archive


class BatchDatabase:
    def __init__(self, batches):
        self.batches = iter(batches)
        self.reads = []
        self.writes = []
        self.active_sessions = 0
        self.sessions = self

    @asynccontextmanager
    async def __call__(self):
        self.active_sessions += 1
        try:
            yield SimpleNamespace(execute=self.read)
        finally:
            self.active_sessions -= 1

    async def read(self, statement):
        self.reads.append(statement.compile(dialect=postgresql.dialect()))
        batch = next(self.batches)
        return SimpleNamespace(all=lambda: batch)

    @asynccontextmanager
    async def begin(self):
        self.active_sessions += 1
        try:
            yield SimpleNamespace(execute=self.write)
        finally:
            self.active_sessions -= 1

    async def write(self, statement):
        self.writes.append(statement.compile(dialect=postgresql.dialect()))


def test_openrouter_indexes_existing_chunks_in_separate_space():
    chunks = [SimpleNamespace(id=uuid4(), content="First chunk"),
              SimpleNamespace(id=uuid4(), content="Second chunk")]
    database = BatchDatabase([chunks, []])
    progress = []
    vectors = [[1.0] * 1024, [2.0] * 1024]

    def handler(request):
        assert database.active_sessions == 0
        assert json.loads(request.content)["input"] == [row.content for row in chunks]
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": vectors[1]}, {"index": 0, "embedding": vectors[0]},
        ]})

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(handler))
        try:
            assert await embed_pending_chunks(database, OpenRouterEmbeddings(client), "chunks-v1",
                                             batch_size=2, progress=progress.append) == 2
        finally:
            await client.close()

    asyncio.run(check())
    assert progress == [2]
    assert len(database.writes) == 1
    params = database.writes[0].params
    for index, chunk in enumerate(chunks):
        assert params[f"chunk_id_m{index}"] == chunk.id
        assert params[f"provider_m{index}"] == "openrouter"
        assert params[f"model_m{index}"] == "baai/bge-m3"
        assert params[f"dimensions_m{index}"] == 1024
        assert params[f"input_version_m{index}"] == "raw-chunk-v1"
        assert params[f"embedding_m{index}"] == vectors[index]
    assert "ON CONFLICT ON CONSTRAINT uq_chunk_embeddings_config DO NOTHING" in str(database.writes[0])
    for statement in database.reads:
        assert "NOT (EXISTS" in str(statement)
        assert "openrouter" in statement.params.values()
        assert "baai/bge-m3" in statement.params.values()
        assert 1024 in statement.params.values()
        assert ARCHIVE_SHA256 in statement.params.values()
        assert "chunks-v1" in statement.params.values()


def test_no_pending_openrouter_chunks_skips_api_and_writes():
    database = BatchDatabase([[]])

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(
            lambda request: pytest.fail("Unexpected embedding request")))
        try:
            assert await embed_pending_chunks(database, OpenRouterEmbeddings(client), "chunks-v1") == 0
        finally:
            await client.close()

    asyncio.run(check())
    assert not database.writes


@pytest.mark.parametrize("status,vector", [(429, None), (200, [1.0] * 1536)])
def test_failed_openrouter_batch_is_not_stored(status, vector):
    database = BatchDatabase([[SimpleNamespace(id=uuid4(), content="Chunk")]])

    async def check():
        client = OpenRouterClient("fake", transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={"data": [{"index": 0, "embedding": vector}]})))
        try:
            with pytest.raises(ProviderError):
                await embed_pending_chunks(database, OpenRouterEmbeddings(client), "chunks-v1")
        finally:
            await client.close()

    asyncio.run(check())
    assert not database.writes


@pytest.mark.parametrize("provider,model,dimensions,filename,batch_size,worker_count", [
    ("openrouter", "baai/bge-m3", 1024, "full_index_openrouter.json", 64, 2),
    ("openrouter", "baai/bge-m3", 1024, "full_index_openrouter.json", 16, 1),
    ("openai", "text-embedding-3-small", 1536, "full_index.json", 64, 2),
])
def test_archive_runner_selects_provider_and_checks_its_coverage(monkeypatch, tmp_path, provider, model, dimensions, filename, batch_size, worker_count):
    settings = Settings(_env_file=None, openai_api_key="openai-key", openrouter_api_key="router-key")
    client = SimpleNamespace(close=AsyncMock())
    selected_keys = []
    monkeypatch.setattr(index_full_archive, "get_settings", lambda: settings)
    def make_client(key):
        selected_keys.append(key)
        return client
    monkeypatch.setattr(index_full_archive, "OpenRouterClient", make_client if provider == "openrouter" else lambda key: pytest.fail("Wrong client"))
    monkeypatch.setattr(index_full_archive, "OpenAIClient", make_client if provider == "openai" else lambda key: pytest.fail("Wrong client"))
    coverage_params = []
    coverage = [{"member": f"episode-{i}", "chunks": 1, "embeddings": 1, "embedding_tokens": 10} for i in range(303)]
    async def execute(statement, params):
        coverage_params.append(params)
        assert "v.provider=:provider" in str(statement)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: coverage))
    session = SimpleNamespace(scalar=AsyncMock(return_value=303), execute=execute)
    @asynccontextmanager
    async def sessions():
        yield session
    database = SimpleNamespace(sessions=sessions, close=AsyncMock())
    monkeypatch.setattr(index_full_archive, "Database", lambda settings: database)
    shards = []
    async def embed(database_arg, embeddings, version, **kwargs):
        assert database_arg is database
        assert embeddings.spec.provider == provider
        assert embeddings.spec.model == model
        assert embeddings.spec.dimensions == dimensions
        assert isinstance(embeddings.provider, OpenRouterEmbeddings if provider == "openrouter" else OpenAIEmbeddings)
        assert kwargs["batch_size"] == batch_size
        assert kwargs["shards"] == worker_count
        shards.append(kwargs["shard_index"])
        return 1
    monkeypatch.setattr(index_full_archive, "embed_pending_chunks", embed)
    monkeypatch.setattr(index_full_archive, "import_archive", AsyncMock(side_effect=AssertionError("Unexpected import")))
    monkeypatch.setattr(index_full_archive, "__file__", str(tmp_path / "index_full_archive.py"))
    (tmp_path / "results").mkdir()
    argv = ["index_full_archive", "--skip-import"]
    if provider == "openrouter":
        argv += ["--embedding-provider", "openrouter"]
    if batch_size != 64 or worker_count != 2:
        argv += ["--batch-size", str(batch_size), "--shards", str(worker_count)]
    monkeypatch.setattr("sys.argv", argv)
    asyncio.run(index_full_archive.main())
    assert selected_keys == ["router-key" if provider == "openrouter" else "openai-key"]
    assert sorted(shards) == list(range(worker_count))
    assert coverage_params[0]["provider"] == provider
    assert coverage_params[0]["model"] == model
    assert coverage_params[0]["dimensions"] == dimensions
    report = json.loads((tmp_path / "results" / filename).read_text())
    assert report["embeddings"] == 303
    assert report["new_embeddings_this_run"] == worker_count
    other_filename = "full_index.json" if provider == "openrouter" else "full_index_openrouter.json"
    assert not (tmp_path / "results" / other_filename).exists()
    client.close.assert_awaited_once()
    database.close.assert_awaited_once()


def test_openrouter_key_is_loaded_and_masked(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-router-key")
    settings = Settings(_env_file=None)
    assert settings.openrouter_api_key.get_secret_value() == "private-router-key"
    assert "private-router-key" not in repr(settings)


def test_retrying_openrouter_embeddings_preserves_spec_and_retries(monkeypatch, capsys):
    provider = SimpleNamespace(spec=OpenRouterEmbeddings.spec, embed_documents=AsyncMock(
        side_effect=[ProviderError("OpenRouter request failed (HTTP 429)."), [[1.0] * 1024]]))
    sleep = AsyncMock()
    monkeypatch.setattr(index_full_archive.asyncio, "sleep", sleep)
    wrapper = index_full_archive.RetryingEmbeddings(provider)
    assert wrapper.spec is provider.spec
    assert asyncio.run(wrapper.embed_documents(["chunk"])) == [[1.0] * 1024]
    assert provider.embed_documents.await_count == 2
    sleep.assert_awaited_once_with(4)
    output = capsys.readouterr().out
    assert "HTTP 429" in output
    assert "retry" in output.lower()
    assert "in 4s" in output


@pytest.mark.parametrize("arguments", [["--batch-size", "0"], ["--batch-size", "129"], ["--shards", "0"], ["--shards", "5"]])
def test_invalid_batch_settings_fail_before_initializing_clients(monkeypatch, arguments):
    monkeypatch.setattr("sys.argv", ["index_full_archive", *arguments])
    monkeypatch.setattr(index_full_archive, "get_settings", lambda: pytest.fail("Unexpected initialization"))
    with pytest.raises(SystemExit) as error:
        asyncio.run(index_full_archive.main())
    assert error.value.code == 2


@pytest.mark.parametrize("message,attempts", [
    ("OpenRouter request failed (HTTP 429).", 5),
    ("OpenRouter request failed (HTTP 401).", 1),
    ("OpenRouter returned invalid embeddings.", 1),
])
def test_retry_limits_and_permanent_failures(monkeypatch, message, attempts):
    provider = SimpleNamespace(spec=OpenRouterEmbeddings.spec,
                               embed_documents=AsyncMock(side_effect=ProviderError(message)))
    sleep = AsyncMock()
    monkeypatch.setattr(index_full_archive.asyncio, "sleep", sleep)
    with pytest.raises(ProviderError, match=message.replace("(", r"\(").replace(")", r"\)")):
        asyncio.run(index_full_archive.RetryingEmbeddings(provider).embed_documents(["chunk"]))
    assert provider.embed_documents.await_count == attempts
    assert sleep.await_count == attempts - 1
