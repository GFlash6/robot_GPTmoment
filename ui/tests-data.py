"""Create only actual local data operations for UI integration checks.

Uses an isolated directory chosen by the caller. Never creates robot or LLM results.
"""
import json
import sys
from pathlib import Path
from robot_agent.store import Store
from robot_agent.runtime import Runtime
from robot_agent.memory import Memory
root=Path(sys.argv[1]);source=Path(__file__).resolve().parent.parent/'docs/UI_DESIGN.md'
if (root/'ui-check-ids.json').exists():
    raise SystemExit('该目录已有验证记录；可直接复用运行浏览器检查，或为新验证选择一个空目录。')
s=Store(root);rt=Runtime(s);rt.install_local_skills([str(source.parent),str(root.resolve())])
def body(path):
    return {'steps':[{'id':'archive','skill':'file.ingest','args':{'path':str(path),'metadata':{'kind':'document','source':'ui-integration-source','encoding':'utf8','timestamp_ns':source.stat().st_mtime_ns}}},{'id':'verify','skill':'asset.verify','deps':['archive'],'args':{'asset_id':{'$ref':'archive.asset_id'}}}],'verification':'verify'}
completed=rt.submit(body(source),'local-files',goal='归档 UI 设计文档并校验完整性')['id'];rt.tick(completed)
fallback=body(source.parent/'absent-ui-check-input');fallback['steps'][0]['fallback']=[{'skill':'file.ingest','args':body(source)['steps'][0]['args']}]
recovered=rt.submit(fallback,'local-files',goal='验证缺失文件失败后的真实 fallback')['id'];rt.tick(recovered);rt.tick(recovered)
failed=rt.submit(body(source.parent/'absent-ui-check-input'),'local-files',goal='记录真实缺失输入错误')['id'];rt.tick(failed)
spec=rt.catalog()['file.copy'];spec['resources']={'archive-io':1};rt.register('file.copy',spec);s.set_capacity('local-files/archive-io',2)
copy=rt.submit({'steps':[{'id':'copy','skill':'file.copy','args':{'source':str(source),'target':str((root/'partial-copy').resolve()),'chunk_bytes':64}}],'verification':'copy'},'local-files',goal='检查分块归档取消后的停止证据')['id'];rt.tick(copy);rt.interrupt(copy,'pause');rt.tick(copy)
asset=s.get('tasks',completed)['steps']['archive']['result']['output']['asset_id']
Memory(s).remember('note','UI 集成验证使用的实际设计文档',{'purpose':'UI validation'},[asset])
(root/'ui-check-ids.json').write_text(json.dumps({'completed':completed,'recovered':recovered,'failed':failed,'paused':copy,'asset':asset}))
s.close()
