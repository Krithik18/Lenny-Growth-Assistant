"""Read-only timing of search SQL and provider calls, without logging parameters."""
import asyncio
import json
from pathlib import Path
import time
from sqlalchemy import event
from app.core.config import get_settings
from app.db.session import Database
from app.llm.client import OpenAIClient
from app.rag.service import RAGService


async def main():
    settings = get_settings()
    db = Database(settings)
    client = OpenAIClient(settings.openai_api_key.get_secret_value())
    original_post = client.post
    captured = []

    async def timed_post(path, payload):
        start = time.monotonic()
        result = await original_post(path, payload)
        print(path, round(time.monotonic() - start, 2), flush=True)
        return result

    client.post = timed_post

    @event.listens_for(db.engine.sync_engine, "before_cursor_execute")
    def before(conn, cursor, statement, parameters, context, executemany):
        context.start_time = time.monotonic()
        if "ts_rank_cd" in statement and not statement.startswith("EXPLAIN"):
            captured.append((statement, parameters))

    @event.listens_for(db.engine.sync_engine, "after_cursor_execute")
    def after(conn, cursor, statement, parameters, context, executemany):
        kind = "lexical" if "ts_rank_cd" in statement else "semantic" if "<=>" in statement else "setup"
        print(kind, round(time.monotonic() - context.start_time, 2), flush=True)

    try:
        cases = json.loads((Path(__file__).parent / "results/full_cases.json").read_text(encoding="utf-8"))["cases"]
        case = next(c for c in cases if c["id"] == "ebi-atawodi")
        await RAGService(db, client).retrieve(case["question"], top_k=20)
        if captured:
            statement, parameters = captured[0]
            async with db.engine.connect() as connection:
                plan = (await connection.exec_driver_sql("EXPLAIN (FORMAT JSON) " + statement, parameters)).scalar()
            path = Path(__file__).parent / "results/lexical_plan.json"
            path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    finally:
        await client.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
