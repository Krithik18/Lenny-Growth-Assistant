// Run after backend/evals/check_workspace_live.py. Reuses results; no model calls.
import { chromium } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const read=async mode=>JSON.parse(await readFile(`../.impeccable/review/live-${mode}.json`,'utf8'));
const code=await read('code'),essay=await read('essay');
assert.equal(code.artifact?.language,'html');assert.equal(essay.artifact?.language,'markdown');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  await page.addInitScript(({code,essay})=>localStorage.setItem('lenny-workspace-v1',JSON.stringify([
    {id:'live-check',title:'Activation: an essay and a simple tool',messages:[
      {role:'user',content:'Write an essay about user activation.'},
      {role:'assistant',content:essay.message,artifact:essay.artifact,sources:essay.sources},
      {role:'user',content:'Build a simple growth calculator.'},
      {role:'assistant',content:code.message,artifact:code.artifact,sources:{}}
    ]}
  ])),{code,essay});
  await page.goto('http://127.0.0.1:8000');
  await page.locator('.history-row>button').first().click();
  await page.locator('.artifact-card').last().click();
  const frame=page.frameLocator('#preview');
  await frame.getByLabel('Starting users').fill('1000');
  await frame.getByLabel('Monthly growth (%)').fill('10');
  await frame.getByLabel('Number of months').fill('2');
  await frame.locator('#projection').filter({hasText:'1,210'}).waitFor();
  await page.screenshot({path:'../.impeccable/review/live-code-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Close artifact'}).click();
  await page.locator('.artifact-card').first().click();
  await page.locator('.document h1').waitFor();
  assert.ok(await page.locator('.document strong').count()>2);
  assert.ok(await page.locator('.document li').count()>2);
  assert.equal(await page.locator('.artifact-body').evaluate(el=>el.scrollHeight>el.clientHeight),true);
  await page.screenshot({path:'../.impeccable/review/live-essay-desktop.png',fullPage:true});
  console.log(JSON.stringify({status:'PASS',essayWords:essay.artifact.content.trim().split(/\s+/).length,sources:Object.keys(essay.sources).length,calculator:'1000 users at 10% for 2 months = 1,210',essay:'Rendered headings, bold text, bullets, source passages and independent scrolling'}));
}finally{await browser.close();}
