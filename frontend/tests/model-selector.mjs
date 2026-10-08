import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';

await mkdir('../.impeccable/review',{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:900}});
const requests=[],failures=[];
page.on('pageerror',e=>failures.push(e.message));
let status=200,release;
await page.route('**/api/v1/workspace/chat',async route=>{
  requests.push(route.request().postDataJSON());
  if(release)await new Promise(resolve=>{release.resolve=resolve;});
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(
    status===200?{message:`Response ${requests.length}`,sources:{},artifact:null}:{detail:'Test: unavailable.'})});
});

try{
  await page.goto('http://127.0.0.1:5173');
  const selector=page.getByRole('combobox',{name:'Model'});
  await selector.waitFor();
  assert.equal(await selector.inputValue(),'openai');
  assert.deepEqual(await selector.locator('option').allTextContents(),['OpenAI','Llama 3.1 8B']);
  await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:'../.impeccable/review/automatic-skills-desktop.png',fullPage:true});
  await page.getByLabel('Message Lenny').fill('Default model question');
  await page.getByRole('button',{name:'Send message'}).click();
  await page.getByText('Response 1',{exact:true}).waitFor();
  assert.equal(requests[0].provider,'openai');
  assert.equal('mode' in requests[0],false);

  await selector.selectOption({label:'Llama 3.1 8B'});
  for(const question of ['How can I improve activation?','Turn this into an essay.','Build an HTML calculator.']){
    assert.equal(await selector.inputValue(),'openrouter');
    await page.getByLabel('Message Lenny').fill(question);
    await page.getByRole('button',{name:'Send message'}).click();
    await page.getByText(`Response ${requests.length}`,{exact:true}).waitFor();
    // The selector is enabled again only after the response has rendered.
    await page.waitForFunction(()=>!document.querySelector('#model').disabled);
    assert.equal(requests.at(-1).provider,'openrouter');
    assert.equal('mode' in requests.at(-1),false);
    assert.ok(requests.at(-1).history.length>0);
  }

  release={};
  await page.getByLabel('Message Lenny').fill('A pending request');
  await page.getByRole('button',{name:'Send message'}).click();
  await page.waitForFunction(()=>document.querySelector('#model').disabled);
  assert.equal(await selector.isDisabled(),true);
  assert.equal(await page.getByRole('button',{name:'Stop waiting'}).count(),1);
  while(!release.resolve)await page.waitForTimeout(10);
  release.resolve();release=null;
  await page.getByText('Response 5',{exact:true}).waitFor();

  status=503;
  await page.getByLabel('Message Lenny').fill('Retry question');
  await page.getByRole('button',{name:'Send message'}).click();
  await page.getByRole('alert').waitFor();
  assert.equal(requests.at(-1).provider,'openrouter');
  await selector.selectOption('openai');
  status=200;
  await page.getByRole('button',{name:'Retry',exact:true}).click();
  await page.getByText('Response 7',{exact:true}).waitFor();
  assert.equal(requests.at(-1).provider,'openai');
  assert.equal(requests.at(-1).message,'Retry question');
  assert.equal(await page.locator('.message.user').count(),6);

  await page.getByRole('button',{name:/New conversation/}).click();
  await selector.selectOption('openrouter');
  await page.setViewportSize({width:375,height:812});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  const box=await selector.boundingBox();
  assert.ok(box.x>=0&&box.x+box.width<=375);
  await selector.focus();
  assert.equal(await selector.evaluate(el=>getComputedStyle(el).outlineStyle),'solid');
  await page.screenshot({path:'../.impeccable/review/automatic-skills-mobile.png',fullPage:true});
  await page.reload();
  assert.equal(await selector.inputValue(),'openai');
  assert.deepEqual(failures,[]);
  console.log('PASS: OpenAI default, both model options, provider payloads without manual modes, history, busy state, retry, keyboard focus, mobile layout, default after reload. No model calls.');
}finally{await browser.close();}
