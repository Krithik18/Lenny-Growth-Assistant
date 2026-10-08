import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';

const browser = await chromium.launch({channel:'chrome',headless:true});
const page = await browser.newPage();
const requests = [];
await page.route('**/api/v1/workspace/chat', async route => {
  requests.push(route.request().postDataJSON());
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
    message:'Earlier in this chat, you named your app Orbit Garden.',skill:'podcast-qa',
    provider:'openai',model:'gpt-6-luna',artifact:null,sources:{},coverage:null})});
});
await page.addInitScript(() => {
  if(localStorage.getItem('history-test-seeded'))return;
  localStorage.setItem('history-test-seeded','true');
  const messages = [{role:'user',content:'My app is Orbit Garden.'},{role:'assistant',content:'Orbit Garden helps teachers.'}];
  for(let i=0;i<14;i++)messages.push({role:'user',content:`Question ${i}`},{role:'assistant',content:`Answer ${i}`});
  localStorage.setItem('lenny-workspace-v1',JSON.stringify([
    {id:'orbit',title:'Orbit chat',messages},
    {id:'other',title:'Other chat',messages:[{role:'user',content:'This chat is about a private test label: OtherProject.'},
      {role:'assistant',content:'OtherProject is separate.'}]}
  ]));
});
try {
  await page.goto('http://127.0.0.1:5173');
  await page.getByRole('button',{name:'Orbit chat',exact:true}).click();
  await page.getByLabel('Message Lenny').fill('What name did I give my app?');
  await page.getByRole('button',{name:'Send message'}).click();
  await page.getByText('Earlier in this chat, you named your app Orbit Garden.',{exact:true}).waitFor();
  assert.equal(requests[0].history.length,30);
  assert.equal(requests[0].history[0].content,'My app is Orbit Garden.');
  assert.ok(!JSON.stringify(requests[0].history).includes('OtherProject'));
  await page.reload();
  await page.getByRole('button',{name:'Orbit chat',exact:true}).click();
  await page.getByText('Earlier in this chat, you named your app Orbit Garden.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Other chat',exact:true}).click();
  await page.getByLabel('Message Lenny').fill('What did I discuss here?');
  await page.getByRole('button',{name:'Send message'}).click();
  await page.getByText('Earlier in this chat, you named your app Orbit Garden.',{exact:true}).waitFor();
  assert.equal(requests[1].history.length,2);
  assert.ok(!JSON.stringify(requests[1].history).includes('Orbit Garden'));
  console.log('PASS: old questions and answers sent, per-chat isolation, saved replies survive reload.');
} finally {await browser.close();}
