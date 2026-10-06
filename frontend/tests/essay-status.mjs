import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
  const page=await browser.newPage();
  await page.addInitScript(()=>localStorage.setItem('lenny-workspace-v1',JSON.stringify([{id:'saved-essay',title:'Activation question',messages:[{role:'user',content:'Write an essay about activation.'},{role:'assistant',content:'Complete Markdown essay synthesizing the supplied evidence, with limitations and practical applications clearly distinguished. This draft is 1405 words; review its evidence limits before expanding it.',artifact:{title:'Activation',language:'markdown',content:'# Activation\n\nThe original essay remains intact.'},sources:{}}]}])));
  await page.goto('http://127.0.0.1:8000');
  await page.locator('.history-row>button').first().click();
  await page.getByText('Your essay is ready.',{exact:true}).waitFor();
  const stored=await page.evaluate(()=>JSON.parse(localStorage.getItem('lenny-workspace-v1'))[0].messages[1]);
  assert.equal(stored.content,'Your essay is ready.');
  assert.equal(stored.artifact.content,'# Activation\n\nThe original essay remains intact.');
  console.log('PASS: saved essay status repaired; original essay preserved.');
} finally {await browser.close();}
