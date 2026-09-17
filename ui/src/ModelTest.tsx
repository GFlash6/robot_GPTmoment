import { useEffect, useRef, useState } from 'react';
import './model-test.css';

type Result = {id:string; question:string; expected:string; status:string; answer?:string; error?:string; elapsed_ms?:number; response_id?:string; actual_model?:string; verdict?:string; http_status?:number};
type Config = {model:string; csrf:string; ready:boolean; timeout:number};
const verdicts:Record<string,string> = {matched:'预期答案匹配', mismatched:'预期答案不匹配', unjudged:'未判定正确性'};
export function ModelTest(){
  const [config,setConfig]=useState<Config>();
  const [question,setQuestion]=useState('');
  const [expected,setExpected]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [records,setRecords]=useState<Result[]>([]);
  const [selected,setSelected]=useState<Result>();
  const pending=useRef(false);
  async function history(){
    const response=await fetch('/model-test/history');
    if(!response.ok) throw new Error('无法读取测试历史');
    const body=await response.json();setRecords(body.items);
  }
  useEffect(()=>{let active=true;fetch('/model-test/config').then(async r=>{if(!r.ok)throw new Error();return r.json()}).then(c=>{if(active){setConfig(c);history().catch(()=>setError('无法读取测试历史，请刷新页面。'))}}).catch(()=>{if(active)setError('测试服务未连接。请启动模型测试网关，并打开其页面。')});return()=>{active=false}},[]);
  async function send(e:React.FormEvent){
    e.preventDefault();if(!config||pending.current||!question.trim())return;
    pending.current=true;setBusy(true);setError('');setSelected(undefined);
    try{
      const response=await fetch('/model-test/run',{method:'POST',headers:{'Content-Type':'application/json','X-Model-Test-Token':config.csrf},body:JSON.stringify({id:crypto.randomUUID(),question,expected}),signal:AbortSignal.timeout((config.timeout+20)*1000)});
      const result=await response.json();if(!response.ok)throw new Error(result.error);
      setSelected(result);await history();
    }catch(e){setError(`${e instanceof Error?e.message:'请求失败'}。如已发送，请先刷新历史确认结果，避免重复调用。`)}
    finally{pending.current=false;setBusy(false)}
  }
  return <section className="panel model-test" aria-labelledby="model-test-title">
    <div className="section-head"><h2 id="model-test-title">真实问答测试</h2><code>{config?.model||'qwen3.8-max'}</code></div>
    <div className="model-test-grid"><form onSubmit={send}>
      <p>自由输入问题，查看模型的实际回答。每次发送会消耗 API 额度。</p>
      <label htmlFor="qa-question">测试问题</label><textarea id="qa-question" value={question} onChange={e=>setQuestion(e.target.value)} maxLength={8000} required rows={5} placeholder="例如：37 箱零件，每箱 29 个，取走 428 个，还剩多少？只回答数字。"/>
      <label htmlFor="qa-expected">预期答案 <span>（可选）</span></label><textarea id="qa-expected" value={expected} onChange={e=>setExpected(e.target.value)} maxLength={8000} rows={2}/>
      <p className="qa-help">填写后按去除首尾空白的全文匹配；预期答案不会发送给模型。</p>
      <button className="qa-send" disabled={busy||!config?.ready||!question.trim()}>{busy?'正在等待模型回答…':'发送测试'}</button>
      {config&&!config.ready&&<p role="alert">服务端未读取到 API Key，请设置环境变量后重启服务。</p>}
    </form><div className="qa-result" aria-live="polite" aria-busy={busy}>
      <h3>实际回答</h3>{error&&<p role="alert" className="qa-error">{error}</p>}
      {busy?<p>请求已发送，请等待。不会自动重试。</p>:selected?<>
        <p className="qa-outcome">{selected.status==='completed'?'调用完成':selected.status==='requesting'?'请求处理中 / 结果尚未记录':'调用失败'}{selected.verdict&&` · ${verdicts[selected.verdict]}`}</p>
        <p className="qa-answer">{selected.answer||selected.error||'尚未收到回答'}</p>
        <dl><dt>耗时</dt><dd>{selected.elapsed_ms!=null?`${(selected.elapsed_ms/1000).toFixed(2)} 秒`:'待记录'}</dd><dt>返回模型</dt><dd>{selected.actual_model||'未记录'}</dd><dt>HTTP 状态</dt><dd>{selected.http_status??'未收到'}</dd><dt>响应 ID</dt><dd>{selected.response_id||'未记录'}</dd></dl>
      </>:<p>发送问题后，回答和耗时会显示在这里。没有预期答案时，请自行核对回答内容。</p>}
    </div></div>
    <details className="qa-history"><summary>测试历史（最近 {records.length} 条）</summary><button type="button" onClick={()=>history().catch(()=>setError('刷新历史失败，请检查服务连接。'))}>刷新历史</button>{records.map(r=><button type="button" key={r.id} onClick={()=>{setSelected(r);setQuestion(r.question);setExpected(r.expected)}}><span>{r.question}</span><span>{r.status==='completed'?verdicts[r.verdict||'unjudged']:r.status==='failed'?'调用失败':'待确认'}</span></button>)}</details>
  </section>
}
