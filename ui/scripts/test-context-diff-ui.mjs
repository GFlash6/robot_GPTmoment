import { chromium, expect } from '@playwright/test';
import { spawn, execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const project = path.resolve(import.meta.dirname, '../..');
const python = path.join(project, '.venv/bin/python');
const root = path.join(project, '.runtime/context-diff-browser-validation', randomUUID());
await mkdir(path.join(root, 'ledger'), { recursive: true });
const sql = code => JSON.parse(execFileSync(python, ['-c', `import json,sqlite3,sys,hashlib\nfrom pathlib import Path\ndb=sqlite3.connect(Path(sys.argv[1])/'ledger/ledger.sqlite')\n${code}\ndb.close()`, root], { cwd: project, encoding: 'utf8' }));
const seed = sql(`source=Path('.runtime/replanning-context-validation/93593234-4e6a-44a8-8bf0-e4ba3ae8ade9/ledger/ledger.sqlite').resolve()
origin=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);origin.backup(db);origin.close()
legacy_source=Path('.runtime/memory-validation/83872251-288f-402a-b821-592ce3297033/ledger/ledger.sqlite').resolve()
origin=sqlite3.connect(legacy_source.as_uri()+'?mode=ro',uri=True)
legacy=next(json.loads(r[0]) for r in origin.execute("SELECT data FROM objects WHERE collection='model_responses'") if not json.loads(r[0]).get('context_bundle_id') and not json.loads(r[0]).get('context_manifest_id'))
origin.close();assert legacy['raw'] and legacy['response_id']
db.execute('INSERT INTO objects VALUES(?,?,?)',('model_responses',legacy['id'],json.dumps(legacy,ensure_ascii=False,sort_keys=True)));db.commit()
records=[json.loads(r[0]) for r in db.execute("SELECT data FROM objects WHERE collection='model_responses'")]
assert all(r['raw'] and r['response_id'] for r in records)
bundles={r['id']:json.loads(db.execute("SELECT data FROM objects WHERE collection='context_bundles' AND id=?",(r['context_bundle_id'],)).fetchone()[0]) for r in records if r.get('context_bundle_id')}
first=next(r for r in records if r['method']=='planning' and bundles[r['id']]['request']['phase']=='planning')
recovery=next(r for r in records if r['method']=='planning' and bundles[r['id']]['request']['phase']=='replanning')
wire=db.execute("SELECT data FROM objects WHERE collection='context_bundles' AND id=?",(recovery['context_bundle_id'],)).fetchone()[0]
(Path(sys.argv[1])/'original-bundle.json').write_text(wire)
print(json.dumps({'first':first['id'],'recovery':recovery['id'],'legacy':legacy['id'],'bundle_id':recovery['context_bundle_id'],'source':str(source),'legacy_source':str(legacy_source),'models':len(records),'actual_response_ids':[r['response_id'] for r in records],'ledger_hash':hashlib.sha256('\\n'.join(sorted(db.iterdump())).encode()).hexdigest()}))`);
let server, browser;
const start = async () => {
  server = spawn(python, ['-m', 'robot_agent_observer.server', '--root', path.join(root, 'ledger'), '--static', path.join(project, 'ui/dist'), '--port', '18775'], { cwd: project, stdio: ['ignore', 'ignore', 'pipe'] });
  let errors = ''; server.stderr.on('data', b => { errors += b; });
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error(errors);
    try { if ((await fetch('http://127.0.0.1:18775/api/v1/overview')).ok) return; } catch {}
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error('observer startup timed out');
};
const stop = async () => {
  if (!server || server.exitCode !== null || server.signalCode !== null) return;
  const done = new Promise(resolve => server.once('exit', resolve)); server.kill('SIGTERM'); await done;
};
const report = { status: 'running', root, seed, mock_used: false, simulation_used: false, new_model_calls: 0, page_errors: [], mutations: [] };
try {
  await start(); browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', e => report.page_errors.push(e.message));
  page.on('request', r => { if (!['GET', 'HEAD'].includes(r.method())) report.mutations.push({ method: r.method(), url: r.url() }); });
  await page.goto('http://127.0.0.1:18775');
  await page.getByRole('button', { name: '模型记录', exact: true }).click();
  const diff = page.getByRole('region', { name: '上下文对比', exact: true });
  const context = page.getByRole('region', { name: '本次调用的上下文', exact: true });
  const baseline = diff.getByRole('textbox', { name: '基准模型记录 ID' });
  const pin = diff.getByRole('button', { name: '使用当前记录为基准', exact: true });
  const select = async id => { await page.getByRole('button', { name: `查看模型记录 ${id}`, exact: true }).click(); await expect(context.locator('.context-record')).toContainText(id); };
  const apply = async id => { await baseline.fill(id); await diff.getByRole('button', { name: '应用基准', exact: true }).click(); };
  const compared = async () => { await expect(diff).toContainText('已读取两条记录的上下文差异'); };
  const identities = diff.locator('.context-comparison-identity');
  await expect(diff).toContainText('尚未设置基准'); await expect(pin).toBeDisabled();
  await select(seed.first); await pin.focus(); await page.keyboard.press('Enter');
  await expect(diff).toContainText('正在比较同一条记录');
  await expect(diff).toContainText('新增 0 个片段 · 移除 0 个片段 · 变化 0 个片段');
  await select(seed.recovery); await compared();
  await expect(baseline).toHaveValue(seed.first);
  await expect(identities).toContainText(seed.first); await expect(identities).toContainText(seed.recovery);
  const budget = diff.locator('.context-field-change[data-field="input_token_limit"]');
  await expect(budget).toContainText('32768'); await expect(budget).toContainText('18719');
  await expect(diff.getByRole('heading', { name: '新增片段 · 2', exact: true })).toBeVisible();
  const capabilities = diff.locator('.context-changed-fragment').filter({ hasText: 'capabilities' });
  await capabilities.locator('summary').focus(); await page.keyboard.press('Enter');
  await expect(capabilities).toHaveAttribute('open', '');
  await expect(capabilities.getByText('skill_registry', { exact: true })).toBeVisible();
  await expect(capabilities.getByText('frozen_skill_catalog', { exact: true })).toBeVisible();
  await expect(context).toContainText('关联与包哈希一致');
  await baseline.fill(seed.recovery);
  await expect(diff).toContainText('输入已修改，应用基准后更新对比');
  await expect(identities.locator('dd').first()).toContainText(seed.first);
  await diff.getByRole('button', { name: '应用基准', exact: true }).click();
  await expect(diff).toContainText('正在比较同一条记录');
  await select(seed.first); await compared();
  await expect(diff.getByRole('heading', { name: '移除片段 · 2', exact: true })).toBeVisible();
  await expect(budget.locator('.context-value-pair > div').first()).toContainText('18719');
  await expect(budget.locator('.context-value-pair > div').last()).toContainText('32768');
  await apply('absent-model-record'); await expect(diff.getByRole('alert')).toContainText('记录不存在');
  await expect(diff.locator('.context-integrity')).toHaveCount(0);
  await apply(seed.first); await select(seed.legacy);
  await expect(diff).toContainText('无法比较上下文证据'); await expect(diff).toContainText('缺少比较所需');
  await expect(diff.locator('.context-field-change')).toHaveCount(0);
  await expect(context).toContainText('没有保存上下文');
  await select(seed.recovery); await compared();
  await stop(); await expect(diff.getByRole('alert')).toBeVisible({ timeout: 15000 });
  await expect(diff).toContainText('数据可能过期，正在自动重连'); await expect(budget).toContainText('18719');
  await apply(seed.legacy); await expect(diff.locator('.context-field-change')).toHaveCount(0);
  await start(); await expect(diff).toContainText('无法比较上下文证据', { timeout: 15000 });
  await expect(diff.getByRole('alert')).toHaveCount(1);
  await apply(seed.first); await compared();
  await stop(); await expect(diff.getByRole('alert')).toBeVisible({ timeout: 15000 });
  await select(seed.first); await expect(diff.locator('.context-field-change')).toHaveCount(0);
  await start(); await expect(diff).toContainText('正在比较同一条记录', { timeout: 15000 });
  await select(seed.recovery); await compared();
  sql(`wire=json.loads((Path(sys.argv[1])/'original-bundle.json').read_text());wire['fragments'][0]['content']='Actual copied-ledger corruption.'
db.execute("UPDATE objects SET data=? WHERE collection='context_bundles' AND id=?",(json.dumps(wire),${JSON.stringify(seed.bundle_id)}));db.commit();print('true')`);
  await expect(diff).toContainText('无法比较上下文证据'); await expect(diff).toContainText('上下文包与保存的哈希不一致');
  await expect(diff.locator('.context-field-change')).toHaveCount(0);
  sql(`wire=(Path(sys.argv[1])/'original-bundle.json').read_text();db.execute("UPDATE objects SET data=? WHERE collection='context_bundles' AND id=?",(wire,${JSON.stringify(seed.bundle_id)}));db.commit();print('true')`);
  await compared();
  await diff.getByRole('button', { name: '清除基准', exact: true }).click();
  await expect(diff).toContainText('尚未设置基准'); await expect(identities).toHaveCount(0);
  await expect(diff.locator('.context-field-change')).toHaveCount(0);
  await apply(seed.first); await compared();
  await capabilities.locator('summary').click(); await expect(capabilities).toHaveAttribute('open', '');
  for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
    await page.setViewportSize({ width, height }); await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(root, `${name}.png`), fullPage: true });
    await diff.screenshot({ path: path.join(root, `${name}-diff.png`) });
    const dimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    if (dimensions.scroll > dimensions.client) throw new Error(`${name} horizontal overflow: ${JSON.stringify(dimensions)}`);
  }
  report.final_ledger_hash = sql(`print(json.dumps(hashlib.sha256('\\n'.join(sorted(db.iterdump())).encode()).hexdigest()))`);
  if (report.final_ledger_hash !== seed.ledger_hash) throw new Error('browser observation altered actual ledger');
  if (report.page_errors.length || report.mutations.length) throw new Error('unexpected browser errors or writes');
  report.status = 'passed'; report.checks = ['actual baseline pin and source disclosure by keyboard', 'self comparison', 'real planning to recovery sources and budget', 'draft baseline does not change active pair', 'reverse comparison', 'missing record error', 'actual legacy evidence unavailable', 'real server disconnect retention', 'baseline and current switch during disconnect clear stale pair', 'real server restart recovery', 'actual copied-ledger hash corruption blocks comparison', 'clear and reapply baseline', 'desktop and mobile no overflow', 'single context panel remains functional', 'no new model calls or browser ledger writes'];
} catch (e) { report.status = 'failed'; report.error = e.stack || String(e); throw e; }
finally { await browser?.close(); await stop(); await writeFile(path.join(root, 'report.json'), JSON.stringify(report, null, 2)); console.log('actual context diff browser report:', path.join(root, 'report.json')); }
