import { useState } from 'react';
import { Json, stamp, useQuery } from './api';
import { Notice, Raw } from './components';
import { contextIssueLabels } from './ModelContext';
import './model-context-diff.css';

const fields: Record<string, string> = {
  source: '来源', content_sha256: '内容哈希', authority: '权限层级', required: '是否必需',
  priority: '优先级', evidence_ids: '证据标识', metadata: '元数据', allocation: '纳入与丢弃',
  phase: '调用阶段', request_id: '请求 ID', robot_id: '机器人', session_id: '会话',
  task_id: '任务', revision: '任务版本', generation: '控制代次', context_snapshot_id: '上下文快照',
  goal: '目标', estimated_input_tokens: '输入估算', input_token_limit: '输入上限',
  reserved_output_tokens: '输出预留', estimator: '估算方式', renderer_version: '提示渲染版本',
};
const issues: Record<string, string> = { ...contextIssueLabels,
  missing_comparison_evidence: '缺少比较所需的上下文包或清单', invalid_request_shape: '请求身份格式无法比较',
  invalid_fragment_shape: '来源片段格式无法比较', duplicate_fragment_ids: '来源片段标识重复',
  invalid_included_shape: '纳入清单格式无法比较', invalid_dropped_shape: '丢弃清单格式无法比较',
  ambiguous_fragment_allocation: '纳入与丢弃清单不能唯一对应全部片段',
};
const rows = (value: unknown): Json[] => Array.isArray(value) ? value : [];
const label = (field: string) => fields[field] || field;

function Value({ value, present }: { value: unknown; present: boolean }) {
  if (!present) return <p>字段未记录</p>;
  if (value === null) return <p><code>null</code>（已记录）</p>;
  return typeof value === 'object' ? <pre>{JSON.stringify(value, null, 2)}</pre> : <p>{String(value)}</p>;
}

function FieldChange({ change }: { change: Json }) {
  return <div className="context-field-change" data-field={change.field}>
    <strong>{label(change.field)}</strong>
    <div className="context-value-pair">
      <div><span>基准</span><Value value={change.before} present={change.before_present}/></div>
      <div><span>当前</span><Value value={change.after} present={change.after_present}/></div>
    </div>
  </div>;
}

function FragmentList({ items, title }: { items: Json[]; title: string }) {
  return <>
    <h3>{title} · {items.length}</h3>
    {items.length ? items.map(item => <details className="context-fragment" key={item.id}>
      <summary><span><code>{item.id}</code> · {item.allocation?.status === 'included' ? '已纳入' : '未纳入'}</span><span>{item.source}</span></summary>
      <Raw value={item} label="来源、内容哈希与分配记录"/>
    </details>) : <p>没有{title}。</p>}
  </>;
}

export function ModelContextDiff({ recordId }: { recordId?: string }) {
  const [baseline, setBaseline] = useState('');
  const [draft, setDraft] = useState('');
  const result = useQuery<Json>(recordId && baseline ? `/models/${encodeURIComponent(recordId)}/context-diff?against=${encodeURIComponent(baseline)}` : null);
  const data = result.data?.before?.model_record_id === baseline && result.data?.after?.model_record_id === recordId ? result.data : undefined;
  const delta = data?.status === 'compared' ? data.changes : undefined;
  const fragments = delta?.fragments;
  const budget = rows(delta?.manifest).filter(change => ['estimated_input_tokens', 'input_token_limit', 'reserved_output_tokens', 'estimator', 'renderer_version'].includes(change.field));
  const pin = (id: string) => { setBaseline(id); setDraft(id); };
  return <section className="panel model-context model-context-diff" aria-labelledby="context-diff-title">
    <h2 id="context-diff-title">上下文对比</h2>
    <p id="context-diff-help">将一条记录设为基准，再从上方列表选择当前记录；也可以粘贴其他页的模型记录 ID。</p>
    <form onSubmit={event => { event.preventDefault(); setBaseline(draft.trim()); }}>
      <label htmlFor="context-baseline">基准模型记录 ID</label>
      <input id="context-baseline" value={draft} onChange={event => setDraft(event.target.value)} aria-describedby="context-diff-help" autoComplete="off" spellCheck={false}/>
      <div className="context-diff-actions">
        <button type="submit" disabled={!draft.trim()}>应用基准</button>
        <button type="button" disabled={!recordId} onClick={() => recordId && pin(recordId)}>使用当前记录为基准</button>
        <button type="button" disabled={!baseline && !draft} onClick={() => pin('')}>清除基准</button>
      </div>
    </form>
    {draft.trim() !== baseline && <p>输入已修改，应用基准后更新对比。</p>}
    {!baseline ? <p>尚未设置基准。选择记录后可使用上方按钮固定基准。</p> : !recordId ? <p>基准已设置。选择上方一条模型记录开始对比。</p> : <>
      <dl className="context-comparison-identity">
        <div><dt>基准记录</dt><dd><code>{baseline}</code></dd></div>
        <div><dt>当前记录</dt><dd><code>{recordId}</code></dd></div>
      </dl>
      <p>方向：基准记录 → 当前记录。仅对比脱敏后保存的上下文，不证明调用继承关系、模型正确性或任务完成。</p>
      <Notice loading={result.loading} error={result.error}/>
      {data && <>
        <p>上次成功读取：{stamp(result.observed)}{result.error ? ' · 数据可能过期，正在自动重连' : ''}</p>
        {!delta ? <div className="context-integrity context-inconsistent" role="alert">
          <strong>无法比较上下文证据</strong><p>至少一侧的记录缺失、不一致或结构无法比较；这不表示两次调用没有变化。</p>
          {(['before', 'after'] as const).map(side => <div key={side}>
            <strong>{side === 'before' ? '基准记录' : '当前记录'}</strong>
            <ul>{[...(data[side]?.integrity?.issues || []), ...(data[side]?.comparison_issues || [])].map((issue: string, index: number) => <li key={index}>{issues[issue] || issue}</li>)}</ul>
          </div>)}
          <Raw value={{ before: data.before, after: data.after }} label="双方证据检查详情"/>
        </div> : <>
          <div className="context-integrity" role="status">
            <strong>{baseline === recordId ? '正在比较同一条记录' : '已读取两条记录的上下文差异'}</strong>
            <p>新增 {rows(fragments?.added).length} 个片段 · 移除 {rows(fragments?.removed).length} 个片段 · 变化 {rows(fragments?.changed).length} 个片段</p>
            {data.scope_differences?.length > 0 && <p>范围字段不同：{data.scope_differences.map(label).join('、')}。请结合请求身份判断比较是否有意义。</p>}
          </div>
          <h3>预算与渲染变化</h3>
          {budget.length ? budget.map(change => <FieldChange key={change.field} change={change}/>) : <p>记录的预算与渲染字段没有变化。</p>}
          <FragmentList items={rows(fragments?.added)} title="新增片段"/>
          <FragmentList items={rows(fragments?.removed)} title="移除片段"/>
          <h3>变化片段 · {rows(fragments?.changed).length}</h3>
          <p>内容哈希基于脱敏后的显示值；可在下方单记录区域查看当前片段原文。</p>
          {rows(fragments?.changed).map(item => <details className="context-fragment context-changed-fragment" key={item.id}>
            <summary><code>{item.id}</code> · {rows(item.fields).map(change => label(change.field)).join('、')}</summary>
            {rows(item.fields).map(change => <FieldChange key={change.field} change={change}/>)}
          </details>)}
          {!rows(fragments?.changed).length && <p>没有变化片段。</p>}
          <Raw value={fragments?.unchanged_ids} label={`未变化片段 · ${fragments?.unchanged_ids?.length || 0}`}/>
          <h3>请求身份与诊断</h3>
          <details className="context-fragment"><summary>请求字段变化 · {rows(delta.request).length}</summary>
            {rows(delta.request).length ? rows(delta.request).map(change => <FieldChange key={change.field} change={change}/>) : <p>请求字段没有变化。</p>}
          </details>
          <Raw value={fragments?.order} label={fragments?.order?.changed ? '片段顺序已变化' : '片段顺序未变化'}/>
          <Raw value={{ manifest: delta.manifest, allocation: delta.allocation, provider_diagnostics: delta.provider_diagnostics }} label="完整清单、预算与 Provider 诊断差异"/>
        </>}
      </>}
    </>}
  </section>;
}
