"""Prepare reviewed object/evidence updates; canonical writing stays revision guarded."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
now=datetime.now(timezone.utc).isoformat()
w=json.loads(Path('.momo/momo-workspace.json').read_text())
updates={
'project-robot-agent-framework':('应用协作、持久执行、上下文追溯与文件任务恢复已验证；真实世界状态、物理实体和真机闭环仍待接入。','docs/PROJECT_STATUS.md',['completion-recovery-live','action-idempotency-live','world-source-discovery']),
'kernel':('已有共享动作、控制命令、HTTP fencing 与显式停止协调的实际文件服务验证；物理设备隔离、停止与补偿仍待验收。','robot_agent/runtime.py',['fencing-live','fencing-reconciliation-live']),
'core-execution':('共享动作发现契约、任务/会话/自动化跨动作幂等已实现；实际 HTTP 并发、文件执行和旧账本回执兼容通过。设备端控制与物理停止未验收。','robot_agent/actions.py',['action-idempotency-live','fencing-reconciliation-live']),
'model-adapter':('持久会话、记忆检索、分块摘要、恢复预算和完整上下文追溯已接通并有真实模型证据；实时世界状态未接入。','robot_agent/sessions.py',['summary-context-live','completion-recovery-live']),
'model-flow-gap-session':('多轮会话、固定原文、分块摘要、自动预算、绑定资产/记忆和冻结提交快照已有真实验证；生产留存策略仍待完善。','robot_agent/sessions.py',['summary-context-live','asset-binding-live']),
'model-flow-gap-summary':('有来源的记忆检索、版本绑定、工作台选择、长历史分块摘要和恢复预算已完成限定场景验证；空间检索与实体合并仍待完成。','robot_agent/session_history.py',['summary-context-live','memory-browser-live']),
'model-flow-replan':('真实失败后的恢复继承冻结快照、契约与实际验收差异；模型改用授权备用文件并由独立 worker 核验原字节通过。通用和物理恢复仍未证明。','robot_agent/runtime.py',['completion-recovery-live']),
'model-flow-task-state':('权威任务版本、任务图与结果进入上下文；完成契约检查失败时单独以 data 片段保留实际逐项差异，供恢复使用。','robot_agent/context_providers.py',['completion-recovery-live']),
'model-flow-fragments':('Goal/Task/Fragment/Bundle 保留来源与权限；AssetBinding 固定归档字节和记录版本；独立操作者完成契约不可被模型计划改写。物理实体尚无绑定。','robot_agent/context_models.py',['asset-binding-live','completion-contract-live']),
'model-flow-plan-history':('模型调用保存实际请求、原始响应、Bundle/Manifest 与哈希；目标、规划、解释、摘要、自动诊断已有输入重建证据。','robot_agent/context_codec.py',['context-codec-live','summary-context-live','action-idempotency-live']),
'model-flow-manifest':('Manifest 保存纳入/丢弃来源、预算与诊断；完整上下文包和只读单记录/双记录视图已接通，哈希一致不等于模型正确。','robot_agent/context_evidence.py',['context-diff-browser-live','context-codec-live']),
'model-flow-config':('运行时使用环境中的实际模型和鉴权配置；近期证据为 qwen3.7-plus，qwen3.8-max 属历史记录，不将任一模型名当固定默认。','robot_agent/model_transport.py',['completion-recovery-live']),
'workflow-ui':('工作台控制、记忆/摘要、自动诊断、事件分页及上下文单记录/差异视图已有真实浏览器验证；远程认证与设备实时状态待完成。','ui/src/App.tsx',['context-diff-browser-live','automation-browser-live']),
'ui-validation':('实际账本浏览器验证覆盖上下文比较、来源、断连恢复与损坏证据；不同增量结果分别保留，UI 验证不证明真机完成。','docs/UI_VALIDATION.md',['context-diff-browser-live','summary-browser-live']),
'verification':('真实模型文件、多文件、摘要、失败诊断与完成契约恢复已有实际执行证据；当前 ROS 图仅检查节点诊断发布者，无设备闭环。','docs/VALIDATION.md',['multifile-live','completion-recovery-live','world-source-discovery']),
'software-validation':('按改动运行真实文件/HTTP/SQLite/进程回归；最新跨动作幂等回归25项、真实自动诊断1项通过。不是整个测试集或物理系统验收。','tests/test_action_idempotency.py',['action-idempotency-live']),
'questions':('问题台账已修正文件闭环、恢复与UI控制过时描述；设备连接、时间/坐标语义、物理停止和通用任务质量仍开放。','docs/OPEN_QUESTIONS.md',['world-source-discovery']),
'memory':('归档资产、记忆检索、来源版本绑定和摘要已具备；实时物体定位、空间融合、地图失效与容量策略仍待完善。','robot_agent/context_assets.py',['asset-binding-live','summary-context-live']),
'truth':('Runtime 独立执行冻结的操作者完成条件；技能成功但任务字节不匹配会失败，实际模型恢复仍保留原要求。物理验证指标待设备观测。','robot_agent/completion.py',['completion-contract-live','completion-recovery-live']),
}
for o in w['snapshot']['objects']:
 if o['id'] not in updates:continue
 summary,source,reports=updates[o['id']]
 evidence=[]
 for report in reports:
  p=Path('docs/validation')/(report+'.json');data=json.loads(p.read_text())
  assert data.get('status','').startswith(('passed','discovery_completed')),(p,data.get('status'))
  evidence.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'status':data['status']})
 o.update(summary=summary,updatedAt=now)
 o['properties'].update(evidenceStatus='Confirmed',source=source,sourceFingerprint=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
   verifiedIncrementEvidence=evidence,verificationScope='限定软件场景与已有实际证据；不代表整体或真机完成',lastEvidenceReview=now)
 if o['id']=='model-flow-gap-summary':o['title']='记忆检索、历史摘要与恢复预算'
 if o['id'] in {'project-robot-agent-framework','kernel','core-execution','model-adapter','verification','truth','memory'}:o['lifecycle']='in_progress'
 for content in w['snapshot']['contents']:
  if content.get('objectId')==o['id']:
   content.update(value=summary+'\n\n实际证据：\n'+'\n'.join(e['path'] for e in evidence),updatedAt=now)
Path('.momo/intake/verified-increments-candidate.json').write_text(json.dumps(w,ensure_ascii=False,indent=2)+'\n')
a=json.loads(Path('.momo/intake/relation-assessment.json').read_text());a['generatedAt']=now;a['baseRevision']=w['workspace']['revision']
replacements={
'goal-analysis-drives-clarification':['robot_agent/goal_analysis.py','docs/validation/goal-context-live.json'],
'goal-analysis-feeds-planning':['robot_agent/sessions.py','docs/validation/completion-recovery-live.json'],
' task-state-feeds-builder'.strip():['robot_agent/context_providers.py','robot_agent/context_builder.py','docs/validation/completion-recovery-live.json'],
'context-builder-feeds-allocation':['robot_agent/planner.py','robot_agent/model_call.py','docs/validation/context-codec-live.json'],
'manifest-persists-with-plan-history':['robot_agent/planner.py','docs/validation/context-codec-live.json'],
'persistent-session-drives-analysis':['robot_agent/sessions.py','docs/validation/goal-context-live.json'],
'verified-memory-feeds-context':['robot_agent/context_providers.py','docs/validation/memory-context-live.json']}
for project in a['projects']:
 for c in project['candidates']:
  if c['action']=='remove':continue # Preserve pending historical removal and its old evidence; no implied approval.
  paths=replacements.get(c['claimKey'],[e['path'] for e in c['evidence']])
  c['evidence']=[{'sourceId':path,'path':path,'fingerprint':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
    'claim':c['claimKey'],'authority':'repository','observedAt':now} for path in paths]
Path('.momo/intake/verified-increments-relations.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
print('candidate revision',w['workspace']['revision'],'updated objects',len(updates),'relations preserved',len(w['snapshot']['relations']))
