"""Real model plans a seven-node file workflow; every output is independently read."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from robot_agent.actions import Actions, local_principal
from robot_agent.memory import Memory
from robot_agent.model_transport import environment_config
from robot_agent.runtime import Runtime
from robot_agent.store import Store


@pytest.mark.live_model
def test_real_model_multifile_copy_archive_and_collective_verification():
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('requires explicit real model invocation')
    root = (Path('.runtime/multifile-validation') / str(uuid.uuid4())).resolve()
    root.mkdir(parents=True)
    inputs = []
    for name in ('SKILL_PROTOCOL.md', 'ARCHITECTURE.md', 'CONTEXT_PROVIDERS.md'):
        data = (Path('docs') / name).read_bytes()
        source, target = root / name, root / ('copied-' + name)
        source.write_bytes(data)
        inputs.append({'source': str(source), 'target': str(target), 'sha256': hashlib.sha256(data).hexdigest()})
    store = Store(root / 'ledger')
    Runtime(store).install_local_skills([str(root)])
    actions = Actions(store)
    def call(name, args):
        return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
    report = {'configured_model': environment_config()['model'], 'mock_used': False,
              'simulation_used': False, 'inputs': inputs, 'scenario': 'three_file_copy_archive_set_verification'}
    started = time.monotonic()
    try:
        session = call('session.create', {'robot_id': 'r1', 'goal':
            '处理以下三个真实文件：分别用 file.copy 复制到指定 target，再用 file.ingest 归档复制后的文件。'
            '归档 path 必须引用对应复制步骤的 path 输出，metadata 为 kind=document、encoding=utf8、robot_id=r1、source=batch-archive。'
            '最后用一个 asset.verify-set 统一核验全部三个归档资产；asset_id 引用对应归档输出，sha256 使用清单给定的预期值，不引用执行输出的哈希。'
            '共七个步骤，每个文件的归档依赖它的复制，最终核验直接依赖全部归档步骤。'
            '目标文件尚不存在，父目录已创建，归档位置已配置，不涉及机器人运动，无需澄清。实际文件清单：' + json.dumps(inputs)})['session']
        session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
        version = {'session_id': session['id'], 'expected_revision': session['revision']}
        draft = call('plan.propose', version)['draft']
        plan = draft['plan']; report['plan'] = plan
        assert len(plan['steps']) == 7
        copies = [s for s in plan['steps'] if s['skill'] == 'file.copy']
        ingests = [s for s in plan['steps'] if s['skill'] == 'file.ingest']
        final = next(s for s in plan['steps'] if s['id'] == plan['verification'])
        assert len(copies) == len(ingests) == 3 and final['skill'] == 'asset.verify-set'
        assert set(final['deps']) == {s['id'] for s in ingests}
        assert len(final['args']['items']) == 3
        for item in inputs:
            copy = next(s for s in copies if s['args']['source'] == item['source'])
            assert copy['args']['target'] == item['target']
            ingest = next(s for s in ingests if s['args']['path'] == {'$ref': copy['id'] + '.path'})
            assert copy['id'] in ingest['deps']
            assert {'asset_id': {'$ref': ingest['id'] + '.asset_id'}, 'sha256': item['sha256']} in final['args']['items']
        response = store.get('model_responses', draft['model_response_id'])
        assert response['raw'] and response['actual_model'] and response['response_id']
        assert all(i['source'] in json.dumps(response['request']['messages']) for i in inputs)
        receipt = call('plan.submit', {**version, 'draft_id': draft['id'], 'plan_hash': draft['plan_hash']})
        worker = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root),
            'run', '--until', receipt['task_id']], capture_output=True, text=True, timeout=90)
        assert worker.returncode == 0, worker.stderr
        task = store.get('tasks', receipt['task_id'])
        assert task['status'] == 'succeeded' and all(s['status'] == 'succeeded' for s in task['steps'].values())
        actual = task['steps'][plan['verification']]['result']
        assert actual['output']['count'] == 3 and actual['output']['verified']
        assert len(actual['evidence']) == 3
        assert {i['sha256'] for i in actual['output']['items']} == {i['sha256'] for i in inputs}
        for item in inputs:
            assert hashlib.sha256(Path(item['target']).read_bytes()).hexdigest() == item['sha256']
        for item in actual['output']['items']:
            assert hashlib.sha256(Memory(store).read(item['asset_id'])).hexdigest() == item['sha256']
        records = store.list('model_responses')
        assert all(r['status'] == 'validated' and r['raw'] and r['response_id'] for r in records)
        expected_events = [{**e, 'data': json.loads(e['data'])} for e in store.events(task['id'])]
        pages, events, cursor, upper = [], [], 0, None
        while True:
            args = {'task_id': task['id'], 'after_seq': cursor, 'limit': 2}
            if upper is not None:
                args['through_seq'] = upper
            page = call('task.events-page', args)
            assert call('task.events-page', {**args, 'through_seq': page['through_seq']}) == page
            pages.append(page); events.extend(page['events'])
            cursor, upper = page['next_seq'], page['through_seq']
            if not page['has_more']:
                break
        assert events == expected_events
        assert len([e for e in events if e['type'] == 'execution_result']) == 7
        assert store.list('model_responses') == records
        assert store.get('tasks', task['id']) == task
        report.update(status='passed', task_id=task['id'], actual_result=actual,
            event_pages={'page_count': len(pages), 'event_count': len(events), 'through_seq': upper,
                'exact_ledger_match': True, 'duplicate_reads_stable': True, 'pages': pages},
            step_results={k: v['result'] for k, v in task['steps'].items()},
            model_records=[{k: r.get(k) for k in ('id', 'method', 'actual_model', 'response_id', 'context_bundle_id', 'context_bundle_hash')} for r in records])
    except Exception as exc:
        report.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        report['elapsed_seconds'] = time.monotonic() - started
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('actual multifile report:', root / 'report.json')
        store.close()
