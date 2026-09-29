"""Environment model plans a real remotely executed, fenced file copy."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

import pytest
import httpx

from robot_agent.actions import Actions, local_principal, process_commands
from robot_agent.model_transport import environment_config
from robot_agent.runtime import Runtime
from robot_agent.service import skill_server
from robot_agent.store import Store


@pytest.mark.live_model
@pytest.mark.parametrize('reconcile', [False, True], ids=['complete', 'reconcile'])
def test_real_model_fenced_http_execution(reconcile):
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('requires explicit real model invocation')
    root = (Path('.runtime/fencing-validation') / str(uuid.uuid4())).resolve(); root.mkdir(parents=True)
    source, target = root / 'source.md', root / 'copy.md'
    source.write_bytes(Path('docs/SKILL_PROTOCOL.md').read_bytes())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    service_store = Store(root / 'service')
    service_runtime = Runtime(service_store); service_runtime.install_local_skills([str(root)])
    local = {**service_runtime.catalog()['file.copy'], 'fencing_domain': 'disk'}
    service_runtime.register('file.copy', local)
    server = skill_server(service_store)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    store = Store(root / 'client'); runtime = Runtime(store)
    runtime.register('file.copy', {**local, 'adapter': 'http', 'endpoint': f'http://127.0.0.1:{server.server_port}', 'resources': {'disk': 1}})
    store.set_capacity('r1/disk', 1)
    actions = Actions(store)
    def call(name, args):
        return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
    report = {'configured_model': environment_config()['model'], 'mock_used': False, 'simulation_used': False,
              'expected_sha256': digest, 'scenario': 'reconcile' if reconcile else 'complete'}
    try:
        session = call('session.create', {'robot_id': 'r1', 'goal':
            f'用已注册的 file.copy 将实际文件 {source} 复制到 {target}。目标不存在，父目录存在且可写。'
            '仅需一个步骤，chunk_bytes=512。该技能已注册为 verifier，会实际核验复制字节完整性，最终验证就是该复制步骤。'
            '不涉及机器人运动，不需要其他技能或澄清。'})['session']
        session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
        version = {'session_id': session['id'], 'expected_revision': session['revision']}
        draft = call('plan.propose', version)['draft']
        assert len(draft['plan']['steps']) == 1
        step = draft['plan']['steps'][0]
        assert step['skill'] == 'file.copy' and step['args'] == {'source': str(source), 'target': str(target), 'chunk_bytes': 512}
        receipt = call('plan.submit', {**version, 'draft_id': draft['id'], 'plan_hash': draft['plan_hash']})
        if reconcile:
            process_commands(store)
            task = runtime.tick(receipt['task_id'])
            assert task['status'] == 'running' and target.stat().st_size == 512
            old_id = task['steps'][step['id']]['execution_id']
            original = service_store.get('service_requests', old_id)['body']
            takeover = {**original, 'execution_id': 'current-controller',
                'authority': {'domain': 'disk', 'token': 2},
                'args': {**original['args'], 'target': str(root / 'takeover.md')}}
            headers = {'X-Execution-Authority': json.dumps(takeover['authority'])}
            with httpx.Client(trust_env=False) as client:
                base = f'http://127.0.0.1:{server.server_port}/executions/'
                accepted = client.put(base + takeover['execution_id'], json=takeover, headers=headers)
                assert accepted.status_code == 200
                task = runtime.tick(task['id'])
                assert task['status'] == 'unknown' and store.leases()
                call('task.cancel', {'task_id': task['id'], 'expected_revision': task['revision'],
                    'expected_generation': task['generation']})
                stopped = client.post(base + old_id + '/reconcile', headers=headers)
                assert stopped.status_code == 200
                report['reconciled_result'] = stopped.json()
        worker = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root),
            'run', '--until', receipt['task_id']], capture_output=True, text=True, timeout=60)
        assert worker.returncode == 0, worker.stderr
        task = store.get('tasks', receipt['task_id'])
        assert task['status'] == ('canceled' if reconcile else 'succeeded')
        execution = store.get('executions', task['steps'][step['id']]['execution_id'])
        remote = service_store.get('service_requests', execution['id'])
        assert execution['authority'] == remote['body']['authority'] == {'domain': 'disk', 'token': 1}
        assert execution['result']['authority'] == execution['authority']
        if reconcile:
            assert execution['result'] == report['reconciled_result']
            assert execution['result']['status'] == 'canceled' and execution['result']['quiescent']
            assert execution['result']['output']['bytes_copied'] == 512
            assert target.read_bytes() == source.read_bytes()[:512]
            assert execution['result']['reconciliation']['authority'] == {'domain': 'disk', 'token': 2}
            assert (root / 'takeover.md').stat().st_size == 512
        else:
            assert execution['result']['output']['sha256'] == digest == hashlib.sha256(target.read_bytes()).hexdigest()
        assert not store.leases()
        models = store.list('model_responses')
        assert all(r['status'] == 'validated' and r['raw'] and r['response_id'] for r in models)
        report.update(status='passed', task_id=task['id'], task_status=task['status'], plan=draft['plan'], execution=execution,
            service_request=remote, model_records=[{k: r.get(k) for k in ('id', 'method', 'actual_model', 'response_id', 'context_bundle_id')} for r in models])
    except Exception as exc:
        report.update(status='failed', error=type(exc).__name__ + ': ' + str(exc)); raise
    finally:
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('actual fencing report:', root / 'report.json')
        server.shutdown(); server.server_close(); thread.join(); service_store.close(); store.close()
