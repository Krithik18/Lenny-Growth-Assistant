"""Verify real query plans and latency without exposing credentials or vectors."""
import asyncio
import json
import time
from pathlib import Path
from sqlalchemy import event, text
from app.core.config import get_settings
from app.db.session import Database
from app.llm.client import OpenAIClient
from app.rag.service import RAGService


async def main():
    settings = get_settings()
    database = Database(settings)
    client = OpenAIClient(settings.openai_api_key.get_secret_value())
    captured = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT") and " AS distance" in statement:
            captured.append((statement, parameters))
    event.listen(database.engine.sync_engine, "before_cursor_execute", capture)
    try:
        start = time.monotonic()
        found = await RAGService(database, client).retrieve(
            "How does Brian Chesky involve designers in Airbnb product management?", top_k=20)
        elapsed = time.monotonic() - start
        assert found.passages
        statement, parameters = captured[0]
        async with database.engine.connect() as connection:
            await connection.execute(text("SET LOCAL hnsw.ef_search = 200"))
            version = await connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
            plan = (await connection.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters)).scalar()
        if isinstance(plan, str):
            plan = json.loads(plan)
        result = {"vector_version":version, "retrieval_seconds":round(elapsed,3), "plan":plan}
        path = Path(__file__).parent / "results" / "search_plan.json"
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"vector_version":version, "retrieval_seconds":result["retrieval_seconds"],
                          "database_execution_ms":plan[0]["Execution Time"],
                          "uses_hnsw": "ix_embeddings_openai_hnsw" in json.dumps(plan)}), flush=True)
        assert "ix_embeddings_openai_hnsw" in json.dumps(plan), "Query planner did not use the vector index"
    finally:
        await client.close()
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())
