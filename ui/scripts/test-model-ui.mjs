// Opt-in acceptance: real browser -> local gateway -> actual model API.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
if (process.env.RUN_LIVE_MODEL_TESTS !== '1') throw new Error('Set RUN_LIVE_MODEL_TESTS=1; this test consumes API quota.');
const browser = await chromium.launch({headless:true});
try {
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  await page.goto(process.env.MODEL_TEST_UI_URL || 'http://127.0.0.1:8767');
  await page.getByRole('button',{name:'模型记录',exact:true}).click();
  await page.getByLabel('测试问题',{exact:true}).fill('37 箱零件，每箱 29 个，取走 428 个，还剩多少？只回答数字。');
  await page.getByLabel('预期答案',{exact:false}).fill('645');
  const completed = page.waitForResponse(r=>r.url().endsWith('/model-test/run') && r.request().method()==='POST',{timeout:90000});
  await page.getByRole('button',{name:'发送测试',exact:true}).click();
  const response = await completed;
  assert.equal(response.status(),200);
  const result = await response.json();
  assert.equal(result.status,'completed',JSON.stringify(result));
  assert.equal(result.answer.trim(),'645');
  assert.equal(result.actual_model,'qwen3.8-max');
  assert.equal(result.verdict,'matched');
  await page.getByText('调用完成 · 预期答案匹配',{exact:true}).waitFor();
  const path='../.impeccable/review';await mkdir(path,{recursive:true});
  await page.screenshot({path:`${path}/desktop.png`,fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'mobile overflow');
  await page.screenshot({path:`${path}/mobile.png`,fullPage:true});
  await page.reload();await page.getByRole('button',{name:'模型记录',exact:true}).click();
  await page.getByText(/测试历史（最近 [1-9]/).waitFor();
  console.log(JSON.stringify({status:result.status,answer:result.answer,model:result.actual_model,elapsed_ms:result.elapsed_ms,response_id:result.response_id,history_persisted:true,mobile_overflow:false}));
} finally { await browser.close(); }
