"""Genuine model plans and actual file results, including successful skill/wrong goal bytes."""
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
from robot_agent.model_call import ModelCaller
from robot_agent.model_transport import environment_config
from robot_agent.runtime import Runtime
from robot_agent.store import Store


@pytest.mark.live_model
def test_actual_model_completion_contract_accepts_and_rejects_real_outputs():
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('requires explicit real model invocation')
    config = environment_config()
    root = (Path('.runtime/completion-validation') / str(uuid.uuid4())).resolve(); root.mkdir(parents=True)
    store = Store(root / 'ledger'); Runtime(store).install_local_skills([str(root)])
    actions = Actions(store)
    original = Path('docs/SKILL_PROTOCOL.md').read_bytes()
    expected = hashlib.sha256(original).hexdigest()
    contract = {'schema_version': 1, 'verifier_skill': 'asset.verify', 'checks': [
        {'id': 'operator-expected-hash', 'path': 'sha256', 'op': 'eq', 'value': expected},
        {'id': 'operator-expected-size', 'path': 'size', 'op': 'eq', 'value': len(original)},
        {'id': 'actual-integrity', 'path': 'verified', 'op': 'eq', 'value': True}]}
    def call(name, args):
        return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
    report = {'configured_model': config['model'], 'mock_used': False, 'simulation_used': False,
              'contract': contract, 'contract_hash': record_hash(contract), 'cases': [], 'model_records': []}
    started = time.monotonic()
    try:
        for damage in (False, True):
            source = root / ('changed-after-plan.md' if damage else 'unchanged.md'); source.write_bytes(original)
            session = call('session.create', {'robot_id': 'r1', 'goal':
                f'归档实际文件 {source} 并核验归档字节。操作者已在规划前实际读取该文件。'
                '使用 file.ingest 读取这个路径，metadata 为 kind=document、encoding=utf8、source=completion-validation；'
                '后接一个 asset.verify，其 asset_id 必须引用归档步骤实际输出。这两个步骤足够，最终 verification 指向 asset.verify。'
                '操作者在独立 completion-contract 上下文中给出最终输出的预期哈希、大小和 verified 要求，执行框架将独立核对。'
                '不要把完成契约放进模型计划，不需要另一个 verify-set 或探测技能。仅本地文件操作，不涉及机器人运动。'})['session']
            session = call('session.completion-contract', {'session_id': session['id'], 'expected_revision': session['revision'],
                                                          'contract': contract})['session']
            session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
            assert session['analysis']['status'] in {'ready', 'needs_grounding'} and not session['analysis']['questions'], session['analysis']
            version = {'session_id': session['id'], 'expected_revision': session['revision']}
            draft = call('plan.propose', version)['draft']
            plan = draft['plan']; assert len(plan['steps']) == 2 and 'completion_contract' not in plan
            first = next(s for s in plan['steps'] if s['skill'] == 'file.ingest')
            last = next(s for s in plan['steps'] if s['id'] == plan['verification'])
            assert first['args']['path'] == str(source) and last['skill'] == 'asset.verify'
            assert last['args'] == {'asset_id': {'$ref': first['id'] + '.asset_id'}}
            receipt = call('plan.submit', {**version, 'draft_id': draft['id'], 'plan_hash': draft['plan_hash']})
            if damage:
                source.write_bytes(original + b'\nActual filesystem edit after model planning, before worker ingestion.')
            actual_source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            worker = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root),
                'run', '--until', receipt['task_id']], capture_output=True, text=True, timeout=60)
            assert worker.returncode == (1 if damage else 0), worker.stderr
            task = store.get('tasks', receipt['task_id'])
            result = task['steps'][plan['verification']]['result']
            assert task['completion_contract'] == contract and task['completion_contract_hash'] == record_hash(contract)
            assert task['steps'][first['id']]['status'] == 'succeeded'
            assert result['reported_status'] == 'succeeded' and result['output']['verified'] is True
            assert result['output']['sha256'] == actual_source_hash
            assert result['quiescent'] and result['evidence']
            check = result['completion_evaluation']
            assert check['contract_hash'] == record_hash(contract) and check['execution_id'] == result['execution_id']
            assert task['status'] == ('failed' if damage else 'succeeded')
            assert check['status'] == ('failed' if damage else 'passed')
            failed = {c['id'] for c in check['checks'] if c['status'] == 'failed'}
            assert failed == ({'operator-expected-hash', 'operator-expected-size'} if damage else set())
            from robot_agent.memory import Memory
            asset_id = task['steps'][first['id']]['result']['output']['asset_id']
            assert hashlib.sha256(Memory(store).read(asset_id)).hexdigest() == actual_source_hash
            assert not store.db.execute('SELECT * FROM leases').fetchall()
            report['cases'].append({'source_changed_after_planning': damage, 'task_id': task['id'],
                'task_status': task['status'], 'plan': plan, 'actual_source_sha256': actual_source_hash,
                'actual_result': result, 'asset_id': asset_id})

        records = store.list('model_responses'); assert len(records) == 4
        for record in records:
            assert record['status'] == 'validated' and record['raw'] and record['response_id'] and record['actual_model']
            assert json.loads(record['raw'])['id'] == record['response_id']
            wire = store.get('context_bundles', record['context_bundle_id'])
            assert record_hash(wire) == record['context_bundle_hash']
            bundle = decode_bundle(wire)
            completion = next(f for f in bundle.fragments if f.id == 'completion-contract')
            assert completion.required and completion.authority == 'operator' and completion.content['contract'] == contract
            manifest = store.get('context_manifests', record['context_manifest_id'])
            assert 'completion-contract' in manifest['included']
            assert expected in json.dumps(record['request']['messages'])
            arguments = record.get('preparation', {}).get('arguments')
            if record['method'] == 'planning':
                arguments = {'goal': record['goal'], 'skills': next(f.content for f in bundle.fragments if f.id == 'capabilities')}
            rebuilt = ModelCaller(config).prepare(record['method'], arguments, context=bundle.fragments)
            assert list(rebuilt.request.messages) == record['request']['messages']
            assert rebuilt.request.response_format == record['request']['response_format']
            assert rebuilt.allocation.as_dict() == record['context_allocation']
            report['model_records'].append({k: record[k] for k in ('id', 'method', 'actual_model', 'response_id', 'context_bundle_hash')} |
                {'request_sha256': record_hash(record['request']), 'raw_sha256': hashlib.sha256(record['raw'].encode()).hexdigest(),
                 'exact_input_reconstruction': True})
        report['status'] = 'passed'
    except Exception as exc:
        report.update(status='failed', error=type(exc).__name__ + ': ' + str(exc)); raise
    finally:
        report['elapsed_seconds'] = time.monotonic() - started
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print('actual completion report:', root / 'report.json'); store.close()
