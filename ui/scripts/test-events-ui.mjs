import { chromium } from '@playwright/test';
import { spawn, execFileSync } from 'node:child_process';
import { randomBytes, randomUUID } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
const project = path.resolve(import.meta.dirname, '../..');
const python = path.join(project, '.venv/bin/python');
const sourceRoot = path.resolve(process.env.EVENT_UI_SOURCE_ROOT || '.runtime/multifile-validation/226fe510-73f6-4516-af2e-ba3354c74443');
const captureRoot = process.env.EVENT_UI_CAPTURE_ROOT;
const root = captureRoot ? path.resolve(captureRoot) : path.join(project, '.runtime/event-browser-validation', randomUUID());
await mkdir(root, { recursive: true });
const ledger = script => JSON.parse(execFileSync(python, ['-c', `import json,sys\nfrom robot_agent.store import Store\ns=Store(sys.argv[1]+'/ledger')\n${script}\ns.close()`, root, sourceRoot], { cwd: project, encoding: 'utf8' }));
const seed = captureRoot ? JSON.parse(await readFile(path.join(root, 'report.json'), 'utf8')).seed : ledger(`from pathlib import Path
from robot_agent.runtime import Runtime
origin=Store(Path(sys.argv[2])/'ledger');origin.db.backup(s.db);origin.close()
original=json.loads((Path(sys.argv[2])/'report.json').read_text());assert original['status']=='passed'
models=s.list('model_responses');assert all(r['raw'] and r['response_id'] for r in models)
rt=Runtime(s);rt.install_local_skills([sys.argv[1]])
p=Path(sys.argv[1])/'protocol.md';p.write_bytes(Path('docs/SKILL_PROTOCOL.md').read_bytes())
plan={'steps':[{'id':'archive','skill':'file.ingest','args':{'path':str(p),'metadata':{'kind':'document','encoding':'utf8','source':str(p)}}},{'id':'check','skill':'asset.verify','deps':['archive'],'args':{'asset_id':{'$ref':'archive.asset_id'}}}],'verification':'check'}
t=rt.submit(plan,'r1',goal='实际分页验证：协议文档归档')
for _ in range(32):
 rt.interrupt(t['id'],'pause');assert rt.tick(t['id'])['status']=='paused';rt.resume(t['id'])
t=rt.tick(t['id']);assert t['status']=='succeeded'
print(json.dumps({'model_task':original['task_id'],'model_events':len(s.events(original['task_id'])),'long_task':t['id'],'long_events':len(s.events(t['id'])),'models':len(models),'executions':len(s.list('executions'))}))`);
if (seed.long_events <= 50) throw new Error('actual control history did not exceed one page');
const token = randomBytes(32).toString('hex');
const auth = path.join(root, 'auth.json');
await writeFile(auth, JSON.stringify({ principals: [{ subject: 'event-reader', token_env: 'EVENT_UI_TOKEN', permissions: ['tasks.read'], robots: ['r1'] }] }));
let server, browser;
const start = async () => {
  server = spawn(python, ['-m', 'robot_agent.application', '--root', path.join(root, 'ledger'), '--auth-config', auth, '--static', path.join(project, 'ui/dist'), '--port', '18773'], { cwd: project, env: { ...process.env, EVENT_UI_TOKEN: token }, stdio: ['ignore', 'ignore', 'pipe'] });
  let errors = ''; server.stderr.on('data', b => { errors += b; });
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error(errors);
    try { if ((await fetch('http://127.0.0.1:18773/api/v1/overview')).ok) return; } catch {}
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error('application startup timed out');
};
const stop = async () => {
  if (!server || server.exitCode !== null || server.signalCode !== null) return;
  server.kill('SIGTERM'); await new Promise(resolve => server.once('exit', resolve));
};
const report = { status: 'running', root, sourceRoot, seed, mock_used: false, simulation_used: false, new_model_calls: 0, console_errors: [], page_requests: [] };
try {
  await start(); browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', e => report.console_errors.push(e.message));
  page.on('request', req => { if (req.url().endsWith('/actions/task.events-page')) report.page_requests.push(req.postDataJSON()); });
  await page.goto('http://127.0.0.1:18773');
  await page.getByRole('button', { name: '任务协作', exact: true }).click();
  const connect = async () => {
    await page.getByLabel('应用操作凭据', { exact: true }).fill(token);
    await page.getByRole('button', { name: '连接', exact: true }).click();
    await page.getByText('应用服务已连接', { exact: true }).waitFor();
  };
  await connect();
  const panel = page.getByRole('region', { name: '任务事件记录', exact: true });
  await panel.getByLabel('查看任务', { exact: true }).selectOption(seed.long_task);
  await panel.getByText('已读取 50 条事件', { exact: true }).waitFor();
  await panel.getByRole('button', { name: '加载后续事件', exact: true }).click();
  await panel.getByText(`已读取 ${seed.long_events} 条事件`, { exact: true }).waitFor();
  await panel.getByLabel('查看任务', { exact: true }).selectOption(seed.model_task);
  await panel.getByText(`已读取 ${seed.model_events} 条事件`, { exact: true }).waitFor();
  if (await panel.locator('ol > li').count() !== seed.model_events) throw new Error('task switch retained unrelated events');
  await stop();
  await panel.getByRole('button', { name: '刷新事件', exact: true }).click();
  await panel.getByRole('alert').waitFor();
  if (await panel.locator('ol > li').count() !== seed.model_events) throw new Error('disconnect discarded records');
  await start();
  await panel.getByRole('alert').waitFor({ state: 'hidden', timeout: 15000 });
  if (await panel.locator('ol > li').count() !== seed.model_events) throw new Error('reconnect duplicated records');
  await page.getByLabel('应用操作凭据', { exact: true }).fill('');
  await panel.waitFor({ state: 'hidden' });
  await connect();
  await panel.getByLabel('查看任务', { exact: true }).selectOption(seed.model_task);
  await panel.getByText(`已读取 ${seed.model_events} 条事件`, { exact: true }).waitFor();
  const result = panel.locator('ol > li').filter({ hasText: '执行结果' }).first();
  await result.getByText('查看事件证据', { exact: true }).click();
  if (!(await result.innerText()).includes('execution_id')) throw new Error('actual execution evidence missing');
  report.computed_styles = await result.evaluate(el => Object.fromEntries(['summary', 'pre'].map(tag => {
    const style = getComputedStyle(el.querySelector(tag)); return [tag, { fontSize: style.fontSize, color: style.color }];
  })));
  if (Object.values(report.computed_styles).some(style => parseFloat(style.fontSize) < 12 || style.color !== 'rgb(38, 60, 50)')) throw new Error('evidence text style overridden');
  for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    await page.setViewportSize(viewport); await panel.scrollIntoViewIfNeeded();
    await panel.evaluate(el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 90));
    await page.screenshot({ path: path.join(root, name + '.png'), animations: 'disabled' });
    if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) throw new Error(name + ' overflow');
  }
  const after = ledger("print(json.dumps({'models':len(s.list('model_responses')),'executions':len(s.list('executions'))}))");
  if (after.models !== seed.models || after.executions !== seed.executions || report.console_errors.length) throw new Error('read-only or browser invariant failed');
  report.status = 'passed';
  report.checks = ['actual control history pagination', 'task switch isolation', 'real server disconnect retains records', 'server restart resumes without duplicates', 'credential change clears events', 'actual model task evidence disclosure', 'desktop/mobile captures', 'no new model calls or executions'];
} catch (e) { report.status = 'failed'; report.error = e.message; throw e; }
finally {
  await writeFile(path.join(root, captureRoot ? 'recapture.json' : 'report.json'), JSON.stringify(report, null, 2));
  if (browser) await browser.close(); await stop();
  console.log('Actual event browser report:', path.join(root, captureRoot ? 'recapture.json' : 'report.json'));
}
