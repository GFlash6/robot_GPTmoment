import { chromium, expect } from '@playwright/test';
import { spawn, execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const project = path.resolve(import.meta.dirname, '../..');
const python = path.join(project, '.venv/bin/python');
const root = path.join(project, '.runtime/context-browser-validation', randomUUID());
await mkdir(path.join(root, 'ledger'), { recursive: true });
const sql = code => JSON.parse(execFileSync(python, ['-c', `import json,sqlite3,sys,hashlib\nfrom pathlib import Path\ndb=sqlite3.connect(Path(sys.argv[1])/'ledger/ledger.sqlite')\n${code}\ndb.close()`, root], { cwd: project, encoding: 'utf8' }));
const seed = sql(`source=Path('.runtime/session-summary-validation/c5f8cb4e-15b9-4722-9220-117a16ab4009/ledger/ledger.sqlite').resolve()
origin=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);origin.backup(db);origin.close()
legacy_source=Path('.runtime/memory-validation/83872251-288f-402a-b821-592ce3297033/ledger/ledger.sqlite').resolve()
origin=sqlite3.connect(legacy_source.as_uri()+'?mode=ro',uri=True)
legacy=next(json.loads(r[0]) for r in origin.execute("SELECT data FROM objects WHERE collection='model_responses'") if not json.loads(r[0]).get('context_bundle_id') and not json.loads(r[0]).get('context_manifest_id'))
origin.close();assert legacy['raw'] and legacy['response_id']
db.execute('INSERT INTO objects VALUES(?,?,?)',('model_responses',legacy['id'],json.dumps(legacy,ensure_ascii=False,sort_keys=True)));db.commit()
records=[json.loads(r[0]) for r in db.execute("SELECT data FROM objects WHERE collection='model_responses'")]
summary=min((r for r in records if r['method']=='session_summary'),key=lambda r:r['chunk_index'])
goal=next(r for r in records if r['method']=='goal_analysis' and r.get('context_bundle_id'))
wire=db.execute("SELECT data FROM objects WHERE collection='context_bundles' AND id=?",(summary['context_bundle_id'],)).fetchone()[0]
(Path(sys.argv[1])/'original-bundle.json').write_text(wire)
print(json.dumps({'summary':summary['id'],'goal':goal['id'],'legacy':legacy['id'],'bundle_id':summary['context_bundle_id'],'source':str(source),'legacy_source':str(legacy_source),'models':len(records),'ledger_hash':hashlib.sha256('\\n'.join(sorted(db.iterdump())).encode()).hexdigest()}))`);
let server, browser;
const start = async () => {
  server = spawn(python, ['-m', 'robot_agent_observer.server', '--root', path.join(root, 'ledger'), '--static', path.join(project, 'ui/dist'), '--port', '18774'], { cwd: project, stdio: ['ignore', 'ignore', 'pipe'] });
  let errors = ''; server.stderr.on('data', b => { errors += b; });
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error(errors);
    try { if ((await fetch('http://127.0.0.1:18774/api/v1/overview')).ok) return; } catch {}
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
  await page.goto('http://127.0.0.1:18774');
  await page.getByRole('button', { name: '模型记录', exact: true }).click();
  const context = page.getByRole('region', { name: '本次调用的上下文' });
  await expect(context).toContainText('选择上方一条模型记录');
  const select = async id => { await page.getByRole('button', { name: `查看模型记录 ${id}`, exact: true }).click(); await expect(context.locator('.context-record')).toContainText(id); };
  await select(seed.summary); await expect(context).toContainText('关联与包哈希一致');
  const disclosure = context.locator('.context-fragment > summary').first();
  await disclosure.focus(); await page.keyboard.press('Enter');
  await expect(context.locator('.context-fragment').first()).toHaveAttribute('open', '');
  await expect(context.locator('.context-fragment pre').first()).toContainText('original_goal');
  await select(seed.goal); await expect(context).toContainText('关联与包哈希一致');
  await expect(context.locator('.context-fragment > summary').first()).toContainText('goal');
  await expect(context).not.toContainText('summary-source');
  await select(seed.legacy); await expect(context).toContainText('没有保存上下文');
  await expect(context.locator('.context-fragment')).toHaveCount(0);
  await select(seed.summary); await expect(context).toContainText('关联与包哈希一致');
  await stop(); await expect(context.getByRole('alert')).toBeVisible({ timeout: 15000 });
  await expect(context).toContainText('summary-source');
  await select(seed.legacy); await expect(context.locator('.context-fragment')).toHaveCount(0);
  await start(); await expect(context).toContainText('没有保存上下文', { timeout: 15000 });
  await expect(context.getByRole('alert')).toHaveCount(0);
  await select(seed.summary); await expect(context).toContainText('关联与包哈希一致');
  sql(`wire=json.loads((Path(sys.argv[1])/'original-bundle.json').read_text());wire['fragments'][0]['content']['turns'][0]['content']+='\\nCopied ledger corruption.'
db.execute("UPDATE objects SET data=? WHERE collection='context_bundles' AND id=?",(json.dumps(wire),${JSON.stringify(seed.bundle_id)}));db.commit();print('true')`);
  await expect(context).toContainText('上下文证据不一致'); await expect(context).toContainText('上下文包与保存的哈希不一致');
  sql(`wire=(Path(sys.argv[1])/'original-bundle.json').read_text();db.execute("UPDATE objects SET data=? WHERE collection='context_bundles' AND id=?",(wire,${JSON.stringify(seed.bundle_id)}));db.commit();print('true')`);
  await expect(context).toContainText('关联与包哈希一致');
  await context.locator('.context-fragment > summary').first().click();
  for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
    await page.setViewportSize({ width, height }); await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(root, `${name}.png`), fullPage: true });
    await context.screenshot({ path: path.join(root, `${name}-context.png`) });
    const dimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    if (dimensions.scroll > dimensions.client) throw new Error(`${name} horizontal overflow: ${JSON.stringify(dimensions)}`);
  }
  report.final_ledger_hash = sql(`print(json.dumps(hashlib.sha256('\\n'.join(sorted(db.iterdump())).encode()).hexdigest()))`);
  if (report.final_ledger_hash !== seed.ledger_hash) throw new Error('browser observation altered actual ledger');
  if (report.page_errors.length || report.mutations.length) throw new Error('unexpected browser errors or writes');
  report.status = 'passed'; report.checks = ['actual context disclosure by keyboard', 'model switch isolation', 'actual legacy empty state', 'server disconnect retention', 'switch while disconnected clears old data', 'server restart recovery', 'actual copied-ledger hash corruption', 'desktop and mobile no overflow', 'no new model calls or ledger writes'];
} catch (e) { report.status = 'failed'; report.error = e.stack || String(e); throw e; }
finally { await browser?.close(); await stop(); await writeFile(path.join(root, 'report.json'), JSON.stringify(report, null, 2)); console.log('actual context browser report:', path.join(root, 'report.json')); }
