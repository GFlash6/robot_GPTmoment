import copy,hashlib,json
from pathlib import Path
from datetime import datetime,timezone
root=Path('.')
canonical=Path('.momo/momo-workspace.json')
w=json.loads(canonical.read_text()); now=datetime.now(timezone.utc).isoformat()
updates={
'core-execution':('任务执行与控制权','in_progress','共享动作和权限范围、持久幂等命令、任务锁及原子回执已实现；实际文件、HTTP、进程故障和取消竞争验证通过。控制端 fencing、真机停止和补偿仍未验收。','robot_agent/actions.py'),
'model-adapter':('模型调用与上下文流转','in_progress','已接通持久会话、多轮目标分析、选择对象、实际资产证据、草稿及模型原始输入/响应。当前环境 qwen3.7-plus 的实际文件规划执行闭环通过；长程摘要、通用检索与实时世界状态未完成。','robot_agent/sessions.py'),
'model-flow-gap-session':('持久会话与多轮目标完善','in_progress','已实现 session_id、用户隔离、消息持久化、版本检查、澄清回填、资产引用与草稿关联；通过真实模型多轮验证。长程摘要、历史窗口与生产留存策略仍待完善。','robot_agent/sessions.py'),
'workflow-ui':('解耦流程观察与任务协作 UI','in_progress','保留只读观察界面，新增独立应用动作服务与协作工作台。实际浏览器完成节点解释、模型计划提交和真实文件任务；远程认证和设备状态展示未完成。','ui/src/Workbench.tsx'),
'verification':('实际 AI 与机器人技能联调','in_progress','qwen3.7-plus 实际目标分析、文件计划与 worker 执行、哈希核验、多轮澄清和失败节点解释通过。当前 ROS2 只有诊断主题，真机动作与实时传感器仍未验收。','docs/validation/application-layer-2026-09-22.json')}
for o in w['snapshot']['objects']:
 if o['id'] in updates:
  title,lifecycle,summary,source=updates[o['id']];o.update(title=title,lifecycle=lifecycle,summary=summary,updatedAt=now)
  o['properties'].update(source=source,implementationStatus='partial',validationSource='docs/validation/application-layer-2026-09-22.json')
  if 'configuredModel' in o['properties']:o['properties']['configuredModel']='qwen3.7-plus (environment, 2026-09-22)'
  if 'latestModelValidation' in o['properties']:o['properties']['latestModelValidation']='docs/validation/application-layer-2026-09-22.json'
 for field in ['source','validationSource']:
  source=o.get('properties',{}).get(field)
  if source and Path(source).is_file() and (field+'Fingerprint' in o['properties'] or o['id'] in updates):
   o['properties'][field+'Fingerprint']=hashlib.sha256(Path(source).read_bytes()).hexdigest()
for c in w['snapshot']['contents']:
 if c.get('objectId') in ['model-adapter','model-flow-gap-session']:
  c['value']=updates[c['objectId']][2]+'\n\n当前实现与范围：docs/APPLICATION_LAYER.md\n实际验收：docs/validation/application-layer-2026-09-22.json\n历史 Session→QA history 依赖不再表示当前实现，已列为待移除提案，未自动删除。'
  c['updatedAt']=now
w['workspace']['updatedAt']=now
Path('.momo/intake/application-layer-candidate.json').write_text(json.dumps(w,ensure_ascii=False,indent=2)+'\n')
print('expected_revision',w['workspace']['revision'])
