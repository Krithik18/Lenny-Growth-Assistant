"""Read-only migration progress without printing connection details."""
import asyncio
import json
from sqlalchemy import text
from app.core.config import get_settings
from app.db.session import Database


async def main():
    database = Database(get_settings())
    try:
        async with database.sessions() as session:
            rows = (await session.execute(text("""SELECT relid::regclass::text AS table_name, phase, tuples_done, tuples_total,
              blocks_done, blocks_total FROM pg_stat_progress_create_index
              WHERE relid IN ('app_data.chunk_embeddings'::regclass, 'app_data.transcript_chunks'::regclass)"""))).mappings().all()
            print(json.dumps([dict(row) for row in rows]), flush=True)
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())
