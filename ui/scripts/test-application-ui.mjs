// Exercises the real application, ledger, and configured live model. No route substitutes.
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { randomBytes, createHash } from 'node:crypto';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';

const project = path.resolve(import.meta.dirname, '../..');
const reportPath = process.env.APPLICATION_VALIDATION_REPORT;
if (!reportPath) throw new Error('APPLICATION_VALIDATION_REPORT must identify an actual clarification/failure report');
const report = JSON.parse(await readFile(reportPath, 'utf8'));
if (report.status !== 'passed' || report.kind !== 'clarification-and-failure-explanation') throw new Error('actual prior execution evidence required');
const output = path.join(report.root, 'browser');
await mkdir(output, { recursive: true });
const token = randomBytes(32).toString('hex');
const config = path.join(output, 'auth.json');
await writeFile(config, JSON.stringify({ principals: [{ subject: `local:${process.env.USER}`, token_env: 'APPLICATION_TEST_TOKEN', permissions: ['planning.use', 'tasks.read', 'tasks.submit', 'tasks.control', 'assets.read'], robots: ['*'] }] }));
const server = spawn(path.join(project, '.venv/bin/python'), ['-m', 'robot_agent.application', '--root', path.join(report.root, 'ledger'), '--auth-config', config, '--port', '18768', '--static', path.join(project, 'ui/dist')], { cwd: project, env: { ...process.env, APPLICATION_TEST_TOKEN: token }, stdio: ['ignore', 'pipe', 'pipe'] });
let stderr = '';
server.stderr.on('data', data => { stderr += data.toString(); });
let browser;
let worker;
const executeOnly = process.argv.includes('--execute-only');
const summary = { status: 'running', source_report: reportPath, task_id: report.task_id, session_id: report.session_id };
try {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error(`application exited: ${stderr}`);
    try { if ((await fetch('http://127.0.0.1:18768/api/v1/overview')).ok) break; } catch {}
    if (attempt === 99) throw new Error('application did not start');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:18768');
  if (!executeOnly) {
  await page.getByRole('button', { name: '任务流程', exact: true }).click();
  await page.locator('.react-flow__node').filter({ hasText: 'file.ingest' }).click();
  await page.getByRole('button', { name: '在任务协作中分析此节点' }).click();
  } else { await page.getByRole('button', { name: '任务协作', exact: true }).click(); }
  await page.getByLabel('应用操作凭据', { exact: true }).fill(token);
  await page.getByRole('button', { name: '连接', exact: true }).click();
  await page.getByText('应用服务已连接', { exact: true }).waitFor();
  if (!executeOnly) {
  await page.getByLabel('恢复已有会话', { exact: true }).fill(report.session_id);
  await page.getByRole('button', { name: '读取会话', exact: true }).click();
  await page.getByRole('button', { name: '将所选节点加入上下文' }).click();
  await page.getByRole('button', { name: '解释所选节点', exact: true }).click();
  await page.getByText('模型解释 · 依据所选账本记录', { exact: true }).waitFor({ timeout: 180000 });
  const explanation = await page.locator('.workbench-analysis').last().innerText();
  if (!explanation.includes('does-not-exist.txt')) throw new Error('model explanation omitted actual missing filename');
  if (errors.length) throw new Error(errors.join('\n'));
  // Never capture the operator credential, even in a password input.
  await page.getByLabel('应用操作凭据', { exact: true }).fill('');
  await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  if (overflow) throw new Error('mobile viewport overflows');
  summary.status = 'passed'; summary.explanation = explanation; summary.console_errors = errors; summary.mobile_overflow = overflow;
  } else {
    const source = path.join(report.root, 'actual-note.txt');
    const hash = createHash('sha256').update(await readFile(source)).digest('hex');
    await page.getByLabel('任务目标', { exact: true }).fill(`归档已经实际读取的本机文件 ${source}。使用 file.ingest，metadata 为 kind=document、encoding=utf8、source=browser-operator；再使用 asset.verify 校验上一步返回的 asset_id。SHA256 应为 ${hash}。系统资产库存储位置已配置，不需要外部备份，不涉及机器人运动。最终节点必须是 asset.verify。`);
    await page.getByRole('button', { name: '创建会话', exact: true }).click();
    await page.getByRole('button', { name: '分析当前目标', exact: true }).click();
    await page.waitForFunction(() => [...document.querySelectorAll('button')].some(b => b.textContent === '生成计划草稿' && !b.disabled), undefined, { timeout: 180000 });
    await page.getByRole('button', { name: '生成计划草稿', exact: true }).click();
    await page.getByRole('button', { name: '提交当前计划', exact: true }).waitFor({ timeout: 180000 });
    worker = spawn(path.join(project, '.venv/bin/python'), ['-m', 'robot_agent.cli', '--root', path.join(report.root, 'ledger'), 'run'], { cwd: project, env: process.env, stdio: ['ignore', 'pipe', 'pipe'] });
    worker.stderr.on('data', data => { stderr += data.toString(); });
    await page.getByRole('button', { name: '提交当前计划', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.workbench-result')?.textContent?.includes('succeeded'), undefined, { timeout: 60000 });
    const taskId = await page.locator('.workbench-result > code').innerText();
    const { execFileSync } = await import('node:child_process');
    const task = JSON.parse(execFileSync(path.join(project, '.venv/bin/python'), ['-m', 'robot_agent.cli', '--root', path.join(report.root, 'ledger'), 'status', taskId], { cwd: project, encoding: 'utf8' }));
    const actual = task.steps[task.plan.verification].result;
    if (task.status !== 'succeeded' || actual.output.sha256 !== hash || !actual.quiescent || !actual.evidence.length) throw new Error('actual worker output does not prove the browser goal');
    if (errors.length) throw new Error(errors.join('\n'));
    summary.status = 'passed'; summary.kind = 'browser-plan-and-real-execution'; summary.executed_task_id = taskId; summary.expected_sha256 = hash; summary.actual_result = actual; summary.console_errors = errors;
  }
} catch (error) {
  summary.status = 'failed'; summary.error = error.message;
  throw error;
} finally {
  await writeFile(path.join(output, executeOnly ? 'execution-report.json' : 'report.json'), JSON.stringify(summary, null, 2));
  if (browser) await browser.close();
  if (worker) { worker.kill('SIGTERM'); await new Promise(resolve => { if (worker.exitCode !== null) resolve(); else worker.once('exit', resolve); }); }
  server.kill('SIGTERM');
  await new Promise(resolve => { if (server.exitCode !== null) resolve(); else server.once('exit', resolve); });
  console.log('Browser validation:', path.join(output, 'report.json'));
}
