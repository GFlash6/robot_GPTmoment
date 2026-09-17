import fs from 'node:fs';
import path from 'node:path';
const canonical=JSON.parse(fs.readFileSync('.momo/momo-workspace.json','utf8'));
if(canonical.workspace.revision!==16)throw new Error('Unexpected canonical revision; stop finalization.');
const assessment=JSON.parse(fs.readFileSync('.momo/intake/model-context-assessment.json','utf8'));
const now=new Date().toISOString();
assessment.generatedAt=now;assessment.baseRevision=16;
const project=assessment.projects[0];
project.zeroRelationRationale='单一项目；模型调用与上下文流转独立展开，原主图保留，所有内部语义关系同属 model-adapter 容器。';
project.graphHealth={semanticRelationCount:38,eligibleObjectCount:36,isolatedObjectKeys:[],invalidRelationKeys:[],zeroRelationWarning:false,staleEvidenceRelationKeys:[]};
for(const c of project.candidates)if(c.status==='proposed'){
 if(!canonical.snapshot.relations.some(r=>r.id===c.relation.key))throw new Error('Relation was not written');
 c.status='auto_applied';c.autoEligible=true;c.appliedAt=now;
}
let patch='*** Begin Patch\n';
const file='.momo/intake/relation-assessment.json';
const old=fs.readFileSync(file,'utf8').trimEnd();
patch+='*** Update File: '+path.resolve(file)+'\n@@\n'+old.split('\n').map(l=>'-'+l).join('\n')+'\n'+JSON.stringify(assessment,null,2).split('\n').map(l=>'+'+l).join('\n')+'\n';
const base='.momo/lifecycle/robot-agent-framework/';
const notes={
 'WORKLOG.md':'## 2026-09-07 模型调用与上下文独立子图\n\n按用户要求将既有 model-adapter 展开为「模型调用与上下文流转」，保留原主图关系，新增18个子节点、21条内部语义关系、18条包含关系和专用画布。说明配置、调用方法、片段预算、HTTP、结果校验，以及问答历史/规划证据/任务状态的不同用途。连续会话、摘要检索和重规划预算继承明确为开放缺口。\n\n正式图 revision 15→16：37对象、74关系（38语义＋36包含）。21条新增关系通过确定性证据校验；原3处落后指纹核对后刷新。最终无孤立对象、无无效关系、无过期证据。没有修改模型运行代码，也未发起新的模型调用。细节见 docs/MODEL_CONTEXT_FLOW.md。',
 'DECISIONS.md':'## 2026-09-07 模型流转图范围\n\nConfirmed（用户请求）：在现有单一项目内独立展示模型调用和上下文流转；沿用 model-adapter 作为容器，不另建项目、不迁移原节点或删除旧关系。Confirmed（代码）：UI 历史不自动进提示词；自动重规划仅注入选定任务状态。未实现的连续会话、摘要检索和预算继承修复只记录，不声称已接通。',
 'UNKNOWNS.md':'## 2026-09-07 模型上下文具体缺口\n\n代码确认：尚无 session_id 与跨轮消息维护；没有自动摘要、滑动窗口或记忆检索注入；单个必需重规划上下文超预算直接失败。Runtime 持久化 model_config 未保留 max_input_tokens/max_output_tokens，自定义预算在自动重规划时回到默认值。独立子图以3个 open 节点追踪；未改变原问题台账编号和关闭状态。',
 'HANDOFF.md':'## 2026-09-07 模型上下文图交接\n\n当前正式图 revision 16。刷新 Momo 后进入「模型调用与上下文流转」（model-adapter）查看独立画布及节点详情。新增18子节点、21语义关系；未实现项标为 open。docs/MODEL_CONTEXT_FLOW.md 给出图例和代码来源。下一步实现仍需按用户指示选择；本次仅细化结构与证据。',
 'PROJECT.md':'## 模型调用与上下文子图（2026-09-07）\n\n正式图 revision 16，在原 model-adapter 对象内独立展开18个细项。包含调用主链、三类历史和重规划回流，以及连续会话/摘要检索/预算继承3项开放缺口。详见 docs/MODEL_CONTEXT_FLOW.md；项目边界与运行能力未改变。'
};
for(const [name,note]of Object.entries(notes)){
 const file=base+name,old=fs.readFileSync(file,'utf8').trimEnd(),tail=old.split('\n').slice(-4);
 patch+='*** Update File: '+path.resolve(file)+'\n@@\n'+tail.map(l=>' '+l).join('\n')+'\n'+('\n'+note+'\n').split('\n').map(l=>'+'+l).join('\n')+'\n';
}
process.stdout.write(patch+'*** End Patch\n');
