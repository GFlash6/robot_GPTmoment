"""Real model context -> exact plan -> boundary rejection and actual stored-byte verification."""
import copy
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
from robot_agent.context_codec import decode_bundle
from robot_agent.context_memory import record_hash
from robot_agent.contracts import ContractError
from robot_agent.memory import Memory
from robot_agent.model_call import ModelCaller
from robot_agent.model_transport import environment_config
from robot_agent.runtime import Runtime
from robot_agent.store import Store


@pytest.mark.live_model
def test_real_model_bound_asset_lifecycle_and_actual_verification():
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('requires explicit real model invocation')
    config = environment_config()
    root = (Path('.runtime/asset-binding-validation') / str(uuid.uuid4())).resolve()
    root.mkdir(parents=True)
    store = Store(root / 'ledger')
    runtime = Runtime(store)
    runtime.install_local_skills([str(root)])
    asset = Memory(store).ingest(Path('docs/SKILL_PROTOCOL.md'),
        {'kind': 'document', 'encoding': 'utf8', 'source': 'actual-project-protocol', 'robot_id': 'r1'})
    blob = Path(asset['path']); original_bytes = blob.read_bytes()
    expected = hashlib.sha256(original_bytes).hexdigest()
    actions = Actions(store)
    def call(name, args):
        return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
    def apply_commands():
        child = subprocess.run([sys.executable, '-c',
            'import sys; from robot_agent.store import Store; from robot_agent.actions import process_commands; '
            'store=Store(sys.argv[1]); process_commands(store); store.close()', str(store.root)],
            capture_output=True, text=True, timeout=30)
        assert child.returncode == 0, child.stderr
    report = {'root': str(root), 'mock_used': False, 'simulation_used': False,
              'configured_model': config['model'], 'asset_id': asset['id'], 'expected_sha256': expected,
              'boundaries': [], 'model_records': []}
    started = time.monotonic()
    try:
        session = call('session.create', {'robot_id': 'r1', 'max_replans': 1, 'goal':
            '核验本会话附加的唯一已归档文档资产。它已由系统实际读取并绑定版本，资产 ID 与预期 SHA256 '
            '取自 asset-evidence 上下文，不要猜测、不重新归档、不操作原始文件路径。'
            '只需一个已注册的 asset.verify-set 步骤，items 为该资产的 asset_id 和保存的 sha256；'
            '该步骤即最终 verification，直接读取归档字节并核验预期哈希。robot_id=r1 只是数据命名空间，不涉及物理机器人。'
            '没有待消歧的对象或位置，不需要额外的探测步骤。'})['session']
        session = call('session.attach-assets', {'session_id': session['id'], 'expected_revision': session['revision'],
                                               'asset_ids': [asset['id']]})['session']
        report['binding'] = session['asset_bindings'][0]
        assert report['binding']['record_hash'] == record_hash(asset)
        session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
        assert session['analysis']['status'] == 'ready', session['analysis']
        version = {'session_id': session['id'], 'expected_revision': session['revision']}
        def propose():
            draft = call('plan.propose', version)['draft']
            plan = draft['plan']
            assert len(plan['steps']) == 1 and plan['verification'] == plan['steps'][0]['id']
            final = plan['steps'][0]
            assert final['skill'] == 'asset.verify-set'
            assert final['args'] == {'items': [{'asset_id': asset['id'], 'sha256': expected}]}
            snapshot = store.get('planning_contexts', draft['context_snapshot_id'])
            assert snapshot['session']['asset_bindings'] == session['asset_bindings']
            return draft
        def submit(draft):
            return call('plan.submit', {**version, 'draft_id': draft['id'], 'plan_hash': draft['plan_hash']})

        first = propose()
        edited = copy.deepcopy(asset); edited['metadata']['source'] = 'actual metadata edit after planning'
        store.put('assets', asset['id'], edited)
        count = len(store.list('model_responses'))
        with pytest.raises(ContractError, match='bound asset record changed'):
            submit(first)
        assert not store.list('commands') and not store.list('executions')
        assert len(store.list('model_responses')) == count
        report['boundaries'].append('metadata change after actual planning blocks submit without a new model call')
        store.put('assets', asset['id'], asset)
        receipt = submit(first)
        store.put('assets', asset['id'], edited)
        apply_commands()
        command = store.get('commands', receipt['command_id'])
        assert command['status'] == 'rejected' and 'bound asset record changed' in command['error']['message']
        assert store.get('tasks', receipt['task_id']) is None and not store.list('executions')
        report['rejected_command'] = {'id': command['id'], 'status': command['status'], 'error': command['error']}
        report['boundaries'].append('independent process rejects changed asset before creating task')
        store.put('assets', asset['id'], asset)

        second = propose()
        receipt = submit(second)
        apply_commands()
        assert store.get('commands', receipt['command_id'])['status'] == 'applied'
        assert store.get('tasks', receipt['task_id'])['status'] == 'queued'
        blob.write_bytes(original_bytes + b'\nActual bound-blob corruption before dispatch.')
        failed = runtime.tick(receipt['task_id'])
        assert failed['status'] == 'replanning' and not store.list('executions')
        assert any(e['type'] == 'context_rejected' for e in store.events(failed['id']))
        count = len(store.list('model_responses'))
        failed = runtime.recover_plan(failed['id'])
        assert failed['status'] == 'failed' and len(store.list('model_responses')) == count
        assert any(e['type'] == 'replan_rejected' and 'asset integrity failed' in e['data'] for e in store.events(failed['id']))
        assert not store.list('executions') and not store.db.execute('SELECT * FROM leases').fetchall()
        report['rejected_task'] = {'id': failed['id'], 'status': failed['status'], 'steps': failed['steps']}
        report['boundaries'].append('actual blob corruption after acceptance blocks dispatch and recovery without any external skill call')
        blob.write_bytes(original_bytes)

        third = propose()
        receipt = submit(third)
        worker = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root),
                                 'run', '--until', receipt['task_id']], capture_output=True, text=True, timeout=60)
        assert worker.returncode == 0, worker.stderr
        task = store.get('tasks', receipt['task_id'])
        assert task['status'] == 'succeeded'
        final = task['steps'][task['plan']['verification']]['result']
        assert final['status'] == 'succeeded' and final['quiescent'] and final['evidence']
        assert final['output']['verified'] and final['output']['count'] == 1
        assert final['output']['items'] == [{'asset_id': asset['id'], 'sha256': expected, 'size': len(original_bytes)}]
        assert hashlib.sha256(Memory(store).read(asset['id'])).hexdigest() == expected
        assert len(store.list('executions')) == 1
        report.update(task_id=task['id'], actual_result=final)
        report['boundaries'].append('fresh actual model plan completes in independent worker with exact bound bytes and expected hash')

        records = store.list('model_responses')
        assert len(records) == 4
        for record in records:
            assert record['status'] == 'validated' and record['raw'] and record['actual_model'] and record['response_id']
            assert json.loads(record['raw'])['id'] == record['response_id']
            wire = store.get('context_bundles', record['context_bundle_id'])
            assert record_hash(wire) == record['context_bundle_hash']
            bundle = decode_bundle(wire)
            fragment = next(f for f in bundle.fragments if f.id == 'asset-evidence')
            assert fragment.metadata['asset_bindings'] == session['asset_bindings']
            assert fragment.content[0]['id'] == asset['id'] and fragment.content[0]['sha256'] == expected
            assert expected in json.dumps(record['request']['messages'])
            manifest = store.get('context_manifests', record['context_manifest_id'])
            assert 'asset-evidence' in manifest['included']
            if record['method'] == 'planning':
                arguments = {'goal': record['goal'], 'skills': next(f.content for f in bundle.fragments if f.id == 'capabilities')}
            else:
                arguments = record['preparation']['arguments']
            rebuilt = ModelCaller(config).prepare(record['method'], arguments, context=bundle.fragments)
            assert list(rebuilt.request.messages) == record['request']['messages']
            assert rebuilt.request.response_format == record['request']['response_format']
            assert rebuilt.allocation.as_dict() == record['context_allocation']
            report['model_records'].append({k: record[k] for k in ('id', 'method', 'actual_model', 'response_id', 'context_bundle_hash')} |
                {'request_sha256': record_hash(record['request']), 'raw_sha256': hashlib.sha256(record['raw'].encode()).hexdigest(),
                 'exact_input_reconstruction': True})
        report['status'] = 'passed'
    except Exception as exc:
        report.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        # Isolated fault injection must not leave stored bytes or metadata damaged.
        blob.write_bytes(original_bytes); store.put('assets', asset['id'], asset)
        report['elapsed_seconds'] = time.monotonic() - started
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print('actual asset binding report:', root / 'report.json')
        store.close()
