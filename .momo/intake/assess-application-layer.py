import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
w=json.loads(Path('.momo/momo-workspace.json').read_text());a=json.loads(Path('.momo/intake/relation-assessment.json').read_text())
now=datetime.now(timezone.utc).isoformat();a.update(baseRevision=w['workspace']['revision'],generatedAt=now)
p=a['projects'][0]
for c in p['candidates']:
 for e in c['evidence']:
  if e['path']=='tests/test_goal_analysis.py':e['sourceId']=e['path']='tests/test_application_live.py'
  if c['claimKey']=='goal-analysis-feeds-planning' and e['path']=='robot_agent/runtime.py':e['sourceId']=e['path']='robot_agent/sessions.py'
  if Path(e['path']).is_file():e['fingerprint']=hashlib.sha256(Path(e['path']).read_bytes()).hexdigest();e['observedAt']=now
for claim,source,target,files in [
 ('persistent-session-supplies-context','model-flow-gap-session','model-flow-context-builder',['robot_agent/sessions.py','robot_agent/context_builder.py']),
 ('persistent-session-drives-analysis','model-flow-gap-session','model-flow-goal-analysis',['robot_agent/sessions.py','tests/test_application_live.py'])]:
 key='relation-'+hashlib.sha256('\0'.join([p['projectKey'],source,target,claim]).encode()).hexdigest()[:16]
 p['candidates'].append({'claimKey':claim,'action':'add','confidence':'high','confirmedDecision':False,'relation':{'key':key,'sourceKey':source,'targetKey':target,'type':'supports'},
 'evidence':[{'sourceId':f,'path':f,'fingerprint':hashlib.sha256(Path(f).read_bytes()).hexdigest(),'claim':claim,'authority':'repository','observedAt':now} for f in files],
 'alternatives':[],'blockingReasons':[],'status':'proposed','changesBoundary':False,'changesOwnership':False,'changesPermission':False,'changesSafetyBoundary':False})
old=json.loads(Path('.momo/intake/model-context-assessment.json').read_text())['projects'][0]['candidates']
c=next(c for c in old if c['claimKey']=='session-needs-history-integration')
c.update(action='remove',status='proposed',confidence='high',confirmedDecision=False,blockingReasons=['历史计划依赖与当前独立 sessions 账本不符；保留移除提案，不自动删除。'])
c['evidence']=[{'sourceId':f,'path':f,'fingerprint':hashlib.sha256(Path(f).read_bytes()).hexdigest(),'claim':'当前会话使用 Store sessions 而不依赖 model-tests.sqlite','authority':'repository','observedAt':now} for f in ['robot_agent/sessions.py','robot_agent_observer/model_test.py']]
c.pop('autoEligible',None);c.pop('appliedAt',None)
p['candidates'].append(c)
p['graphHealth']['staleEvidenceRelationKeys']=['relation-a2b14ca51b2d1d23']
p['zeroRelationRationale']='当前会话与 ContextBuilder 和 GoalAnalyzer 有实际代码及真实模型验证；历史 QA history 依赖列为待清理。'
Path('.momo/intake/relation-assessment.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
print('base_revision',a['baseRevision'])
