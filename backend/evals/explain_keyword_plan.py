"""Print an analyzed PostgreSQL plan for the application's actual keyword query."""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import dialect

from app.core.config import get_settings
from app.db.session import Database
from app.ingestion.chunker import TranscriptChunker
from app.llm.client import OpenAIClient
from app.rag import retrieval
from app.rag.openai_embeddings import OpenAIEmbeddings


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=(
        "What example of a decision-making practice does Dharmesh Shah describe "
        "at HubSpot in the Zigging vs. zagging episode?"))
    args = parser.parse_args()

    settings = get_settings()
    database = Database(settings)
    client = OpenAIClient(settings.openai_api_key.get_secret_value())
    plan = None

    async def explain_keyword(database_arg, semantic, lexical, indexed, concurrent):
        nonlocal plan
        if lexical is None:
            raise ValueError("The selected question produced no keyword query")
        compiled = lexical.compile(dialect=dialect(paramstyle="named"))
        typed_binds = [bindparam(name, type_=value.type)
                       for name, value in compiled.binds.items() if name in compiled.params]
        statement = text(
            "EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON)\n" + compiled.string
        ).bindparams(*typed_binds)
        async with database_arg.sessions() as session:
            raw_plan = (await session.execute(statement, compiled.params)).scalar_one()
        plan = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
        return [], []

    original = retrieval.search_rows
    retrieval.search_rows = explain_keyword
    try:
        await retrieval.retrieve(
            database, OpenAIEmbeddings(client), args.question,
            TranscriptChunker().version, top_k=20, hybrid=True,
            candidate_pool=True, concurrent_search=True,
        )
    finally:
        retrieval.search_rows = original
        await client.close()
        await database.close()

    if plan is None:
        raise RuntimeError("No keyword plan was captured")

    root = plan[0]
    print(f"Question: {args.question}")
    print(f"Planning time: {root.get('Planning Time', 0):.3f} ms")
    print(f"Execution time: {root.get('Execution Time', 0):.3f} ms")
    print("Plan nodes:")

    def show(node, depth=0):
        indent = "  " * depth
        label = node.get("Node Type", "Unknown")
        if node.get("Relation Name"):
            label += f" on {node['Relation Name']}"
        if node.get("Index Name"):
            label += f" using {node['Index Name']}"
        details = [f"actual rows={node.get('Actual Rows', '?')}",
                   f"loops={node.get('Actual Loops', '?')}",
                   f"time={node.get('Actual Total Time', 0):.3f} ms"]
        if node.get("Shared Hit Blocks") is not None:
            details.append(f"buffer hits/reads={node['Shared Hit Blocks']}/{node.get('Shared Read Blocks', 0)}")
        if node.get("Rows Removed by Filter"):
            details.append(f"rows filtered={node['Rows Removed by Filter']}")
        print(f"{indent}{label}: " + ", ".join(details))
        for child in node.get("Plans", []):
            show(child, depth + 1)

    show(root["Plan"])


if __name__ == "__main__":
    asyncio.run(main())
