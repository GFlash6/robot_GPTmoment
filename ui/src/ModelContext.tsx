import { Json, stamp, useQuery } from './api';
import { Notice, Raw } from './components';
import './model-context.css';

const integrityLabels: Record<string, string> = {
  matched: '关联与包哈希一致', partial: '上下文记录不完整',
  unavailable: '没有保存上下文', inconsistent: '上下文证据不一致',
};
export const contextIssueLabels: Record<string, string> = {
  missing_bundle: '引用的上下文包不存在', missing_manifest: '引用的来源清单不存在',
  bundle_hash_mismatch: '上下文包与保存的哈希不一致', unsupported_bundle_version: '上下文包版本不受支持',
  manifest_identity_mismatch: '来源清单身份不一致', request_manifest_mismatch: '请求与来源清单不对应',
  model_identity_mismatch: '模型记录身份不一致',
};
const array = (value: unknown): Json[] => Array.isArray(value) ? value : [];

export function ModelContext({ recordId }: { recordId?: string }) {
  const result = useQuery<Json>(recordId ? `/models/${encodeURIComponent(recordId)}/context` : null);
  const data = result.data?.model_record_id === recordId ? result.data : undefined;
  const integrity = data?.integrity;
  const fragments = array(data?.bundle?.fragments);
  const included = new Set<string>(data?.manifest?.included || []);
  const dropped = array(data?.manifest?.dropped);
  return <section className="panel model-context" aria-labelledby="model-context-title">
    <h2 id="model-context-title">本次调用的上下文</h2>
    <p>查看已保存的来源与预算分配。这里只读记录，不重新调用模型。</p>
    {!recordId ? <p>选择上方一条模型记录，查看它关联的上下文证据。</p> : <>
      <p className="context-record">模型记录 <code>{recordId}</code></p>
      <Notice loading={result.loading} error={result.error}/>
      {data && <>
        <div className={`context-integrity context-${integrity?.status}`} role={integrity?.status === 'inconsistent' ? 'alert' : 'status'}>
          <strong>{integrityLabels[integrity?.status] || '未识别的检查状态'}</strong>
          <p>仅检查存储关联与包哈希；不代表模型回答正确或机器人任务完成。</p>
          {array(integrity?.issues).length > 0 && <ul>{integrity.issues.map((issue: string) => <li key={issue}>{contextIssueLabels[issue] || issue}</li>)}</ul>}
        </div>
        <p>上次成功读取：{stamp(result.observed)}{result.error ? ' · 数据可能过期，正在自动重连' : ''}</p>
        {!data.bundle && <p>该记录没有可读取的完整上下文包。保留已有证据，不补造历史输入。</p>}
        {data.manifest && <dl className="context-budget">
          <div><dt>输入估算</dt><dd>{data.manifest.estimated_input_tokens ?? '未记录'} tokens</dd></div>
          <div><dt>输入上限</dt><dd>{data.manifest.input_token_limit ?? '未记录'} tokens</dd></div>
          <div><dt>输出预留</dt><dd>{data.manifest.reserved_output_tokens ?? '未记录'} tokens</dd></div>
        </dl>}
        <h3>来源片段 · {fragments.length}</h3>
        {fragments.map((fragment, index) => <details className="context-fragment" key={`${fragment.id}-${index}`}>
          <summary><span><code>{fragment.id}</code> · {included.has(fragment.id) ? '已纳入' : '未纳入'}</span><span>{fragment.source}</span></summary>
          <p>权限层级：{fragment.authority} · {fragment.required ? '必需片段' : '可选片段'}</p>
          <pre>{JSON.stringify(fragment.content, null, 2)}</pre>
          <Raw value={{ evidence_ids: fragment.evidence_ids, metadata: fragment.metadata }} label="来源标识与元数据"/>
        </details>)}
        {!fragments.length && <p>没有可展示的片段。</p>}
        <h3>预算丢弃 · {dropped.length}</h3>
        {dropped.length ? <ul>{dropped.map((item, index) => <li key={index}><code>{item.id}</code>：{item.reason === 'over_budget' ? '超出输入预算' : item.reason || '未记录原因'}</li>)}</ul> : <p>{data.manifest ? '清单未记录预算丢弃。' : '没有来源清单，无法判断预算丢弃情况。'}</p>}
        <Raw value={data.manifest} label="完整来源清单与 Provider 诊断"/>
        <Raw value={data.bundle?.request ?? null} label="上下文请求身份"/>
        <Raw value={integrity} label="关联检查原始字段"/>
      </>}
    </>}
  </section>;
}
