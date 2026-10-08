import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const report = JSON.parse(await readFile('../backend/evals/results/workspace_openai_varied_questions_2026-10-08.json', 'utf8'));
const browser = await chromium.launch({channel: 'chrome', headless: true});
const results = [];
try {
  for (const record of report.results.filter(r => ['tip_calculator', 'todo_app'].includes(r.id))) {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(record => {
      if (window !== window.top) return;
      localStorage.setItem('lenny-workspace-v1', JSON.stringify([{
        id: 'varied', title: record.request.message, messages: [
          {role: 'user', content: record.request.message},
          {role: 'assistant', content: record.response.message, ...record.response}
        ]
      }]));
    }, record);
    try {
      await page.goto('http://127.0.0.1:5173');
      await page.locator('.history-row>button').first().click();
      await page.locator('.artifact-card').click();
      const frame = page.frameLocator('#preview');
      await frame.locator('body').waitFor();
      if (record.id === 'tip_calculator') {
        await frame.locator('#bill').fill('100');
        await frame.locator('#tip').fill('20');
        await frame.locator('#people').fill('4');
        assert.equal(await frame.locator('#perPerson').textContent(), '$30.00');
        assert.equal(await frame.locator('#total').textContent(), '$120.00');
        await frame.locator('#people').fill('0');
        assert.match(await frame.locator('#hint').textContent(), /at least 1/);
        await frame.getByRole('button', {name: 'Reset'}).click();
        assert.equal(await frame.locator('#bill').inputValue(), '');
      } else {
        for (const task of ['First task', 'Second task']) {
          await frame.getByRole('textbox', {name: 'New task'}).fill(task);
          await frame.getByRole('button', {name: 'Add task', exact: true}).click();
        }
        assert.equal(await frame.locator('.task').count(), 2);
        await frame.getByRole('checkbox').first().check();
        await frame.getByRole('button', {name: 'Completed', exact: true}).click();
        assert.equal(await frame.locator('.task').count(), 1);
        assert.equal(await frame.locator('.task-text').textContent(), 'First task');
        await frame.getByRole('button', {name: 'Delete “First task”', exact: true}).click();
        assert.equal(await frame.locator('.task').count(), 0);
        await frame.getByRole('button', {name: 'Active', exact: true}).click();
        assert.equal(await frame.locator('.task-text').textContent(), 'Second task');
      }
      assert.deepEqual(errors, []);
      results.push({id: record.id, passed: true});
    } catch (error) {
      results.push({id: record.id, passed: false, error: error.message, errors});
    } finally { await page.close(); }
  }
} finally { await browser.close(); }
await writeFile('../backend/evals/results/workspace_openai_varied_artifact_browser_2026-10-08.json', JSON.stringify(results, null, 2));
console.log(JSON.stringify(results, null, 2));
assert.equal(results.length, 2);
assert.ok(results.every(result => result.passed));
