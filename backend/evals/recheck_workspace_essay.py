"""Recheck synthesis with saved live evidence, avoiding repeated retrieval costs."""
import asyncio, json
from pathlib import Path
from types import SimpleNamespace
from app.api.routes.workspace import create_essay
from app.core.config import get_settings
from app.llm.client import OpenAIClient
from app.llm.openai_provider import OpenAIAnswerProvider

async def main():
    path=Path('../.impeccable/review/live-essay.json')
    data=json.loads(path.read_text(encoding='utf-8'))
    client=OpenAIClient(get_settings().openai_api_key.get_secret_value())
    try:
        service=SimpleNamespace(client=client,generator=OpenAIAnswerProvider(client))
        output=await create_essay(service,'Write an approximately 1,250-word essay for early-stage SaaS founders about improving user activation, with a strong hook, bold text, useful bullet lists and a clear takeaway.',data['artifact']['content'],data['sources'])
        data.update(output.model_dump())
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':'completed','title':output.artifact.title,'words':len(output.artifact.content.split()),'sources':len(data['sources'])}),flush=True)
    finally:
        await client.close()

asyncio.run(main())
