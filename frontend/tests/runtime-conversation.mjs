// Real browser-to-backend request after two real generated artifacts.
import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const report=JSON.parse(await readFile('../backend/evals/results/workspace_runtime_before_2026-10-08.json','utf8'));
const records=['calculator','growth_essay'].map(id=>report.results.find(r=>r.id===id));
const messages=records.flatMap(r=>[{role:'user',content:r.request.message},
  {role:'assistant',content:r.response.message,skill:r.response.skill,artifact:r.response.artifact,sources:r.response.sources}]);
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  await page.addInitScript(messages=>{if(window!==window.top)return;localStorage.setItem('lenny-workspace-v1',JSON.stringify([
    {id:'runtime-conversation',title:'Calculator and product growth essay',messages}
  ]));},messages);
  await page.goto('http://127.0.0.1:8000');
  await page.locator('.history-row>button').first().click();
  assert.equal(await page.getByLabel('Model').inputValue(),'openai');
  await page.getByLabel('Message Lenny').fill('What should I measure to know whether product growth is healthy?');
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/v1/workspace/chat'),{timeout:240000});
  await page.getByRole('button',{name:'Send message'}).click();
  const response=await pending;
  const request=response.request().postDataJSON();
  const data=await response.json();
  const result={status:response.status(),skill:data.skill,history:request.history.map(t=>({role:t.role,
    content_chars:t.content.length,artifact_chars:t.artifact?.content.length||0})),response:data};
  await writeFile('../backend/evals/results/workspace_browser_conversation_2026-10-08.json',JSON.stringify(result,null,2));
  assert.equal(response.status(),200);
  assert.equal(data.skill,'podcast-qa');
  assert.ok(Object.keys(data.sources).length>0);
  assert.equal(request.history.length,4);
  assert.equal(request.history[1].artifact.content,records[0].response.artifact.content);
  assert.equal(request.history[3].artifact.content,records[1].response.artifact.content);
  await page.locator('.message.assistant').last().locator('.sources').waitFor();
  assert.equal(await page.getByRole('alert').count(),0);
  await page.screenshot({path:'../.impeccable/review/runtime-real-conversation.png',fullPage:true});
  console.log(JSON.stringify({passed:true,status:response.status(),skill:data.skill,sources:Object.keys(data.sources).length,
    history_artifact_chars:request.history.reduce((n,t)=>n+(t.artifact?.content.length||0),0)}));
}finally{await browser.close();}
