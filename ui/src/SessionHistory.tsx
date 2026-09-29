import { useEffect, useState } from 'react';
import { Json } from './api';
import { Raw } from './components';

type Props = {
  session: Json; connected: boolean; busy: boolean;
  call: (name: string, args: Json) => Promise<Json>;
  mutation: (name: string, args: Json) => Promise<Json>;
  perform: (label: string, action: () => Promise<void>) => Promise<void>;
  onUpdated: (session: Json) => void;
};

export function SessionHistory({ session, connected, busy, call, mutation, perform, onUpdated }: Props) {
  const [automatic, setAutomatic] = useState(false);
  const [recent, setRecent] = useState('6');
  const [pinned, setPinned] = useState<string[]>([]);
  const [dirty, setDirty] = useState(false);
  const [summary, setSummary] = useState<Json>();
  const [summaryError, setSummaryError] = useState('');
  const [loading, setLoading] = useState(false);
  const policySignature = JSON.stringify(session.context_policy || {});
  const summaryId = session.history_summary?.id;
  useEffect(() => {
    const policy = JSON.parse(policySignature);
    setAutomatic(policy.auto_summary || false);
    setRecent(String(policy.keep_recent ?? 6));
    setPinned(policy.pinned_turn_ids || []);
    setDirty(false);
  }, [policySignature]);
  useEffect(() => {
    let active = true;
    setSummary(undefined); setSummaryError(''); setLoading(false);
    if (!connected || !summaryId) return;
    setLoading(true);
    void call('session.get', { session_id: session.id }).then(result => {
      if (!active) return;
      if (result.session.history_summary?.id !== summaryId) {
        setSummaryError('会话已更新，请刷新会话后查看摘要。'); return;
      }
      setSummary(result.summary || undefined);
      setSummaryError(result.summary_error || '');
    }).catch(e => { if (active) setSummaryError(e instanceof Error ? e.message : '摘要读取失败，请刷新会话重试。'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  // Read only when identity, revision or credentials change; no model call on mount.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, connected]);
  useEffect(() => {
    if (summary && !dirty && !session.context_policy) {
      setRecent(String(summary.keep_recent)); setPinned(summary.pinned_turn_ids);
    }
  }, [summary, dirty, session.context_policy]);

  const keepRecent = Number(recent);
  const validRecent = Number.isInteger(keepRecent) && keepRecent >= 2 && keepRecent <= 32;
  const canSummarize = validRecent && session.turns.slice(0, -keepRecent).some((t: Json) => !pinned.includes(t.id));
  const version = { session_id: session.id, expected_revision: session.revision };
  const disabled = !connected || busy;

  return <section className="workbench-history" aria-label="历史摘要与预算">
    <h3>历史摘要与预算</h3>
    <p>保留原始记录，整理较早的历史。重要约束可指定保留原文，摘要不能作为执行成功的证据。</p>
    <label className="workbench-history-choice"><input type="checkbox" checked={automatic} disabled={disabled}
      onChange={e => { setAutomatic(e.target.checked); setDirty(true); }} /><span>分析或规划超预算时自动摘要</span></label>
    <label htmlFor="history-recent">近期保留原文的消息数</label>
    <input id="history-recent" className="workbench-history-number" type="number" min={2} max={32} step={1}
      value={recent} disabled={disabled} aria-describedby="history-recent-help"
      onChange={e => { setRecent(e.target.value); setDirty(true); }} />
    <p id="history-recent-help" className="workbench-history-note">可设为 2–32 条，同时保留所有指定消息。超预算且无法缩减时会停止调用。</p>
    <details className="workbench-history-pins"><summary>选择必须保留原文的消息（已选 {pinned.length} 条）</summary>
      <div className="workbench-history-pin-list">{session.turns.map((turn: Json, index: number) => <label key={turn.id} className="workbench-history-choice">
        <input type="checkbox" aria-label={`保留第 ${index + 1} 条消息原文`} checked={pinned.includes(turn.id)}
          disabled={disabled || (!pinned.includes(turn.id) && pinned.length >= 64)} onChange={e => {
            setPinned(current => e.target.checked ? [...current, turn.id] : current.filter(id => id !== turn.id)); setDirty(true);
          }} /><span><strong>第 {index + 1} 条 · {turn.role === 'user' ? '操作员' : '目标分析'}</strong>{turn.content.slice(0, 160)}{turn.content.length > 160 ? '…' : ''}</span>
      </label>)}</div>
    </details>
    <p role="status" className="workbench-history-note">{dirty ? '策略有未保存修改。保存会使旧目标分析和计划草稿失效。' : '当前策略已同步。保存策略不调用模型。'}</p>
    <div className="workbench-buttons">
      <button disabled={disabled || !validRecent || (!dirty && !!session.context_policy)} onClick={() => void perform('保存历史上下文策略', async () => {
        const result = await mutation('session.context-policy', { ...version, auto_summary: automatic, keep_recent: keepRecent, pinned_turn_ids: pinned });
        onUpdated(result.session); setDirty(false);
      })}>保存摘要策略</button>
      <button disabled={disabled || dirty || loading || !canSummarize} onClick={() => void perform('调用真实模型整理历史', async () => {
        const result = await mutation('session.summarize', { ...version, keep_recent: keepRecent, pinned_turn_ids: pinned });
        onUpdated(result.session); setSummary(result.summary);
      })}>立即生成历史摘要</button>
    </div>
    {!canSummarize && validRecent && <p className="workbench-history-note">当前没有可整理的较早消息；近期消息和指定消息保留原文。</p>}
    {loading && <p role="status">正在读取已保存的摘要…</p>}
    {summaryError && <p role="alert">摘要暂不可用：{summaryError}。原始消息仍保留，可检查后重新生成摘要。</p>}
    {summary ? <div className="workbench-history-summary">
      <h4>当前历史摘要 · 模型整理</h4>
      <p>覆盖 {summary.covered_turns.length} 条较早消息；未覆盖的消息仍以原文进入上下文。</p>
      <ol>{summary.points.map((point: Json, index: number) => <li key={index}>
        <p>{point.text}</p>
        <details><summary>查看引用原文（{point.turn_ids.length} 条）</summary>
          {point.turn_ids.map((id: string) => {
            const turn = session.turns.find((t: Json) => t.id === id);
            return <article key={id}><code>{id}</code><p className="workbench-history-source">{turn?.content || '原文不可用，请刷新会话。'}</p></article>;
          })}
        </details>
      </li>)}</ol>
      <Raw value={summary} label="摘要版本、覆盖范围和模型记录" />
    </div> : !loading && !summaryError && <p className="workbench-history-note">{summaryId && !connected ? '连接应用服务后可读取摘要。' : '尚未生成历史摘要。'}</p>}
  </section>;
}
