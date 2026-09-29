// Actual operator controls -> actual summary/model plan -> worker/file verification.
import { chromium } from '@playwright/test';
import { spawn, execFileSync } from 'node:child_process';
import { randomBytes, randomUUID } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const project = path.resolve(import.meta.dirname, '../..');
const python = path.join(project, '.venv/bin/python');
const root = path.join(project, '.runtime/summary-browser-validation', randomUUID());
await mkdir(root, { recursive: true });
const readLedger = script => JSON.parse(execFileSync(python, ['-c', script, root], { cwd: project, encoding: 'utf8' }));
const seed = readLedger(`
import json,sys,uuid
from pathlib import Path
from robot_agent.store import Store
from robot_agent.runtime import Runtime
from robot_agent.actions import Actions,local_principal
root=Path(sys.argv[1]);source=root/'protocol.md';doc=Path('docs/SKILL_PROTOCOL.md').read_text();source.write_text(doc)
s=Store(root/'ledger');Runtime(s).install_local_skills([str(root)])
a=Actions(s)
def call(name,args):return a.call(name,args,local_principal(),idempotency_key=str(uuid.uuid4()))['result']
session=call('session.create',{'robot_id':'r1','goal':'归档会话指定的实际协议文件，使用 file.ingest 后接 asset.verify。系统资产库存储位置已配置，无须其他目标路径，不涉及机器人运动。'})['session']
texts=['实际源文件路径是 '+str(source)+'，请保留该路径。','固定约束：file.ingest metadata 为 kind=document、encoding=utf8、robot_id=r1、source=browser-summary-constraint。最终验证节点必须是 asset.verify。']
texts+=['项目协议原文背景，不是额外任务：'+doc[i:i+1200] for i in range(0,len(doc),1200)]
texts+=['仅归档指定文件。','必须检查实际归档字节，不把文档示例当成执行结果。']
for text in texts:session=call('session.message',{'session_id':session['id'],'expected_revision':session['revision'],'content':text})['session']
import hashlib
print(json.dumps({'session_id':session['id'],'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'original_turn_count':len(session['turns'])}));s.close()
`);
const token = randomBytes(32).toString('hex');
const auth = path.join(root, 'auth.json');
await writeFile(auth, JSON.stringify({ principals: [{ subject: `local:${process.env.USER}`, token_env: 'SUMMARY_UI_TOKEN', permissions: ['planning.use', 'tasks.read', 'tasks.submit'], robots: ['r1'] }] }));
const server = spawn(python, ['-m', 'robot_agent.application', '--root', path.join(root, 'ledger'), '--auth-config', auth, '--static', path.join(project, 'ui/dist'), '--port', '18770'], { cwd: project, env: { ...process.env, SUMMARY_UI_TOKEN: token }, stdio: ['ignore', 'ignore', 'pipe'] });
let stderr = ''; server.stderr.on('data', b => { stderr += b; });
let browser, page, worker;
const report = { status: 'running', root, seed, mock_used: false, simulation_used: false, console_errors: [] };
try {
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error(`server exited: ${stderr}`);
    try { if ((await fetch('http://127.0.0.1:18770/api/v1/overview')).ok) break; } catch {}
    if (i === 99) throw new Error('server did not start');
    await new Promise(r => setTimeout(r, 100));
  }
  browser = await chromium.launch({ headless: true });
  page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', e => report.console_errors.push(e.message));
  await page.goto('http://127.0.0.1:18770');
  await page.getByRole('button', { name: '任务协作', exact: true }).click();
  await page.getByLabel('应用操作凭据', { exact: true }).fill(token);
  await page.getByRole('button', { name: '连接', exact: true }).click();
  await page.getByText('应用服务已连接', { exact: true }).waitFor();
  await page.getByLabel('恢复已有会话', { exact: true }).fill(seed.session_id);
  await page.getByRole('button', { name: '读取会话', exact: true }).click();
  const history = page.getByRole('region', { name: '历史摘要与预算', exact: true });
  await history.getByLabel('分析或规划超预算时自动摘要', { exact: true }).check();
  await history.getByLabel('近期保留原文的消息数', { exact: true }).fill('2');
  await history.locator('.workbench-history-pins > summary').click();
  await history.getByLabel('保留第 3 条消息原文', { exact: true }).check();
  if (await history.getByRole('button', { name: '立即生成历史摘要', exact: true }).isEnabled()) throw new Error('unsaved policy must not run summary');
  await history.getByRole('button', { name: '保存摘要策略', exact: true }).click();
  await history.getByText('当前策略已同步。保存策略不调用模型。', { exact: true }).waitFor();
  const before = readLedger(`import json,sys\nfrom robot_agent.store import Store\ns=Store(sys.argv[1]+'/ledger');print(json.dumps(len(s.list('model_responses'))));s.close()`);
  if (before !== 0) throw new Error('saving policy called model');
  await history.getByRole('button', { name: '立即生成历史摘要', exact: true }).click();
  await history.getByRole('heading', { name: '当前历史摘要 · 模型整理', exact: true }).waitFor({ timeout: 240000 });
  if (!(await history.locator('.workbench-history-summary').innerText()).includes(seed.source)) throw new Error('summary omitted actual source path');
  await history.locator('.workbench-history-summary li details > summary').first().click();
  const sourceText = await history.locator('.workbench-history-source').first().innerText();
  if (!sourceText.trim()) throw new Error('source disclosure is empty');
  await history.locator('.workbench-history-summary li details > summary').first().click();
  await history.locator('.workbench-history-pins > summary').click();
  // Keep controls connected; only conceal credentials in the capture.
  await page.getByLabel('应用操作凭据', { exact: true }).evaluate(el => { el.style.visibility = 'hidden'; });
  for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    await page.setViewportSize(viewport);
    await page.evaluate(async () => { await document.fonts.ready; window.scrollTo(0, 0); await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); });
    await page.screenshot({ path: path.join(root, name + '.png'), fullPage: true, animations: 'disabled' });
  }
  report.mobile_overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  if (report.mobile_overflow) throw new Error('mobile overflow');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByLabel('应用操作凭据', { exact: true }).evaluate(el => { el.style.visibility = ''; });
  await page.getByRole('button', { name: '分析当前目标', exact: true }).click();
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some(b => b.textContent === '生成计划草稿' && !b.disabled), undefined, { timeout: 180000 });
  await page.getByRole('button', { name: '生成计划草稿', exact: true }).click();
  await page.getByRole('button', { name: '提交当前计划', exact: true }).waitFor({ timeout: 180000 });
  worker = spawn(python, ['-m', 'robot_agent.cli', '--root', path.join(root, 'ledger'), 'run'], { cwd: project, env: process.env, stdio: ['ignore', 'ignore', 'pipe'] });
  worker.stderr.on('data', b => { stderr += b; });
  await page.getByRole('button', { name: '提交当前计划', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.workbench-result')?.textContent.includes('succeeded'), undefined, { timeout: 60000 });
  const proof = readLedger(`
import json,sys
from robot_agent.store import Store
s=Store(sys.argv[1]+'/ledger');task=s.list('tasks')[0];draft=s.list('plan_drafts')[0]
r=s.get('model_responses',draft['model_response_id']);m=s.get('context_manifests',r['context_manifest_id'])
session=s.list('sessions')[0];summary=s.get('session_summaries',session['history_summary']['id'])
print(json.dumps({'task':task,'summary':summary,'session':session,'manifest':m,'response':{'id':r['id'],'actual_model':r['actual_model'],'response_id':r['response_id'],'messages':r['request']['messages'],'has_raw_response':bool(r['raw'])}}));s.close()
`);
  const actual = proof.task.steps[proof.task.plan.verification].result;
  if (actual.output.sha256 !== seed.sha256 || !actual.quiescent || !actual.evidence.length) throw new Error('actual file verification failed');
  if (!proof.manifest.included.includes('session-summary') || !JSON.stringify(proof.response.messages).includes('browser-summary-constraint') || !proof.response.has_raw_response) throw new Error('actual planning context evidence missing');
  const ingest = proof.task.plan.steps.find(s => s.skill === 'file.ingest');
  if (ingest.args.path !== seed.source || ingest.args.metadata.source !== 'browser-summary-constraint') throw new Error('actual plan violated source/constraint');
  if (proof.session.turns.length < seed.original_turn_count || proof.summary.covered_turns.some(t => t.id === proof.session.turns[2].id)) throw new Error('pinned/original history lost');
  delete proof.response.messages;
  report.proof = proof;
  // Strategy changes invalidate the existing draft without another AI call.
  await history.getByLabel('分析或规划超预算时自动摘要', { exact: true }).uncheck();
  await history.getByRole('button', { name: '保存摘要策略', exact: true }).click();
  await history.getByText('当前策略已同步。保存策略不调用模型。', { exact: true }).waitFor();
  if (await page.getByRole('button', { name: '提交当前计划', exact: true }).count()) throw new Error('old draft remains after policy mutation');
  // Reload the actual application/session and verify persisted summary/policy.
  await page.reload();
  await page.getByRole('button', { name: '任务协作', exact: true }).click();
  await page.getByLabel('应用操作凭据', { exact: true }).fill(token);
  await page.getByRole('button', { name: '连接', exact: true }).click();
  await page.getByText('应用服务已连接', { exact: true }).waitFor();
  await page.getByLabel('恢复已有会话', { exact: true }).fill(seed.session_id);
  await page.getByRole('button', { name: '读取会话', exact: true }).click();
  await history.getByRole('heading', { name: '当前历史摘要 · 模型整理', exact: true }).waitFor();
  if (await history.getByLabel('分析或规划超预算时自动摘要', { exact: true }).isChecked()) throw new Error('saved disabled policy not restored');
  if (await history.getByLabel('近期保留原文的消息数', { exact: true }).inputValue() !== '2') throw new Error('recent count not restored');
  // Real source mutation must report invalid summary without hiding original session.
  readLedger(`import json,sys\nfrom robot_agent.store import Store\ns=Store(sys.argv[1]+'/ledger');x=s.list('sessions')[0];x['turns'][0]['content']+=' 原文记录已修改。';s.put('sessions',x['id'],x);print(json.dumps(True));s.close()`);
  await page.getByRole('button', { name: '刷新会话', exact: true }).click();
  await history.getByRole('alert').filter({ hasText: 'summary source turn changed' }).waitFor();
  if (report.console_errors.length) throw new Error(report.console_errors.join('\n'));
  Object.assign(report, { status: 'passed', actual_result: actual, checks: ['policy save without AI', 'pinned original', 'actual summary and source disclosure', 'actual planning input/output', 'worker hash', 'policy invalidates draft', 'reload restoration', 'source corruption visible'] });
} catch (e) { report.status = 'failed'; report.error = e.message; throw e; }
finally {
  await writeFile(path.join(root, 'report.json'), JSON.stringify(report, null, 2));
  if (browser) await browser.close();
  for (const child of [worker, server]) if (child) {
    child.kill('SIGTERM');
    await new Promise(resolve => { if (child.exitCode !== null) resolve(); else child.once('exit', resolve); });
  }
  console.log('Summary browser validation:', path.join(root, 'report.json'));
}
