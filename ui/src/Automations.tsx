import { useEffect, useRef, useState } from 'react';
import { Json } from './api';
import { Raw } from './components';

type Props = {
  busy: boolean;
  call: (name: string, args: Json) => Promise<Json>;
  mutation: (name: string, args: Json) => Promise<Json>;
  perform: (label: string, action: () => Promise<void>) => Promise<void>;
};
const statuses: Record<string, string> = { queued: '已排队，等待诊断 worker', running: '正在诊断', completed: '诊断完成',
  failed: '诊断失败', canceled: '已取消诊断', unresolved: '结果未知，未自动重发' };

export function Automations({ busy, call, mutation, perform }: Props) {
  const [robot, setRobot] = useState('r1');
  const [budget, setBudget] = useState('10');
  const [question, setQuestion] = useState('解释实际失败原因，区分记录事实与待核查假设，并引用事件和执行记录。');
  const [rules, setRules] = useState<Json[]>([]);
  const [selected, setSelected] = useState('');
  const [runs, setRuns] = useState<Json[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const read = useRef(call); read.current = call;
  const previousSelection = useRef(selected);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true);
    if (previousSelection.current !== selected) { setRuns([]); previousSelection.current = selected; }
    async function update() {
      try {
        const result = await read.current('automation.list', {});
        if (!active) return;
        setRules(result.items);
        const id = result.items.some((r: Json) => r.id === selected) ? selected : result.items[0]?.id || '';
        if (id !== selected) { setSelected(id); return; }
        const details = id ? await read.current('automation.runs', { automation_id: id }) : { items: [] };
        if (!active) return;
        setRuns(details.items.sort((a: Json, b: Json) => b.created_at - a.created_at)); setError('');
      } catch (e) { if (active) setError(e instanceof Error ? e.message : '诊断记录读取失败，请刷新重试。'); }
      finally { if (active) { setLoading(false); timer = setTimeout(update, 2500); } }
    }
    void update();
    return () => { active = false; clearTimeout(timer); };
  }, [selected, refresh]);
  const rule = rules.find(r => r.id === selected);
  const count = Number(budget);
  const validBudget = Number.isInteger(count) && count >= 1 && count <= 100;
  return <section className="panel workbench-automations" aria-label="失败事件自动诊断">
    <h2>失败事件自动诊断</h2>
    <p>为新发生的执行失败生成模型解释。诊断保留事件引用，不会执行恢复计划或改变任务状态。</p>
    <div className="workbench-automation-columns">
      <form onSubmit={e => { e.preventDefault(); void perform('创建失败诊断规则', async () => {
        const result = await mutation('automation.create', { robot_id: robot.trim(), max_runs: count, question: question.trim() });
        setSelected(result.automation.id); setRefresh(n => n + 1);
      }); }}>
        <h3>创建诊断规则</h3>
        <label htmlFor="automation-robot">诊断机器人范围</label>
        <input id="automation-robot" value={robot} required maxLength={512} disabled={busy} onChange={e => setRobot(e.target.value)} />
        <label htmlFor="automation-budget">累计诊断次数上限</label>
        <input id="automation-budget" type="number" min={1} max={100} step={1} value={budget} required disabled={busy}
          aria-describedby="automation-budget-help" onChange={e => setBudget(e.target.value)} />
        <p id="automation-budget-help">1–100 次。每次入队占用一次额度，失败、取消和重新诊断也计入。</p>
        <label htmlFor="automation-question">诊断问题</label>
        <textarea id="automation-question" rows={4} maxLength={16000} required value={question} disabled={busy} onChange={e => setQuestion(e.target.value)} />
        <button disabled={busy || !robot.trim() || !question.trim() || !validBudget}>创建并启用规则</button>
        <p>仅处理创建后的新事件。保存规则不调用模型；独立诊断 worker 消费队列时才会调用。</p>
      </form>
      <div>
        <div className="workbench-buttons"><h3>规则与诊断记录</h3><button disabled={busy} onClick={() => setRefresh(n => n + 1)}>刷新诊断记录</button></div>
        {error && <p role="alert">{error}。可刷新重试；下面保留上次成功读取的记录。</p>}
        {loading && <p role="status">正在读取诊断记录…</p>}
        {!loading && !rules.length && !error && <p className="workbench-empty">尚未创建诊断规则。</p>}
        {!!rules.length && <>
          <label htmlFor="automation-rule">选择诊断规则</label>
          <select id="automation-rule" value={selected} onChange={e => setSelected(e.target.value)}>{rules.map(r =>
            <option key={r.id} value={r.id}>{r.robot_id} · {r.enabled ? '已启用' : '已暂停'} · {r.enqueued}/{r.max_runs} 次 · {r.id.slice(0, 8)}</option>)}</select>
        </>}
        {rule && <>
          <p aria-live="polite"><strong>{rule.enabled ? '规则已启用' : '规则已暂停'}</strong> · 已入队 {rule.enqueued} / {rule.max_runs} 次</p>
          <p>{rule.question}</p>
          <button disabled={busy || !!error} onClick={() => void perform('更新诊断规则', async () => {
            await mutation('automation.set-enabled', { automation_id: rule.id, expected_revision: rule.revision, enabled: !rule.enabled });
            setRefresh(n => n + 1);
          })}>{rule.enabled ? '暂停规则' : '启用规则'}</button>
          <p>暂停期间的事件不补跑。已发送的模型请求可能继续返回。</p>
          {rule.enqueued >= rule.max_runs && <p role="status">额度已用完，不会再为此规则创建诊断。</p>}
          {!loading && !error && !runs.length && <p className="workbench-empty">暂无诊断记录，等待范围内的新失败事件。</p>}
          <ol className="workbench-automation-runs">{runs.filter(run => run.automation_id === selected).map(run => <li key={run.id}>
            <strong>{statuses[run.status] || run.status}</strong>
            <p>事件 {run.event.seq} · 任务 <code>{run.event.task}</code></p>
            {run.error && <p>{run.error}</p>}
            {run.result && <><p>{run.result.explanation.summary}</p>
              <details><summary>已记录错误与引用</summary><p>{run.result.explanation.observed_error}</p>
                <ul>{run.result.explanation.record_refs.map((ref: string) => <li key={ref}><code>{ref}</code></li>)}</ul>
                {!!run.result.explanation.unknowns.length && <><p>仍需核查</p><ul>{run.result.explanation.unknowns.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul></>}
              </details><p>模型解释，不是执行成功证据。</p></>}
            {run.retry_of && <p>重新诊断来源：<code>{run.retry_of}</code></p>}
            {['failed', 'unresolved'].includes(run.status) && <>
              {run.status === 'unresolved' && <p>无法确认上次请求是否已由模型服务处理。再次诊断会发出新请求并消耗额度，原记录保持未知。</p>}
              <button disabled={busy || !!error || !rule.enabled || rule.enqueued >= rule.max_runs} onClick={() => void perform('重新排队诊断', async () => {
                await mutation('automation.retry', { run_id: run.id, expected_status: run.status }); setRefresh(n => n + 1);
              })}>重新诊断此事件</button>
            </>}
            <Raw value={run} label="诊断来源与模型记录" />
          </li>)}</ol>
        </>}
      </div>
    </div>
  </section>;
}
