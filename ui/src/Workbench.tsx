import { useEffect, useRef, useState } from 'react';
import { Raw } from './components';
import { Automations } from './Automations';
import { SessionHistory } from './SessionHistory';
import { TaskEvents } from './TaskEvents';
import { Json } from './api';
import './workbench.css';

export type TaskSelection = { task_id: string; task_revision: number; task_generation: number; step_ids: string[]; robot_id: string };

const commandLabels: Record<string, string> = { accepted: '请求已接受，等待 worker', applied: '控制命令已应用，请查看任务实际状态', rejected: '命令被拒绝' };
class ActionRequestError extends Error {
  constructor(message: string, readonly definitive: boolean) { super(message); }
}

export function Workbench({ selection }: { selection?: TaskSelection }) {
  const [token, setToken] = useState('');
  const [connected, setConnected] = useState(false);
  const [automationAccess, setAutomationAccess] = useState(false);
  const [eventsAccess, setEventsAccess] = useState(false);
  const [robot, setRobot] = useState('r1');
  const [goal, setGoal] = useState('');
  const [message, setMessage] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [session, setSession] = useState<Json>();
  const [draft, setDraft] = useState<Json>();
  const [receipt, setReceipt] = useState<Json>();
  const [task, setTask] = useState<Json>();
  const [explanation, setExplanation] = useState<Json>();
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const [memoryQuery, setMemoryQuery] = useState('');
  const [memoryResults, setMemoryResults] = useState<Json[] | undefined>();
  const [memorySelection, setMemorySelection] = useState<string[]>([]);
  const pending = useRef<{ name: string; args: Json; key: string } | undefined>(undefined);

  useEffect(() => {
    setMemoryQuery(''); setMemoryResults(undefined); setMemorySelection([]); setExplanation(undefined);
  }, [session?.id]);

  async function call(name: string, args: Json, key?: string) {
    const response = await fetch(`/actions/${name}`, { method: 'POST', headers: {
      'Content-Type': 'application/json', Authorization: `Bearer ${token}`,
      ...(key ? { 'Idempotency-Key': key } : {}),
    }, body: JSON.stringify(args) });
    const body = await response.json();
    if (!response.ok) throw new ActionRequestError(`${body.error?.code || response.status}：${body.error?.message || '请求未完成'}`, response.status < 500);
    return body.result as Json;
  }

  async function mutation(name: string, args: Json) {
    const signature = JSON.stringify({ name, args });
    if (!pending.current || JSON.stringify({ name: pending.current.name, args: pending.current.args }) !== signature) {
      pending.current = { name, args, key: crypto.randomUUID() };
    }
    try {
      const result = await call(name, args, pending.current.key);
      pending.current = undefined;
      return result;
    } catch (e) {
      if (e instanceof ActionRequestError && e.definitive) pending.current = undefined;
      throw e;
    }
  }

  async function perform(label: string, action: () => Promise<void>) {
    setBusy(label); setError('');
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : '操作失败'); }
    finally { setBusy(''); }
  }

  useEffect(() => {
    if (!receipt || !connected) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const next = await call('command.get', { command_id: receipt.command_id });
        if (!active) return;
        setReceipt(next);
        if (next.status === 'applied') {
          const result = await call('task.get', { task_id: next.task_id });
          if (active) setTask(result.task);
        }
        if (active) setPollError('');
      } catch (e) { if (active) setPollError(e instanceof Error ? e.message : '状态读取失败'); }
      finally { if (active) timer = setTimeout(refresh, 2000); }
    };
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  // Poll only reads the receipt and ledger. No automatic model calls or mutation retries.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [receipt?.command_id, connected, token]);

  const version = session ? { session_id: session.id, expected_revision: session.revision } : undefined;
  const analysis = session?.analysis;
  const canPlan = analysis && (analysis.status === 'ready' || (analysis.status === 'needs_grounding' && analysis.goal_context.grounding_requests.length > 0 && !analysis.questions.length));

  return <section className="workbench" aria-label="任务协作工作台">
    <div className="page-intro compact"><div><h1>任务协作</h1><p>完善目标、检查计划，再交给执行端。模型回答和控制回执分别留痕。</p></div></div>
    <form className="workbench-connection" onSubmit={e => { e.preventDefault(); void perform('连接应用服务', async () => {
      const response = await fetch('/actions', { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error('应用服务连接失败。请检查服务地址和操作凭据。');
      const body = await response.json();
      if (!body.actions) throw new Error('当前地址未提供应用动作服务。');
      setAutomationAccess(Boolean(body.actions['automation.create']));
      setEventsAccess(Boolean(body.actions['task.events-page']));
      setConnected(true);
    }); }}>
      <label>应用操作凭据<input type="password" autoComplete="off" value={token} onChange={e => { setToken(e.target.value); setConnected(false); }} required placeholder="服务端配置的操作凭据，不是模型 API Key" /></label>
      <button disabled={!!busy || !token}>{connected ? '重新连接' : '连接'}</button>
      <span role="status">{connected ? '应用服务已连接' : '尚未连接应用服务'}</span>
    </form>
    {error && <p className="workbench-error" role="alert">{error}</p>}
    {busy && <p role="status" className="workbench-status">{busy}…</p>}
    <div className="workbench-columns">
      <section className="panel workbench-session" aria-label="目标与会话">
        <h2>目标与上下文</h2>
        {!session ? <>
          <label>机器人命名空间<input value={robot} onChange={e => setRobot(e.target.value)} disabled={!!busy} /></label>
          <label htmlFor="workbench-goal">任务目标</label><textarea id="workbench-goal" rows={5} value={goal} onChange={e => setGoal(e.target.value)} placeholder="描述目标、操作对象和完成标准" disabled={!!busy} />
          <button disabled={!connected || !!busy || !goal.trim() || !robot.trim()} onClick={() => void perform('创建目标会话', async () => {
            const result = await mutation('session.create', { robot_id: robot, goal }); setSession(result.session); setDraft(undefined); setReceipt(undefined); setTask(undefined);
          })}>创建会话</button>
          <div className="workbench-resume"><label>恢复已有会话<input value={sessionId} onChange={e => setSessionId(e.target.value)} placeholder="会话 ID" /></label><button disabled={!connected || !!busy || !sessionId} onClick={() => void perform('读取会话', async () => { const result = await call('session.get', { session_id: sessionId }); setSession(result.session); setDraft(result.drafts?.filter((item: Json) => item.session_revision === result.session.revision).at(-1)); })}>读取会话</button></div>
        </> : <>
          <p className="muted">{session.robot_id} · 会话版本 {session.revision}</p><code>{session.id}</code>
          <button className="text-button" disabled={!connected || !!busy} onClick={() => void perform('刷新会话状态', async () => { const result = await call('session.get', { session_id: session.id }); setSession(result.session); setDraft(result.drafts?.filter((item: Json) => item.session_revision === result.session.revision).at(-1)); })}>刷新会话</button>
          <div className="workbench-turns">{session.turns.map((turn: Json) => <article key={turn.id}><strong>{turn.role === 'user' ? '操作员' : '目标分析'}</strong><p>{turn.content}</p></article>)}</div>
          <SessionHistory key={session.id} session={session} connected={connected} busy={!!busy}
            call={call} mutation={mutation} perform={perform} onUpdated={next => {
              setSession(next); setDraft(undefined); setExplanation(undefined);
            }} />
          <section className="workbench-memory" aria-label="会话记忆">
            <h3>参考记忆</h3>
            <p>仅检索 {session.robot_id} 范围内的有效记忆。来源文件完整性已核验，文字记录仍需结合实际情况判断。</p>
            <p role="status">当前已绑定 {session.memory_bindings?.length || 0} 条记忆</p>
            {!!session.memory_bindings?.length && <>
              <Raw value={session.memory_bindings} label="当前记忆引用与版本" />
              <button disabled={!connected || !!busy} onClick={() => void perform('清除会话记忆', async () => {
                const result = await mutation('session.attach-memories', { ...version, memories: [] });
                setSession(result.session); setDraft(undefined); setExplanation(undefined); setMemorySelection([]);
              })}>清除绑定记忆</button>
            </>}
            <form onSubmit={e => { e.preventDefault(); void perform('检索有效记忆', async () => {
              setMemoryResults(undefined); setMemorySelection([]);
              const result = await call('memory.search', { text: memoryQuery.trim(), robot_id: session.robot_id, limit: 10 });
              setMemoryResults(result.items);
            }); }}>
              <label>记忆关键词<input value={memoryQuery} onChange={e => setMemoryQuery(e.target.value)} disabled={!!busy} placeholder="输入记录中的词语" /></label>
              <button disabled={!connected || !!busy || !memoryQuery.trim()}>检索记忆</button>
            </form>
            {memoryResults && <>
              <p role="status">{memoryResults.length ? `找到 ${memoryResults.length} 条记忆，已选 ${memorySelection.length} 条` : '未找到有效记忆，请调整关键词。'}</p>
              <ul className="workbench-memory-results">{memoryResults.map(item => <li key={item.memory.id}>
                <label className="workbench-memory-choice"><input type="checkbox" checked={memorySelection.includes(item.memory.id)} disabled={!connected || !!busy}
                  onChange={e => setMemorySelection(current => e.target.checked ? [...current, item.memory.id] : current.filter(id => id !== item.memory.id))} />
                  <span>{item.memory.text.slice(0, 240)}{item.memory.text.length > 240 ? '…' : ''}</span>
                </label>
                <p className="muted">{item.memory.kind} · 来源文件 {item.verified_assets.length} 个 · {item.memory.valid_until == null ? '未设置失效时间' : `有效至 ${new Date(item.memory.valid_until * 1000).toLocaleString()}`}</p>
                <Raw value={item} label="完整记忆与来源文件" />
              </li>)}</ul>
              {!!memoryResults.length && <>
                <p>所选记忆将替换当前绑定，并使已有目标分析和计划草稿失效。</p>
                <button disabled={!connected || !!busy || !memorySelection.length} onClick={() => void perform('绑定所选记忆', async () => {
                  const memories = memoryResults.filter(item => memorySelection.includes(item.memory.id)).map(item => ({ memory_id: item.memory.id, record_hash: item.record_hash }));
                  const result = await mutation('session.attach-memories', { ...version, memories });
                  setSession(result.session); setDraft(undefined); setExplanation(undefined); setMemorySelection([]);
                })}>使用所选记忆</button>
              </>}
            </>}
          </section>
          {selection && <div className="workbench-selection"><p>已从任务图选中：<code>{selection.task_id}</code> / {selection.step_ids.join('、') || '整个任务'}</p><button disabled={!!busy || !connected || session.robot_id !== selection.robot_id} onClick={() => void perform('关联任务上下文', async () => {
            const { robot_id: _robot, ...snapshot } = selection;
            const result = await mutation('selection.set', { ...version, ...snapshot }); setSession(result.session); setDraft(undefined);
          })}>将所选节点加入上下文</button>{session.robot_id !== selection.robot_id && <p>会话和任务的机器人范围不同。</p>}</div>}
          <label>补充条件或回答问题<textarea rows={3} value={message} onChange={e => setMessage(e.target.value)} disabled={!!busy} /></label>
          <div className="workbench-buttons"><button disabled={!connected || !!busy || !message.trim()} onClick={() => void perform('保存补充信息', async () => { const result = await mutation('session.message', { ...version, content: message }); setSession(result.session); setMessage(''); setDraft(undefined); })}>保存补充信息</button>
            <button disabled={!connected || !!busy} onClick={() => void perform('调用真实模型分析目标', async () => { const result = await mutation('goal.analyze', version!); setSession(result.session); setDraft(undefined); })}>分析当前目标</button></div>
          {session.selection?.step_ids.length > 0 && <><button disabled={!connected || !!busy} onClick={() => void perform('读取实际记录并调用模型解释', async () => {
            setExplanation(await mutation('task.explain', { ...version, question: message.trim() || '根据所选节点的实际记录解释发生了什么，指出失败原因、已有证据和仍未知的信息。' }));
          })}>解释所选节点</button>{explanation && <div className="workbench-analysis"><strong>模型解释 · 依据所选账本记录</strong><p>{explanation.explanation.summary}</p>{explanation.explanation.unknowns.map((s: string) => <p key={s}>尚不确定：{s}</p>)}<Raw value={explanation} label="引用记录与原始执行结果" /></div>}</>}
          {analysis && <div className="workbench-analysis"><p><strong>{analysis.status === 'ready' ? '目标信息已明确' : analysis.status === 'needs_clarification' ? '需要补充信息' : '需要执行取证'}</strong></p>
            {analysis.questions.map((q: Json) => <p key={q.field}>{q.question}<small>{q.reason}</small></p>)}
            {analysis.goal_context.grounding_requests.map((s: string) => <p key={s}>待取证：{s}</p>)}
            <Raw value={analysis} label="目标分析与模型记录引用" />
          </div>}
          <button className="text-button" disabled={!!busy} onClick={() => { setSession(undefined); setGoal(''); setMessage(''); setSessionId(''); setDraft(undefined); setReceipt(undefined); setTask(undefined); setError(''); pending.current = undefined; }}>开始另一会话</button>
        </>}
      </section>
      <section className="panel workbench-plan" aria-label="计划和执行">
        <h2>计划与执行</h2><p>模型调用由按钮触发。生成计划不会执行任务。</p>
        <button disabled={!connected || !!busy || !canPlan} onClick={() => void perform('调用真实模型生成计划', async () => { const result = await mutation('plan.propose', version!); setDraft(result.draft); if (result.session) setSession(result.session); })}>生成计划草稿</button>
        {draft ? <>
          <ol className="workbench-steps">{draft.plan.steps.map((step: Json) => <li key={step.id}><strong>{step.id}</strong><code>{step.skill}</code><p>依赖：{step.deps?.join('、') || '无'}</p><Raw value={step.args} label="参数" /></li>)}</ol>
          <p>最终验证节点：<code>{draft.plan.verification}</code></p>
          <Raw value={draft} label="草稿版本、哈希与模型证据" />
          <button disabled={!connected || !!busy || draft.session_revision !== session?.revision} onClick={() => void perform('提交当前计划', async () => { setReceipt(await mutation('plan.submit', { ...version, draft_id: draft.id, plan_hash: draft.plan_hash })); })}>{draft.task_id ? '提交修订计划' : '提交当前计划'}</button>
        </> : <p className="workbench-empty">目标分析完成后可生成草稿。待取证内容会保留在规划上下文中。</p>}
        {receipt && <div className="workbench-result" aria-live="polite"><p><strong>{commandLabels[receipt.status] || receipt.status}</strong></p><code>{receipt.task_id}</code>{receipt.error && <p role="alert">{receipt.error.message}</p>}
          {pollError && <p role="alert">{pollError}。下面保留上次成功读取的数据。</p>}
          {task && <><p>任务实际状态：<strong>{task.status}</strong> · 计划 v{task.revision}</p><div className="workbench-buttons">{(['pause', 'cancel', 'resume'] as const).map(mode => <button key={mode} disabled={!connected || !!busy || ['succeeded', 'failed', 'canceled'].includes(task.status) || (mode === 'resume' && task.status !== 'paused')} onClick={() => void perform('提交控制请求', async () => {
            setReceipt(await mutation(`task.${mode}`, { task_id: task.id, expected_revision: task.revision, expected_generation: task.generation }));
          })}>{mode === 'pause' ? '请求暂停' : mode === 'cancel' ? '请求取消' : '请求恢复'}</button>)}</div><Raw value={task.steps} label="实际步骤结果与停止证据" /></>}
        </div>}
      </section>
    </div>
    {connected && eventsAccess && <TaskEvents call={call} suggestedTaskId={task?.id || selection?.task_id} />}
    {connected && automationAccess && <Automations busy={!!busy} call={call} mutation={mutation} perform={perform} />}
  </section>;
}
