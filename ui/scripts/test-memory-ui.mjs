// Real browser -> scoped memory -> actual environment model -> actual worker/file bytes.
import { chromium } from '@playwright/test';
import { spawn, execFileSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const project = path.resolve(import.meta.dirname, '../..');
const python = path.join(project, '.venv/bin/python');
const root = path.join(project, '.runtime/memory-browser-validation', crypto.randomUUID());
await mkdir(root, { recursive: true });
const runPython = script => JSON.parse(execFileSync(python, ['-c', script, root], { cwd: project, encoding: 'utf8' }));
const seed = runPython(`
import json,sys,hashlib
from pathlib import Path
from robot_agent.store import Store
from robot_agent.memory import Memory
from robot_agent.runtime import Runtime
root=Path(sys.argv[1]); source=root/'protocol.md'
source.write_bytes(Path('docs/SKILL_PROTOCOL.md').read_bytes())
s=Store(root/'ledger'); Runtime(s).install_local_skills([str(root)])
a=Memory(s).ingest(source,{'kind':'document','encoding':'utf8','robot_id':'r1','source':str(source)})
m=Memory(s).remember('document','工作台归档协议：'+source.read_text()[:180],{'robot_id':'r1','source_file':str(source),'sha256':a['sha256']},[a['id']])
print(json.dumps({'memory_id':m['id'],'source':str(source),'sha256':a['sha256']}));s.close()
`);
const token = randomBytes(32).toString('hex');
const auth = path.join(root, 'auth.json');
await writeFile(auth, JSON.stringify({ principals: [{ subject: `local:${process.env.USER}`, token_env: 'MEMORY_UI_TOKEN', permissions: ['planning.use', 'memory.read', 'assets.read', 'tasks.read', 'tasks.submit'], robots: ['r1'] }] }));
const server = spawn(python, ['-m', 'robot_agent.application', '--root', path.join(root, 'ledger'), '--auth-config', auth, '--static', path.join(project, 'ui/dist'), '--port', '18769'], { cwd: project, env: { ...process.env, MEMORY_UI_TOKEN: token }, stdio: ['ignore', 'ignore', 'pipe'] });
let stderr = ''; server.stderr.on('data', b => { stderr += b; });
let browser, worker, page;
const report = { status: 'running', root, seed, mock_used: false, simulation_used: false };
try {
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error(`server exited: ${stderr}`);
    try { if ((await fetch('http://127.0.0.1:18769/api/v1/overview')).ok) break; } catch {}
    if (i === 99) throw new Error('server did not start');
    await new Promise(r => setTimeout(r, 100));
  }
  browser = await chromium.launch({ headless: true });
  page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = []; report.console_errors = errors; page.on('pageerror', e => errors.push(e.message));
  await page.goto('http://127.0.0.1:18769');
  await page.getByRole('button', { name: '任务协作', exact: true }).click();
  await page.getByLabel('应用操作凭据', { exact: true }).fill(token);
  await page.getByRole('button', { name: '连接', exact: true }).click();
  await page.getByText('应用服务已连接', { exact: true }).waitFor();
  await page.getByLabel('任务目标', { exact: true }).fill('归档绑定记忆中 attributes.source_file 指向的实际协议文件，然后验证实际归档资产字节。路径和 SHA256 从记忆获取，不要猜测。使用 file.ingest，metadata 为 kind=document、encoding=utf8、robot_id=r1、source=browser-memory-document；再用 asset.verify 校验上一步实际返回的 asset_id，最终节点必须为 asset.verify。系统归档位置已经配置，无须另一个目标路径，不涉及机器人运动。');
  await page.getByRole('button', { name: '创建会话', exact: true }).click();
  const memory = page.getByRole('region', { name: '会话记忆', exact: true });
  await memory.getByLabel('记忆关键词', { exact: true }).fill('不存在的检索词-9a457e');
  await memory.getByRole('button', { name: '检索记忆', exact: true }).click();
  await memory.getByText('未找到有效记忆，请调整关键词。', { exact: true }).waitFor();
  await memory.getByLabel('记忆关键词', { exact: true }).fill('工作台归档协议');
  await memory.getByRole('button', { name: '检索记忆', exact: true }).click();
  await memory.getByRole('checkbox').check();
  await memory.getByRole('button', { name: '使用所选记忆', exact: true }).click();
  await memory.getByText('当前已绑定 1 条记忆', { exact: true }).waitFor();
  await memory.getByRole('button', { name: '清除绑定记忆', exact: true }).click();
  await memory.getByText('当前已绑定 0 条记忆', { exact: true }).waitFor();
  await memory.getByRole('checkbox').check();
  await memory.getByRole('button', { name: '使用所选记忆', exact: true }).click();
  await memory.getByText('当前已绑定 1 条记忆', { exact: true }).waitFor();
  const before = runPython(`import json,sys\nfrom robot_agent.store import Store\ns=Store(sys.argv[1]+'/ledger');print(json.dumps(len(s.list('model_responses'))));s.close()`);
  if (before !== 0) throw new Error('search/binding unexpectedly called model');
  // Keep real connected controls enabled; conceal credential field only for capture.
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
  if (!process.argv.includes('--controls-only')) {
  await page.getByRole('button', { name: '分析当前目标', exact: true }).click();
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some(b => b.textContent === '生成计划草稿' && !b.disabled), undefined, { timeout: 180000 });
  await page.getByRole('button', { name: '生成计划草稿', exact: true }).click();
  await page.getByRole('button', { name: '提交当前计划', exact: true }).waitFor({ timeout: 180000 });
  worker = spawn(python, ['-m', 'robot_agent.cli', '--root', path.join(root, 'ledger'), 'run'], { cwd: project, env: process.env, stdio: ['ignore', 'ignore', 'pipe'] });
  worker.stderr.on('data', b => { stderr += b; });
  await page.getByRole('button', { name: '提交当前计划', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.workbench-result')?.textContent.includes('succeeded'), undefined, { timeout: 60000 });
  const proof = runPython(`
import json,sys
from robot_agent.store import Store
s=Store(sys.argv[1]+'/ledger');t=s.list('tasks')[0];d=s.list('plan_drafts')[0]
r=s.get('model_responses',d['model_response_id']);m=s.get('context_manifests',r['context_manifest_id'])
print(json.dumps({'task':t,'response':{'id':r['id'],'actual_model':r['actual_model'],'response_id':r['response_id'],'messages':r['request']['messages'],'has_raw_response':bool(r['raw'])},'manifest':m}));s.close()
`);
  const actual = proof.task.steps[proof.task.plan.verification].result;
  if (actual.output.sha256 !== seed.sha256 || !actual.quiescent || !actual.evidence.length) throw new Error('execution evidence does not prove byte integrity');
  if (!proof.manifest.included.includes('memory:' + seed.memory_id) || !JSON.stringify(proof.response.messages).includes(seed.source) || !proof.response.has_raw_response) throw new Error('actual model context missing retrieved memory');
  if (proof.task.plan.steps.find(s => s.skill === 'file.ingest').args.path !== seed.source) throw new Error('actual model did not use retrieved file path');
  delete proof.response.messages;
  Object.assign(report, { proof, actual_result: actual });
  // Rebinding invalidates the reviewed draft and analysis, even after a task has run.
  await memory.getByRole('button', { name: '清除绑定记忆', exact: true }).click();
  await memory.getByText('当前已绑定 0 条记忆', { exact: true }).waitFor();
  if (await page.getByRole('button', { name: '提交当前计划', exact: true }).count()) throw new Error('stale draft still displayed after memory change');
  if (await page.getByRole('button', { name: '生成计划草稿', exact: true }).isEnabled()) throw new Error('analysis was not invalidated');
  }
  await page.getByRole('button', { name: '开始另一会话', exact: true }).click();
  await page.getByLabel('任务目标', { exact: true }).fill('下一项独立任务');
  await page.getByRole('button', { name: '创建会话', exact: true }).click();
  await memory.getByText('当前已绑定 0 条记忆', { exact: true }).waitFor();
  if (await memory.getByRole('checkbox').count()) throw new Error('search results leaked into next session');
  if (errors.length) throw new Error(errors.join('\n'));
  Object.assign(report, { status: 'passed', controls_only: process.argv.includes('--controls-only'), console_errors: errors, checks: process.argv.includes('--controls-only') ? ['empty search', 'bind/clear', 'no automatic model call', 'session isolation'] : ['empty search', 'bind/clear', 'no automatic model call', 'actual model context', 'actual model plan path', 'worker hash', 'stale draft invalidation', 'session isolation'] });
} catch (e) { report.status = 'failed'; report.error = e.message; if (page) { report.visible_text_at_failure = await page.locator('body').innerText(); await page.getByLabel('应用操作凭据', { exact: true }).fill('').catch(() => {}); await page.screenshot({ path: path.join(root, 'failure.png'), fullPage: true }); } throw e; }
finally {
  await writeFile(path.join(root, 'report.json'), JSON.stringify(report, null, 2));
  if (browser) await browser.close();
  for (const child of [worker, server]) if (child) {
    child.kill('SIGTERM');
    await new Promise(resolve => { if (child.exitCode !== null) resolve(); else child.once('exit', resolve); });
  }
  console.log('Memory browser validation:', path.join(root, 'report.json'));
}
