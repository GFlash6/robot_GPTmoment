"""Actual model recovery from an actual byte mismatch under a frozen contract."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from robot_agent.actions import Actions, local_principal, process_commands
from robot_agent.context_codec import decode_bundle
from robot_agent.context_memory import record_hash
from robot_agent.memory import Memory
from robot_agent.model_call import ModelCaller
from robot_agent.model_transport import environment_config
from robot_agent.runtime import Runtime
from robot_agent.store import Store


@pytest.mark.live_model
def test_actual_model_recovers_completion_mismatch_without_weakening_contract():
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('requires explicit actual model invocation')
    config = environment_config()
    root = (Path('.runtime/completion-recovery-validation') / str(uuid.uuid4())).resolve()
    root.mkdir(parents=True)
    primary, backup = root / 'primary.md', root / 'backup.md'
    original = Path('docs/SKILL_PROTOCOL.md').read_bytes()
    primary.write_bytes(original)
    backup.write_bytes(original)
    expected = hashlib.sha256(original).hexdigest()
    contract = {'schema_version': 1, 'verifier_skill': 'asset.verify', 'checks': [
        {'id': 'expected-hash', 'path': 'sha256', 'op': 'eq', 'value': expected},
        {'id': 'expected-size', 'path': 'size', 'op': 'eq', 'value': len(original)},
        {'id': 'integrity', 'path': 'verified', 'op': 'eq', 'value': True}]}
    store = Store(root / 'ledger')
    runtime = Runtime(store)
    runtime.install_local_skills([str(root)])
    actions = Actions(store)
    def call(name, args):
        return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
    report = {'configured_model': config['model'], 'mock_used': False, 'simulation_used': False,
              'contract': contract, 'model_records': [], 'operator_read_hashes': {
                  str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (primary, backup)}}
    started = time.monotonic()
    try:
        session = call('session.create', {'robot_id': 'r1', 'max_replans': 1, 'goal':
            f'归档协议文档并验证操作者要求的原始字节。主文件是 {primary}，授权备用文件是 {backup}。'
            f'操作者刚刚实际读取两者，SHA256 均为 {expected}，大小均为 {len(original)}。'
            '首次计划必须仅用主文件执行 file.ingest，再用 asset.verify 引用该步骤实际 asset_id；不要添加 fallback。'
            '如果执行后实际完成契约检查失败，允许重规划改用备用文件重新 file.ingest，再 asset.verify。'
            '每次计划均为这两个步骤，metadata 使用 kind=document、encoding=utf8、source=completion-recovery。'
            '验收必须保持原哈希、大小和 verified=true，不能通过接受已变化的主文件放宽要求。'
            '无需修改任何文件或另加探测技能，不涉及机器人运动。完成契约通过独立上下文提供，勿写进模型计划。'})['session']
        session = call('session.completion-contract', {'session_id': session['id'],
            'expected_revision': session['revision'], 'contract': contract})['session']
        session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
        assert not session['analysis']['questions'], session['analysis']
        version = {'session_id': session['id'], 'expected_revision': session['revision']}
        draft = call('plan.propose', version)['draft']
        def check_plan(plan, path):
            assert len(plan['steps']) == 2 and 'completion_contract' not in plan
            ingest = next(s for s in plan['steps'] if s['skill'] == 'file.ingest')
            verifier = next(s for s in plan['steps'] if s['id'] == plan['verification'])
            assert ingest['args']['path'] == str(path) and not ingest.get('fallback')
            assert verifier['skill'] == 'asset.verify'
            assert verifier['args'] == {'asset_id': {'$ref': ingest['id'] + '.asset_id'}}
            return ingest
        first = check_plan(draft['plan'], primary)
        receipt = call('plan.submit', {**version, 'draft_id': draft['id'], 'plan_hash': draft['plan_hash']})
        process_commands(store)
        primary.write_bytes(original + b'\nActual edit after accepted planning.\n')
        changed = hashlib.sha256(primary.read_bytes()).hexdigest()
        deadline = time.monotonic() + 30
        task = store.get('tasks', receipt['task_id'])
        while task['status'] not in {'failed', 'replanning', 'succeeded'} and time.monotonic() < deadline:
            task = runtime.tick(task['id'])
            time.sleep(0.02)
        assert task['status'] == 'replanning', task
        failed = task['steps'][task['plan']['verification']]['result']
        assert task['steps'][first['id']]['status'] == 'succeeded'
        assert failed['reported_status'] == 'succeeded' and failed['output']['verified'] is True
        assert failed['output']['sha256'] == changed and failed['quiescent'] and failed['evidence']
        evaluation = failed['completion_evaluation']
        assert {c['id'] for c in evaluation['checks'] if c['status'] == 'failed'} == {'expected-hash', 'expected-size'}
        report['actual_failure'] = task
        # Change the current session, not the accepted task. Recovery must use its frozen contract.
        call('session.completion-contract', {**version, 'contract': None})
        recovered = runtime.recover_plan(task['id'])
        report['recovery_task'] = recovered
        assert recovered['status'] == 'queued' and recovered['revision'] == 1, recovered
        second = check_plan(recovered['plan'], backup)
        assert recovered['completion_contract'] == contract
        response = store.get('model_responses', recovered['model_response_id'])
        bundle = decode_bundle(store.get('context_bundles', response['context_bundle_id']))
        differences = next(f for f in bundle.fragments if f.id == 'completion-evaluation')
        assert differences.authority == 'data' and differences.required
        assert differences.content == evaluation
        manifest = store.get('context_manifests', response['context_manifest_id'])
        assert manifest['phase'] == 'replanning'
        assert {'completion-contract', 'completion-evaluation', 'task-state'} <= set(manifest['included'])
        assert changed in json.dumps(response['request']['messages'])
        worker = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root),
            'run', '--until', task['id']], capture_output=True, text=True, timeout=60)
        assert worker.returncode == 0, worker.stderr
        final = store.get('tasks', task['id'])
        result = final['steps'][final['plan']['verification']]['result']
        assert final['status'] == 'succeeded' and final['replans'] == 1
        assert final['completion_contract_hash'] == record_hash(contract)
        assert result['completion_evaluation']['status'] == 'passed'
        assert result['output']['sha256'] == expected and result['quiescent'] and result['evidence']
        asset_id = final['steps'][second['id']]['result']['output']['asset_id']
        assert Memory(store).read(asset_id) == original
        assert hashlib.sha256(primary.read_bytes()).hexdigest() == changed
        assert backup.read_bytes() == original
        assert not store.db.execute('SELECT * FROM leases').fetchall()
        report['final_task'] = final
        records = store.list('model_responses')
        assert len(records) == 3
        for record in records:
            assert record['status'] == 'validated' and record['actual_model'] and record['response_id']
            assert json.loads(record['raw'])['id'] == record['response_id']
            wire = store.get('context_bundles', record['context_bundle_id'])
            assert record_hash(wire) == record['context_bundle_hash']
            context = decode_bundle(wire)
            requirement = next(f for f in context.fragments if f.id == 'completion-contract')
            assert requirement.required and requirement.authority == 'operator'
            assert requirement.content['contract'] == contract
            arguments = record.get('preparation', {}).get('arguments')
            if record['method'] == 'planning':
                arguments = {'goal': record['goal'], 'skills': next(f.content for f in context.fragments if f.id == 'capabilities')}
            rebuilt = ModelCaller(config).prepare(record['method'], arguments, context=context.fragments)
            assert list(rebuilt.request.messages) == record['request']['messages']
            assert rebuilt.request.response_format == record['request']['response_format']
            assert rebuilt.allocation.as_dict() == record['context_allocation']
            report['model_records'].append({k: record[k] for k in ('id', 'method', 'response_id', 'actual_model', 'context_bundle_hash')} |
                {'request_sha256': record_hash(record['request']), 'raw_sha256': hashlib.sha256(record['raw'].encode()).hexdigest(),
                 'exact_input_reconstruction': True})
        report['status'] = 'passed'
    except Exception as exc:
        report.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        report['elapsed_seconds'] = time.monotonic() - started
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print('actual completion recovery report:', root / 'report.json')
        store.close()
