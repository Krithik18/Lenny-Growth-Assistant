import asyncio, json, re
from pathlib import Path
import httpx

async def check(mode, message):
    async with httpx.AsyncClient(timeout=600) as client:
        response=await client.post('http://127.0.0.1:8000/api/v1/workspace/chat',json={'mode':mode,'message':message})
        data=response.json()
        Path('../.impeccable/review/live-'+mode+'.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        artifact=data.get('artifact') or {}
        content=artifact.get('content','')
        print(json.dumps({'mode':mode,'status':response.status_code,'title':artifact.get('title'),'language':artifact.get('language'),'words':len(content.split()),'sources':len(data.get('sources',{})),'headings':len(re.findall(r'^#{1,3} ',content,re.M)),'bullets':len(re.findall(r'^[-*] ',content,re.M)),'detail':data.get('detail')},ensure_ascii=True),flush=True)

async def main():
    await asyncio.gather(
        check('essay','Write an approximately 1,250-word essay for early-stage SaaS founders about improving user activation. Synthesize practical lessons from the podcast, use a strong hook, bold takeaways and bullet points, and end with one clear next step.'),
        check('code','Create a simple self-contained HTML growth calculator. Inputs: starting users, monthly growth percentage, and number of months. Show projected users. Use accessible labels, tasteful green styling, and no libraries or external network requests.')
    )
asyncio.run(main())
