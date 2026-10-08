"""Diagnose actual OpenRouter scope responses for workspace essay requests."""
import asyncio
import json
from pathlib import Path

from app.main import app
from app.rag.openrouter_scope import classify_scope
from app.skills.context import retrieval_question


async def main():
    records = []
    async with app.router.lifespan_context(app):
        client = app.state.openrouter_rag.client
        original = client.post
        calls = []

        async def traced(path, payload):
            result = await original(path, payload)
            calls.append(result)
            return result

        client.post = traced
        history = [{'role': 'assistant', 'content': 'Your essay is ready.', 'skill': 'ship30-essay',
                    'artifact': {'title': 'Product Growth Starts With Retention', 'language': 'markdown',
                                 'content': '# Product Growth Starts With Retention\n\nPrioritize activation and retention.'}}]
        for question in [
            'Write an essay on product growth.',
            'Give me something about improving user activation in Ship30for30 style.',
            retrieval_question('Write a short essay on product growth in Ship30for30 style.', history),
            'What is Ship 30 for 30 style?',
        ]:
            calls.clear()
            try:
                decision = await classify_scope(client, question)
                record = {'question': question, 'decision': decision.model_dump(), 'calls': list(calls)}
            except Exception as error:
                record = {'question': question, 'error': str(error), 'calls': list(calls)}
            records.append(record)
            Path('evals/results/workspace_scope_live_2026-10-08.json').write_text(json.dumps(records, indent=2), encoding='utf8')
            print(json.dumps({key: value for key, value in record.items() if key != 'calls'}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
