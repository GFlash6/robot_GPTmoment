// Reproducible candidate generator. Emits an apply_patch patch; never writes canonical state.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const current=read('.momo/momo-workspace.json');
if(current.workspace.revision!==15)throw new Error('Revision drift: rebuild explicitly from current state.');
const candidate=structuredClone(current), snap=candidate.snapshot;
const now=new Date().toISOString(), project='project-robot-agent-framework', group='model-adapter';
const doc='docs/MODEL_CONTEXT_FLOW.md';
const specs=[
 ['qa','UI 单轮问答入口','work_item','done','只发送当前问题；预期答案本地匹配，历史不自动带入。','robot_agent_observer/model_test.py','caller.call("qa", {question})；UI 输入 question / expected / id；模型仅接收 question。',0,0],
 ['planner','规划入口 · Planner','work_item','done','目标＋技能目录；初次提交默认无上下文，CLI 可显式传入。','robot_agent/planner.py','plan(goal, catalog, context=None)；技能目录只保留 schema、checks、resources、verifier 等能力字段。',0,1],
 ['config','模型配置 · ModelConfig','artifact','done','qwen3.8-max；显式 URL；凭证按环境变量名读取。','robot_agent/model_transport.py','endpoint/model/token_env/timeout/max_input_tokens/max_output_tokens。当前超时60秒；默认预算32768，输出2048。密钥不进入图或提示词。',0,2],
 ['caller','统一调用器 · ModelCaller','work_item','done','组合方法、预算和传输；每次调用独立，无内部会话历史。','robot_agent/model_call.py','call(method, arguments, context=()) → ModelCallResult。允许替换 methods、allocator、transport。',1,0],
 ['methods','调用方法 · qa / planning','artifact','done','生成基础 system/user 消息及 response_format、temperature。','robot_agent/model_methods.py','qa：准确简洁回答，参数可指定 instruction/temperature/response_format；UI 当前只传问题。planning：目标与技能 JSON，要求 JSON 计划。',2,0],
 ['fragments','上下文片段 · ContextFragment','artifact','done','id、content、priority、required；重规划封装为必需片段。','robot_agent/model_context.py','Planner 将外部 JSON 序列化为 planner_runtime_context，priority=100，required=True；没有跨轮消息缓存。',1,1],
 ['allocator','上下文分配 · ContextAllocator','work_item','done','先基础提示，再必需片段，再按优先级加入可选片段。','robot_agent/model_context.py','预算=max_input_tokens-max_output_tokens；UTF-8 字节估算。必需内容放不下报错，可选内容放不下丢弃；返回 included/dropped/estimated_input_tokens。',2,1],
 ['request','请求装配 · ModelRequest','artifact','done','方法 system → 上下文 system（可选）→ 当前 user。','robot_agent/model_call.py','messages、response_format、temperature。context_message 标明上下文是数据，但使用 system role，不等于可靠的指令隔离。',3,0],
 ['transport','HTTP 传输与环境鉴权','work_item','done','POST 显式 endpoint；发送时读取 token_env 指向的凭证。','robot_agent/model_transport.py','请求体 model/messages/max_tokens；按需带 temperature/response_format。非流式，不自动重试，禁止重定向，trust_env=False。',4,0],
 ['result','返回结构 · ModelCallResult','artifact','done','正文、实际模型、响应 ID、结束原因、预算分配及传输结果。','robot_agent/model_call.py','统一要求 2xx、finish_reason=stop、非拒绝且正文非空。TransportResponse 保存 HTTP 状态、raw/body、elapsed_ms；不是机器人成功证据。',4,1],
 ['validation','业务判定 · 计划 / 问答','work_item','done','规划校验 DAG 和最终 verifier；问答可选全文匹配。','robot_agent/planner.py','Planner 解析内容并 validate_plan；UI 去首尾空白比较 expected，不填写则 unjudged。请求成功、答案正确、任务完成是不同层次。',3,2],
 ['qa-history','问答历史 · 独立 SQLite','artifact','done','保存问题、回答和耗时；仅查看，不自动续接对话。','robot_agent_observer/model_test.py','model-tests.sqlite：tests(id, created, data)；展示最近50条。预期答案只参与本地比较。这里描述结构，不保存实际问答正文。',4,2],
 ['plan-history','规划证据 · model_responses','artifact','done','保留请求状态、原始响应、合法计划和上下文分配信息。','robot_agent/planner.py','ledger.sqlite 中 model_responses 集合；requesting→validated/rejected。不会自动回放到下一次模型请求。',3,3],
 ['task-state','任务状态 · tasks 账本','artifact','done','计划、步骤结果和修订号是自动重规划的历史来源。','robot_agent/runtime.py','保存任务 goal/plan/steps/catalog/revision 等。模型配置仅保留 endpoint/model/token_env/timeout。不是完整聊天历史。',0,3],
 ['replan','历史回流 · recover_plan','work_item','in_progress','读取任务失败状态，有界重规划；真实执行闭环仍待验收。','robot_agent/runtime.py','previous_plan=task.plan；step_results=task.steps；revision=task.revision。传入 Planner 必需片段；不自动重放全部历次规划。',1,3],
 ['gap-session','未完成 · 连续会话历史','work_item','open','尚无 session_id、多轮 user/assistant 组装和会话隔离。','ui/src/ModelTest.tsx','已有问答持久化，但每次 UI 发送只有当前问题；后续实现需要明确会话标识、保留策略与调用入口。',0,4],
 ['gap-summary','未完成 · 摘要与检索注入','work_item','open','尚无滑动窗口、摘要和资产/记忆自动检索；必需片段超限报错。','robot_agent/model_context.py','ContextAllocator 仅选择片段，不执行摘要或检索；重规划整体必需上下文可能超限。当前不存在自动 memory→prompt 通路。',2,4],
 ['gap-budget','缺口 · 重规划预算继承','work_item','open','自定义输入输出预算未随任务配置保存；重规划回到默认值。','robot_agent/runtime.py','submit_goal 的 model_config 白名单缺 max_input_tokens/max_output_tokens；这里只记录缺口，未修改运行代码。',1,4]
];
const prefix='model-flow-', id=k=>prefix+k;
for(const [key,title,type,lifecycle,summary,source,detail,col,row] of specs){
 const oid=id(key),cid=oid+'-content';
 snap.objects.push({id:oid,projectId:project,type,schemaVersion:1,title,lifecycle,summary,
  properties:{evidenceStatus:'Confirmed',source,sourceFingerprint:hash(source),flowGuide:doc,implementationStatus:lifecycle==='open'?'not_implemented':lifecycle==='in_progress'?'implemented_pending_live_validation':'implemented'},
  contentRef:{contentId:cid,format:'text/plain',schemaVersion:1},createdAt:now,updatedAt:now});
 snap.contents.push({id:cid,objectId:oid,format:'text/plain',schemaVersion:1,value:title+'\n\n'+summary+'\n\n'+detail+'\n\n代码证据：'+source+'\n关系说明：'+doc,updatedAt:now});
 snap.relations.push({id:'contains-'+oid,sourceObjectId:group,targetObjectId:oid,type:'contains',createdAt:now});
}
const parent=snap.objects.find(o=>o.id===group);
parent.title='模型调用与上下文流转';
parent.summary='独立展开调用入口、配置、方法、上下文预算、HTTP、结果与三类历史；明确单轮问答和重规划回流，连续会话/摘要检索及预算继承仍有缺口。';
parent.updatedAt=now;parent.properties.flowGuide=doc;
parent.contentRef={contentId:'model-flow-overview-content',format:'text/plain',schemaVersion:1};
snap.contents.push({id:'model-flow-overview-content',objectId:group,format:'text/plain',schemaVersion:1,value:fs.readFileSync(doc,'utf8'),updatedAt:now});
snap.views.push({id:'model-context-flow-canvas',projectId:project,kind:'canvas',scopeObjectId:group,
 positions:Object.fromEntries(specs.map(([key,,,,,,,col,row])=>[id(key),{x:48+col*350,y:48+row*235}]))});
const assessment=read('.momo/intake/relation-assessment.json');
assessment.generatedAt=now;
assessment.projects[0].graphHealth.eligibleObjectCount+=specs.length;
assessment.projects[0].graphHealth.isolatedObjectKeys=specs.map(s=>id(s[0])).sort();
// Code was reviewed: adopted dependencies, Planner transport refactor and UI addition preserve existing claims.
for(const c of assessment.projects[0].candidates)for(const e of c.evidence){const fingerprint=hash(e.path);if(fingerprint!==e.fingerprint){e.fingerprint=fingerprint;e.observedAt=now;}}
const edges=[
 ['qa','caller','supports','qa-entry-calls-model','robot_agent_observer/model_test.py','robot_agent/model_call.py'],
 ['planner','caller','supports','planner-calls-model','robot_agent/planner.py','robot_agent/model_call.py'],
 ['config','caller','supports','configured-call','robot_agent/model_transport.py','robot_agent/model_call.py'],
 ['caller','methods','supports','dispatch-method','robot_agent/model_call.py','robot_agent/model_methods.py'],
 ['planner','fragments','supports','serialize-runtime-context','robot_agent/planner.py','robot_agent/model_context.py'],
 ['methods','allocator','supports','base-message-budget','robot_agent/model_methods.py','robot_agent/model_call.py'],
 ['fragments','allocator','supports','select-context-fragments','robot_agent/model_context.py','robot_agent/model_call.py'],
 ['config','allocator','supports','input-output-budget','robot_agent/model_transport.py','robot_agent/model_context.py'],
 ['allocator','request','supports','render-selected-context','robot_agent/model_context.py','robot_agent/model_call.py'],
 ['request','transport','supports','send-model-request','robot_agent/model_call.py','robot_agent/model_transport.py'],
 ['config','transport','supports','endpoint-model-auth','robot_agent/model_transport.py','robot_agent/model_call.py'],
 ['transport','result','supports','parse-transport-response','robot_agent/model_transport.py','robot_agent/model_call.py'],
 ['result','validation','supports','business-response-check','robot_agent/model_call.py','robot_agent/planner.py'],
 ['validation','qa-history','supports','persist-qa-verdict','robot_agent_observer/model_test.py','ui/src/ModelTest.tsx'],
 ['validation','plan-history','supports','persist-plan-verdict','robot_agent/planner.py','robot_agent/runtime.py'],
 ['validation','task-state','supports','submit-validated-plan','robot_agent/planner.py','robot_agent/runtime.py'],
 ['task-state','replan','supports','replan-reads-task-state','robot_agent/runtime.py','robot_agent/planner.py'],
 ['replan','fragments','supports','replan-injects-required-context','robot_agent/runtime.py','robot_agent/planner.py'],
 ['gap-session','qa-history','depends_on','session-needs-history-integration','ui/src/ModelTest.tsx','robot_agent_observer/model_test.py'],
 ['gap-summary','allocator','depends_on','summary-needs-budget-integration','robot_agent/model_context.py','robot_agent/model_call.py'],
 ['gap-budget','task-state','depends_on','budget-needs-task-persistence','robot_agent/runtime.py','robot_agent/model_transport.py']
];
const newRelations=[];
for(const [from,to,type,claimKey,...paths] of edges){
 const sourceKey=id(from),targetKey=id(to);
 const key='relation-'+createHash('sha256').update([project,sourceKey,targetKey,claimKey].join('\0')).digest('hex').slice(0,16);
 newRelations.push({id:key,sourceObjectId:sourceKey,targetObjectId:targetKey,type,createdAt:now});
 assessment.projects[0].candidates.push({claimKey,action:'add',confidence:'high',confirmedDecision:false,
  relation:{key,sourceKey,targetKey,type},evidence:paths.map(path=>({sourceId:path,path,fingerprint:hash(path),claim:claimKey,authority:'repository',observedAt:now})),
  alternatives:[],blockingReasons:[],status:'proposed',changesBoundary:false,changesOwnership:false,changesPermission:false,changesSafetyBoundary:false});
}
const structure=structuredClone(candidate);
snap.relations.push(...newRelations);
const files={'.momo/intake/model-context-structure.json':structure,'.momo/intake/model-context-candidate.json':candidate,'.momo/intake/model-context-assessment.json':assessment};
let patch='*** Begin Patch\n';
for(const [file,value]of Object.entries(files)){if(fs.existsSync(file))throw new Error('Candidate already exists: '+file);patch+='*** Add File: '+path.resolve(file)+'\n'+JSON.stringify(value,null,2).split('\n').map(l=>'+'+l).join('\n')+'\n';}
process.stdout.write(patch+'*** End Patch\n');
