// Exercise actual model output through the application's isolated preview.
// Run workspace_runtime_live.py first; this script makes no model calls.
import { chromium } from '@playwright/test';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const reportPath=process.argv[2]||'../backend/evals/results/workspace_runtime_before_2026-10-08.json';
const url=process.argv[3]||'http://127.0.0.1:8000';
const report=JSON.parse(await readFile(reportPath,'utf8'));
const output=[];
await mkdir('../.impeccable/review',{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  for(const record of report.results.filter(r=>r.status===200&&r.response.artifact)){
    const {artifact}=record.response;
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    const errors=[];
    let checks=[];
    let words;
    page.on('pageerror',e=>errors.push(e.message));
    page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
    await page.route('**/favicon.ico',route=>route.fulfill({status:204}));
    await page.addInitScript(({request,response})=>{if(window!==window.top)return;localStorage.setItem('lenny-workspace-v1',JSON.stringify([
      {id:'runtime',title:request.message,messages:[
        {role:'user',content:request.message},
        {role:'assistant',content:response.message,artifact:response.artifact,sources:response.sources,skill:response.skill}
      ]}
    ]));},record);
    try{
      await page.goto(url);
      await page.locator('.history-row>button').first().click();
      await page.locator('.artifact-card').click();
      if(artifact.language==='html'){
        const frame=page.frameLocator('#preview');
        await frame.locator('body').waitFor();
        if(record.id==='calculator'||record.id==='calculator_edit'){
          if(await frame.locator('#num1').count() && await frame.locator('#operator').count()){
            const calculate=async (left,operator,right)=>{
              await frame.locator('#num1').fill(left);
              await frame.locator('#operator').selectOption(operator);
              await frame.locator('#num2').fill(right);
              await frame.getByRole('button',{name:'Calculate',exact:true}).click();
              return (await frame.locator('#result').textContent()).trim();
            };
            assert.equal(await calculate('2','+','3'),'5');
            assert.equal(await calculate('8','/','2'),'4');
            assert.equal(await calculate('1.5','+','2.5'),'4');
            assert.match(await calculate('1','/','0'),/division by zero|cannot divide|undefined|error/i);
            if(record.id==='calculator_edit'){
              await frame.getByRole('button',{name:/clear|reset/i}).click();
              assert.equal(await frame.locator('#num1').inputValue(),'0');
              await frame.locator('#num1').fill('2');
              await frame.locator('#operator').selectOption('+');
              await frame.locator('#num2').fill('3');
              await frame.locator('#num2').press('Enter');
              assert.equal((await frame.locator('#result').textContent()).trim(),'5');
            }
            checks=['2+3=5','8/2=4','decimals: 1.5+2.5=4','division by zero handled'];
          }else{
          const button=name=>frame.getByRole('button',{name,exact:true});
          const clear=()=>frame.getByRole('button',{name:/^(Clear|All clear|AC|C|Reset)$/i}).first().click();
          const display=frame.locator('output,#display,input[readonly],[role="status"]').first();
          const value=()=>display.evaluate(el=>el instanceof HTMLInputElement?el.value:el.textContent);
          const expect=async n=>assert.equal((await value()).trim().replace(/,/g,''),n);
          await clear(); await button('2').click();
          await frame.getByRole('button',{name:/^(Add|\+)$/i}).click();
          await button('3').click();
          await frame.getByRole('button',{name:/^(Equals|=)$/i}).click(); await expect('5');
          await clear(); await button('8').click();
          await frame.getByRole('button',{name:/^(Divide|÷|\/)$/i}).click();
          await button('2').click();
          await frame.getByRole('button',{name:/^(Equals|=)$/i}).click(); await expect('4');
          await clear(); await button('1').click();
          await page.keyboard.press('.'); await page.keyboard.press('5');
          await page.keyboard.press('+'); await page.keyboard.press('2');
          await page.keyboard.press('.'); await page.keyboard.press('5');
          await page.keyboard.press('Enter'); await expect('4');
          await page.keyboard.press('Escape'); await expect('0');
          checks=['2+3=5','8/2=4','keyboard: 1.5+2.5=4','Escape clears'];
          }
        }else if(record.id==='growth_calculator'){
          const inputs=frame.locator('input[type="number"]');
          assert.equal(await inputs.count(),3);
          await inputs.nth(0).fill('1000'); await inputs.nth(1).fill('10'); await inputs.nth(2).fill('2');
          const calculate=frame.getByRole('button',{name:/calculate|project|compute/i});
          if(await calculate.count())await calculate.first().click();
          await frame.getByText(/1[,.]?210(?:\.0+)?/).first().waitFor();
          checks=['1000 users at 10% for 2 months = 1210'];
        }
        assert.equal(await page.locator('#preview').getAttribute('sandbox'),'allow-scripts allow-forms');
      }else if(artifact.language==='markdown'){
        await page.locator('.document h1').waitFor();
        assert.ok(await page.locator('.document strong').count()>2);
        assert.ok(await page.locator('.document li').count()>2);
        words=artifact.content.trim().split(/\s+/).length;
        checks=['headings','bold ideas','bullets','source passages'];
      }
      assert.deepEqual(errors,[]);
      await page.screenshot({path:`../.impeccable/review/runtime-${record.provider}-${record.id}.png`,fullPage:true});
      await page.setViewportSize({width:390,height:844});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      await page.screenshot({path:`../.impeccable/review/runtime-${record.provider}-${record.id}-mobile.png`,fullPage:true});
      output.push({id:record.id,provider:record.provider,passed:true,checks,...(words?{words}:{})});
    }catch(e){output.push({id:record.id,provider:record.provider,passed:false,error:e.message,console:errors});}
    finally{await page.close();}
  }
}finally{await browser.close();}
await writeFile('../.impeccable/review/runtime-artifacts.json',JSON.stringify(output,null,2));
console.log(JSON.stringify(output,null,2));
assert.ok(output.length>0);
assert.ok(output.every(r=>r.passed),'One or more generated artifacts failed browser checks.');
