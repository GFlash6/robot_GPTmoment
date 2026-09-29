import { chromium } from '@playwright/test';
import { spawn, execFileSync } from 'node:child_process';
import { randomBytes, randomUUID } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const project = path.resolve(import.meta.dirname, '../..');
const python = path.join(project, '.venv/bin/python');
const captureRoot = process.env.AUTOMATION_UI_CAPTURE_ROOT;
const root = captureRoot ? path.resolve(captureRoot) : path.join(project, '.runtime/automation-browser-validation', randomUUID());
await mkdir(root, { recursive: true });
const ledger = script => JSON.parse(execFileSync(python, ['-c', `import json,sys\nfrom robot_agent.store import Store\ns=Store(sys.argv[1]+'/ledger')\n${script}\ns.close()`, root], { cwd: project, encoding: 'utf8' }));
const subject = ledger("from robot_agent.actions import local_principal\nprint(json.dumps(local_principal().subject))");
const token = randomBytes(32).toString('hex');
const auth = path.join(root, 'auth.json');
await writeFile(auth, JSON.stringify({ principals: [{ subject, token_env: 'AUTOMATION_UI_TOKEN', permissions: ['automations.manage', 'tasks.read', 'planning.use'], robots: ['r1'] }] }));
const server = spawn(python, ['-m', 'robot_agent.application', '--root', path.join(root, 'ledger'), '--auth-config', auth, '--static', path.join(project, 'ui/dist'), '--port', '18771'], { cwd: project, env: { ...process.env, AUTOMATION_UI_TOKEN: token }, stdio: ['ignore', 'ignore', 'pipe'] });
let stderr = ''; server.stderr.on('data', b => { stderr += b; });
let browser;
const report = { status: 'running', root, mock_used: false, simulation_used: false, console_errors: [] };
const worker = async (...flags) => {
  const child = spawn(python, ['-m', 'robot_agent.cli', '--root', path.join(root, 'ledger'), 'automation-worker', ...flags], { cwd: project, stdio: ['ignore', 'pipe', 'pipe'] });
  let errors = ''; child.stderr.on('data', b => { errors += b; }); child.stdout.on('data', () => {});
  const timeout = setTimeout(() => child.kill('SIGTERM'), 180000);
  try { const code = await new Promise(resolve => child.once('exit', resolve)); if (code !== 0) throw new Error(`worker: ${code} ${errors}`); }
  finally { clearTimeout(timeout); }
};
try {
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error(stderr);
    try { if ((await fetch('http://127.0.0.1:18771/api/v1/overview')).ok) break; } catch {}
    if (i === 99) throw new Error('app did not start');
    await new Promise(r => setTimeout(r, 100));
  }
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', e => report.console_errors.push(e.message));
  const connect = async () => {
    await page.getByRole('button', { name: '任务协作', exact: true }).click();
    await page.getByLabel('应用操作凭据', { exact: true }).fill(token);
    await page.getByRole('button', { name: '连接', exact: true }).click();
    await page.getByText('应用服务已连接', { exact: true }).waitFor();
  };
  await page.goto('http://127.0.0.1:18771'); await connect();
  const panel = page.getByRole('region', { name: '失败事件自动诊断', exact: true });
  if (!captureRoot) {
  await panel.getByText('尚未创建诊断规则。', { exact: true }).waitFor();
  await panel.getByLabel('累计诊断次数上限', { exact: true }).fill('0');
  if (await panel.getByRole('button', { name: '创建并启用规则' }).isEnabled()) throw new Error('invalid budget enabled');
  await panel.getByLabel('累计诊断次数上限', { exact: true }).fill('3');
  await panel.getByRole('button', { name: '创建并启用规则' }).click();
  await panel.getByText('规则已启用', { exact: true }).waitFor();
  if (ledger("print(json.dumps(len(s.list('model_responses'))))") !== 0) throw new Error('rule creation called model');
  report.actual_failure = ledger("from pathlib import Path\nsys.path.insert(0,'tests')\nfrom test_automations_live import actual_failure\nprint(json.dumps(actual_failure(s,Path(sys.argv[1]))))");
  await worker('--scan-only');
  await panel.getByText('已排队，等待诊断 worker', { exact: true }).waitFor();
  // Actually corrupt the queued source, verify rejection, then restore exact saved bytes.
  ledger("j=s.list('automation_runs')[0];s.db.execute('UPDATE events SET data=? WHERE seq=?',('{}',j['event']['seq']));print(json.dumps(True))");
  await worker('--once');
  await panel.getByText('诊断失败', { exact: true }).waitFor();
  await panel.getByText('automation event changed', { exact: true }).waitFor();
  ledger("j=s.list('automation_runs')[0];s.db.execute('UPDATE events SET data=? WHERE seq=?',(j['event']['data'],j['event']['seq']));print(json.dumps(True))");
  await panel.getByRole('button', { name: '重新诊断此事件', exact: true }).click();
  await panel.getByText('已排队，等待诊断 worker', { exact: true }).waitFor();
  await worker('--once');
  await panel.getByText('诊断完成', { exact: true }).waitFor({ timeout: 150000 });
  report.proof = ledger("jobs=s.list('automation_runs');j=next(x for x in jobs if x['status']=='completed');r=s.get('model_responses',j['model_response_id']);assert r['raw'] and r['response_id'] and r['actual_model'];assert r['parsed']['observed_error']==json.loads(j['event']['data'])['error'];print(json.dumps({'job':j,'request':r['request'],'model':r['actual_model'],'response_id':r['response_id'],'model_calls':len(s.list('model_responses')),'task':s.get('tasks',j['event']['task'])}))");
  if (report.proof.model_calls !== 1 || report.proof.task.status !== 'failed') throw new Error('model count or task state incorrect');
  const completed = panel.locator('.workbench-automation-runs > li').filter({ hasText: '诊断完成' });
  await completed.getByText('已记录错误与引用', { exact: true }).click();
  if (!(await completed.innerText()).includes(report.proof.job.result.explanation.observed_error)) throw new Error('actual error missing from UI');
  await panel.getByRole('button', { name: '暂停规则', exact: true }).click();
  await panel.getByText('规则已暂停', { exact: true }).waitFor();
  if (await panel.getByRole('button', { name: '重新诊断此事件', exact: true }).isEnabled()) throw new Error('paused rule permits retry');
  await page.reload(); await connect();
  await panel.getByText('规则已暂停', { exact: true }).waitFor();
  await panel.getByRole('button', { name: '启用规则', exact: true }).click();
  await panel.getByText('规则已启用', { exact: true }).waitFor();
  await panel.getByText('诊断完成', { exact: true }).waitFor();
  await completed.getByText('已记录错误与引用', { exact: true }).click();
  } else {
    await panel.getByText('诊断完成', { exact: true }).waitFor();
    await panel.getByText('已记录错误与引用', { exact: true }).click();
  }
  await page.getByLabel('应用操作凭据', { exact: true }).evaluate(el => { el.style.visibility = 'hidden'; });
  for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    await page.setViewportSize(viewport); await page.evaluate(async () => { await document.fonts.ready; window.scrollTo(0,0); });
    if (!process.env.AUTOMATION_UI_SKIP_SCREENSHOTS) await page.screenshot({ path: path.join(root, name + (captureRoot ? '-final.png' : '.png')), fullPage: true, animations: 'disabled' });
  }
  report.mobile_overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  if (report.mobile_overflow || report.console_errors.length) throw new Error('rendering error or overflow');
  if (ledger("print(json.dumps(len(s.list('model_responses'))))") !== 1) throw new Error('poll or reload called model');
  if (captureRoot) {
    server.kill('SIGTERM');
    await new Promise(resolve => { if (server.exitCode !== null || server.signalCode !== null) resolve(); else server.once('exit', resolve); });
    await panel.getByRole('button', { name: '刷新诊断记录', exact: true }).click();
    await panel.getByRole('alert').waitFor();
    if (!(await panel.getByText('诊断完成', { exact: true }).isVisible())) throw new Error('lost retained diagnosis after real server disconnect');
    report.disconnected_records_retained = true;
  }
  report.screenshots_reused = Boolean(process.env.AUTOMATION_UI_SKIP_SCREENSHOTS);
  report.status = 'passed';
  report.checks = captureRoot ? ['read-only final capture', 'actual server disconnect preserves last diagnosis'] : ['empty state', 'budget validation', 'create without model', 'actual failure and queue', 'source integrity failure displayed', 'explicit retry', 'actual model response and exact error', 'pause disables retry', 'reload restores rule', 'enable', 'desktop/mobile captures', 'read-only polling'];
} catch (e) { report.status = 'failed'; report.error = e.message; throw e; }
finally {
  await writeFile(path.join(root, captureRoot ? 'recapture.json' : 'report.json'), JSON.stringify(report, null, 2));
  if (browser) await browser.close();
  server.kill('SIGTERM');
  await new Promise(resolve => { if (server.exitCode !== null || server.signalCode !== null) resolve(); else server.once('exit', resolve); });
  console.log('Automation browser validation:', path.join(root, captureRoot ? 'recapture.json' : 'report.json'));
}
