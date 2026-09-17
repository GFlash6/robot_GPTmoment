import { useEffect, useRef, useState } from 'react';
import { Braces, Check, ChevronRight, Layers3, MessagesSquare, Play, Route, TriangleAlert } from 'lucide-react';
import './semantic-context-test.css';
import './semantic-clarification.css';

type Config = {model:string; csrf:string; ready:boolean; timeout:number};
type Json = Record<string, any>;
type Analysis = {
  goal_context:Json;
  status:string;
  questions:Json[];
  analysis_response_id:string;
  clarification_response_id?:string;
};
type ContextPreview = {
  request_id:string;
  phase:string;
  catalog_size:number;
  fragments:Json[];
  messages:Json[];
  allocation:Json;
};
type PlanResult = {
  request_id:string;
  analysis_response_id:string;
  planning_response_id:string;
  context_manifest_id:string;
  catalog_size:number;
  plan:Json;
};
type Tab = 'semantic'|'context'|'messages'|'plan';

const statusText:Record<string,string> = {
  ready:'语义已就绪',
  needs_grounding:'需要机器人感知落地',
  needs_clarification:'有可选追问',
};

function JsonBlock({value,label}:{value:unknown;label:string}){
  return <details className="semantic-json" open><summary>{label}</summary><pre>{JSON.stringify(value,null,2)}</pre></details>;
}

export function SemanticContextTest(){
  const [config,setConfig]=useState<Config>();
  const [goal,setGoal]=useState('到厨房去找热水壶');
  const [robotId,setRobotId]=useState('g1');
  const [clarification,setClarification]=useState('');
  const [busy,setBusy]=useState<''|'analysis'|'context'|'plan'>('');
  const [error,setError]=useState('');
  const [analysis,setAnalysis]=useState<Analysis>();
  const [context,setContext]=useState<ContextPreview>();
  const [plan,setPlan]=useState<PlanResult>();
  const [tab,setTab]=useState<Tab>('semantic');
  const pending=useRef(false);

  useEffect(()=>{
    let active=true;
    fetch('/model-test/config').then(async response=>{
      if(!response.ok)throw new Error();
      return response.json();
    }).then(value=>{if(active)setConfig(value)}).catch(()=>{
      if(active)setError('真实模型测试网关未连接。请启动网关后刷新页面。');
    });
    return()=>{active=false};
  },[]);

  async function post<T>(path:string,body:Json,timeoutSeconds?:number):Promise<T>{
    if(!config)throw new Error('测试网关尚未就绪');
    const response=await fetch(path,{
      method:'POST',
      headers:{'Content-Type':'application/json','X-Model-Test-Token':config.csrf},
      body:JSON.stringify(body),
      signal:AbortSignal.timeout((timeoutSeconds??config.timeout+20)*1000),
    });
    const text=await response.text();
    let result:Json;
    try{result=JSON.parse(text)}catch{
      throw new Error(`服务返回了不可解析的内容（HTTP ${response.status}）。请查看服务端日志并确认审计记录后再重试`);
    }
    if(!response.ok)throw new Error(result.error||`请求失败 (${response.status})`);
    return result as T;
  }

  function invalidate(value:string,field:'goal'|'robot'){
    if(field==='goal')setGoal(value);else setRobotId(value);
    setAnalysis(undefined);setContext(undefined);setPlan(undefined);
    setClarification('');setError('');setTab('semantic');
  }

  async function runAnalysis(withClarification=false){
    if(!goal.trim()||pending.current)return;
    pending.current=true;setBusy('analysis');setError('');setAnalysis(undefined);setContext(undefined);setPlan(undefined);setTab('semantic');
    try{
      const conversation=withClarification&&analysis?[
        {role:'assistant',content:analysis.questions.map(item=>item.question).join('\n')},
        {role:'user',content:clarification.trim()},
      ]:[];
      setAnalysis(await post<Analysis>(
        '/semantic-test/analyze',
        {goal,conversation},
        config?config.timeout*2+20:140,
      ));
      if(withClarification)setClarification('');
    }catch(value){setError(`${value instanceof Error?value.message:'语义分析失败'} 不会自动重试。`)}
    finally{pending.current=false;setBusy('')}
  }

  async function buildContext(){
    if(!analysis||pending.current)return;
    pending.current=true;setBusy('context');setError('');setContext(undefined);setPlan(undefined);
    try{
      const value=await post<ContextPreview>('/semantic-test/context',{
        analysis_response_id:analysis.analysis_response_id,
        robot_id:robotId,
      });
      setContext(value);setTab('context');
    }catch(value){setError(`${value instanceof Error?value.message:'上下文生成失败'}`)}
    finally{pending.current=false;setBusy('')}
  }

  async function runPlan(){
    if(!analysis||!context||pending.current)return;
    pending.current=true;setBusy('plan');setError('');setPlan(undefined);
    try{
      const value=await post<PlanResult>('/semantic-test/plan',{
        context_request_id:context.request_id,
      });
      setPlan(value);setTab('plan');
    }catch(value){setError(`${value instanceof Error?value.message:'真实规划失败'} 不会自动重试。`)}
    finally{pending.current=false;setBusy('')}
  }

  const steps=[
    {label:'语义分析',done:!!analysis,active:busy==='analysis'},
    {label:'上下文生成',done:!!context,active:busy==='context'},
    {label:'真实规划',done:!!plan,active:busy==='plan'},
  ];
  const tabs:{id:Tab;label:string;icon:typeof Braces;enabled:boolean}[]=[
    {id:'semantic',label:'语义档案',icon:Braces,enabled:!!analysis},
    {id:'context',label:'上下文片段',icon:Layers3,enabled:!!context},
    {id:'messages',label:'实际消息',icon:MessagesSquare,enabled:!!context},
    {id:'plan',label:'规划结果',icon:Route,enabled:!!plan},
  ];

  return <section className="panel semantic-test" aria-labelledby="semantic-test-title">
    <div className="semantic-head">
      <div><h2 id="semantic-test-title">语义 → 上下文 → 规划</h2><p>从一条真实指令开始，逐段检查生产链路留下的结构化结果与审计 ID。</p></div>
      <code>{config?.model||'等待网关'}</code>
    </div>
    <div className="semantic-steps" aria-label="测试进度">
      {steps.map((step,index)=><div className={`${step.done?'done':''} ${step.active?'active':''}`} key={step.label}>
        <span>{step.done?<Check size={13}/>:index+1}</span><strong>{step.label}</strong>{index<steps.length-1&&<ChevronRight size={14}/>} 
      </div>)}
    </div>
    <div className="semantic-workbench">
      <form onSubmit={event=>{event.preventDefault();void runAnalysis(false)}}>
        <label htmlFor="semantic-goal">初始语义指令</label>
        <textarea id="semantic-goal" value={goal} onChange={event=>invalidate(event.target.value,'goal')} rows={4} maxLength={8000} required disabled={!!busy}/>
        <div className="semantic-field-row">
          <div><label htmlFor="semantic-robot">机器人 ID</label><input id="semantic-robot" value={robotId} onChange={event=>invalidate(event.target.value,'robot')} maxLength={128} disabled={!!busy}/></div>
          <div className="semantic-fact"><span>技能目录</span><strong>{context?`${context.catalog_size} 项真实注册技能`:'生成上下文后读取'}</strong></div>
        </div>
        <button className="semantic-primary" disabled={!!busy||!config?.ready||!goal.trim()}>
          <Play size={15} fill="currentColor"/>{busy==='analysis'?'正在调用语义模型…':'调用真实模型分析'}
        </button>
        <p className="semantic-cost">此操作调用外部模型并消耗额度。请求不会自动重试。</p>
        {analysis?.status==='needs_clarification'&&<div className="clarification-input">
          <label htmlFor="semantic-clarification">补充回答（可选）</label>
          <textarea id="semantic-clarification" value={clarification} onChange={event=>setClarification(event.target.value)} rows={3} maxLength={8000} placeholder="例如：只需要找到并报告位置，不需要拿取。" disabled={!!busy}/>
          <button type="button" className="semantic-secondary" onClick={()=>void runAnalysis(true)} disabled={!!busy||!clarification.trim()}>带补充说明重新分析</button>
          <p className="semantic-cost">可直接继续生成上下文和规划；不回答时未知信息会保留。补充回答会发起一次新的真实语义模型调用，并保留上一轮审计记录。</p>
        </div>}
        <div className="semantic-divider"/>
        <button type="button" className="semantic-secondary" onClick={()=>void buildContext()} disabled={!!busy||!analysis}>
          <Layers3 size={15}/>{busy==='context'?'正在生成上下文…':'从已验证分析生成上下文'}
        </button>
        <p className="semantic-cost">从服务端审计记录读取分析结果；浏览器不能替换语义 JSON。</p>
        <button type="button" className="semantic-primary plan-button" onClick={()=>void runPlan()} disabled={!!busy||!context}>
          <Route size={15}/>{busy==='plan'?'正在调用规划模型…':'使用该上下文真实规划'}
        </button>
        <p className="semantic-cost">再次调用外部模型，并执行 DAG、技能名与最终 verifier 契约校验。未回答的追问不会阻止规划。</p>
        {!config?.ready&&config&&<p role="alert" className="semantic-inline-error"><TriangleAlert size={14}/>服务端没有读取到 API Key。</p>}
      </form>
      <div className="semantic-output" aria-live="polite" aria-busy={!!busy}>
        <div className="semantic-tabs" role="tablist" aria-label="链路输出">
          {tabs.map(item=><button type="button" role="tab" aria-selected={tab===item.id} disabled={!item.enabled} className={tab===item.id?'active':''} onClick={()=>setTab(item.id)} key={item.id}><item.icon size={14}/>{item.label}</button>)}
        </div>
        {error&&<p role="alert" className="semantic-error"><TriangleAlert size={15}/><span>{error}</span></p>}
        {!analysis&&!busy&&!error&&<div className="semantic-empty"><Route size={28}/><h3>等待真实链路输入</h3><p>点击“调用真实模型分析”。成功后才能继续生成上下文和规划。</p></div>}
        {busy&&<div className="semantic-loading"><span/><div><strong>{busy==='analysis'?'模型正在解析目标':busy==='context'?'框架正在组装上下文':'模型正在生成并校验计划'}</strong><p>保持页面打开；结果不确定时不会自动重发。</p></div></div>}
        {!busy&&tab==='semantic'&&analysis&&<div className="semantic-pane">
          <div className={`semantic-status ${analysis.status}`}><span/><strong>{statusText[analysis.status]||analysis.status}</strong><code>{analysis.analysis_response_id}</code></div>
          {analysis.questions.length>0&&<div className="semantic-questions"><h3>可选追问</h3>{analysis.questions.map((item,index)=><div key={`${item.field}-${index}`}><strong>{item.question}</strong><span>{item.reason}</span></div>)}</div>}
          <JsonBlock label="经契约校验的 GoalContext" value={analysis.goal_context}/>
        </div>}
        {!busy&&tab==='context'&&context&&<div className="semantic-pane">
          <div className="context-summary"><span>请求 <code>{context.request_id}</code></span><span>{context.fragments.length} 个片段</span><span>{context.catalog_size} 项技能</span></div>
          <div className="fragment-list">{context.fragments.map(item=><article key={item.id}><div><strong>{item.id}</strong><span>{item.kind}</span><span>{item.authority}</span>{item.required&&<em>必选</em>}</div><p>{item.source}</p><pre>{JSON.stringify(item.content,null,2)}</pre></article>)}</div>
        </div>}
        {!busy&&tab==='messages'&&context&&<div className="semantic-pane">
          <div className="allocation-strip"><div><span>估算输入</span><strong>{context.allocation.estimated_input_tokens}</strong></div><div><span>输入上限</span><strong>{context.allocation.input_token_limit}</strong></div><div><span>预留输出</span><strong>{context.allocation.reserved_output_tokens}</strong></div><div><span>估算器</span><code>{context.allocation.estimator}</code></div></div>
          <JsonBlock label="实际准备发送的 messages" value={context.messages}/>
          <JsonBlock label="上下文分配清单" value={context.allocation}/>
        </div>}
        {!busy&&tab==='plan'&&plan&&<div className="semantic-pane">
          <div className="plan-proof"><Check size={17}/><div><strong>模型响应已通过计划契约</strong><span>规划绑定上下文请求 {plan.request_id}；这里只证明规划结果合法，尚未提交或执行机器人任务。</span></div></div>
          <dl className="semantic-ids"><dt>上下文请求</dt><dd>{plan.request_id}</dd><dt>分析审计</dt><dd>{plan.analysis_response_id}</dd><dt>规划审计</dt><dd>{plan.planning_response_id}</dd><dt>上下文清单</dt><dd>{plan.context_manifest_id}</dd></dl>
          <JsonBlock label="经契约校验的计划" value={plan.plan}/>
        </div>}
      </div>
    </div>
  </section>;
}
