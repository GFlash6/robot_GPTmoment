"""Live environment model consumes retrieved project documentation and executes it."""
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
@pytest.mark.parametrize('rejection', ['expired_memory', 'changed_snapshot'])
def test_actual_retrieved_memory_drives_model_plan_and_verified_file_execution(rejection):
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('requires explicit live model invocation')
    config = environment_config()
    root = Path('.runtime/memory-validation') / str(uuid.uuid4())
    root.mkdir(parents=True)
    original = Path('docs/SKILL_PROTOCOL.md')
    source = (root / 'skill-protocol.md').resolve()
    source.write_bytes(original.read_bytes())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    store = Store(root / 'ledger')
    Runtime(store).install_local_skills([str(root.resolve())])
    asset = Memory(store).ingest(source, {'kind': 'document', 'source': str(source), 'encoding': 'utf8', 'robot_id': 'r1'})
    memory = Memory(store).remember('document', 'project protocol archive: ' + original.read_text()[:500],
        {'robot_id': 'r1', 'source_file': str(source), 'source_sha256': digest}, [asset['id']])
    actions = Actions(store)
    principal = local_principal()
    def call(name, args):
        return actions.call(name, args, principal, idempotency_key=str(uuid.uuid4()))['result']
    report = {'configured_model': config['model'], 'source': str(original), 'expected_sha256': digest, 'memory_id': memory['id']}
    try:
        found = call('memory.search', {'text': 'project protocol archive', 'robot_id': 'r1'})['items']
        assert len(found) == 1 and found[0]['memory']['id'] == memory['id']
        session = call('session.create', {'robot_id': 'r1', 'goal': (
            '将绑定的 project protocol archive 文档记忆中 attributes.source_file 指向的实际文件归档，'
            '然后核验归档资产字节完整性。源路径及预期哈希从这条记忆读取，不要自行猜测。'
            '使用 file.ingest，metadata 为 kind=document、encoding=utf8、source=memory-selected-document、robot_id=r1；'
            '再用 asset.verify 校验实际返回的 asset_id，最终节点必须是 asset.verify。'
            '系统归档目录已配置，不需要另一个目标路径，不涉及机器人运动。记忆中引用的文档字节已经由服务端真实核验。'
        )})['session']
        session = call('session.attach-memories', {'session_id': session['id'], 'expected_revision': session['revision'],
            'memories': [{'memory_id': memory['id'], 'record_hash': found[0]['record_hash']}]})['session']
        session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
        version = {'session_id': session['id'], 'expected_revision': session['revision']}
        draft = call('plan.propose', version)['draft']
        ingestion = [s for s in draft['plan']['steps'] if s['skill'] == 'file.ingest']
        assert len(ingestion) == 1 and ingestion[0]['args']['path'] == str(source), draft['plan']
        response = store.get('model_responses', draft['model_response_id'])
        assert response['raw'] and response['actual_model'] and response['response_id']
        from robot_agent.context_codec import decode_bundle, encode_bundle
        from robot_agent.context_memory import record_hash
        from robot_agent.model_call import ModelCaller
        bundle_record = store.get('context_bundles', response['context_bundle_id'])
        assert record_hash(bundle_record) == response['context_bundle_hash']
        restored = decode_bundle(bundle_record)
        assert encode_bundle(restored) == bundle_record
        prepared = ModelCaller(config).prepare('planning',
            {'goal': response['goal'], 'skills': next(f.content for f in restored.fragments if f.id == 'capabilities')},
            context=restored.fragments)
        assert list(prepared.request.messages) == response['request']['messages']
        manifest = store.get('context_manifests', response['context_manifest_id'])
        memory_source = next(s for s in manifest['sources'] if s['id'] == 'memory:' + memory['id'])
        assert memory_source['evidence_ids'] == [asset['id']]
        assert memory_source['metadata']['record_hash'] == found[0]['record_hash']
        assert memory_source['metadata']['provider'] == 'memory'
        assert all(s['metadata']['provider_contract_version'] == 1 for s in manifest['sources'])
        diagnostics = {d['provider']: d for d in manifest['provider_diagnostics']}
        assert set(diagnostics) == {'goal-capabilities', 'task-state', 'session', 'memory', 'assets', 'selection'}
        assert diagnostics['memory']['status'] == 'collected'
        assert diagnostics['memory']['included'] == ['memory:' + memory['id']]
        assert diagnostics['memory']['dropped'] == []
        assert diagnostics['assets']['status'] == 'empty'
        assert diagnostics['assets']['fragment_ids'] == diagnostics['assets']['included'] == []
        assert {fid for d in diagnostics.values() for fid in d['included']} == set(manifest['included'])
        assert str(source) in json.dumps(response['request']['messages'])
        if rejection == 'changed_snapshot':
            from robot_agent.contracts import ContractError
            snapshot = store.get('planning_contexts', draft['context_snapshot_id'])
            assert snapshot['schema_version'] == 1 and draft['context_snapshot_hash']
            store.put('planning_contexts', snapshot['id'], {**snapshot, 'schema_version': 99})
            before = len(store.list('model_responses'))
            with pytest.raises(ContractError, match='unsupported planning snapshot version'):
                call('plan.submit', {**version, 'draft_id': draft['id'], 'plan_hash': draft['plan_hash']})
            assert not store.list('commands') and len(store.list('model_responses')) == before
            store.put('planning_contexts', snapshot['id'], snapshot)
        receipt = call('plan.submit', {**version, 'draft_id': draft['id'], 'plan_hash': draft['plan_hash']})
        result = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root), 'run', '--until', receipt['task_id']], capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        task = store.get('tasks', receipt['task_id'])
        actual = task['steps'][task['plan']['verification']]['result']
        assert task['status'] == 'succeeded' and actual['output']['sha256'] == digest
        assert actual['quiescent'] and actual['evidence']
        assert task['context_snapshot_hash'] == draft['context_snapshot_hash']
        # A second actual model draft is accepted, then its source annotation
        # really expires in the ledger before the worker applies the command.
        next_draft = call('plan.propose', version)['draft']
        next_receipt = call('plan.submit', {**version, 'draft_id': next_draft['id'], 'plan_hash': next_draft['plan_hash']})
        if rejection == 'expired_memory':
            memory['valid_until'] = time.time() - 1
            store.put('memories', memory['id'], memory)
        else:
            snapshot = store.get('planning_contexts', next_draft['context_snapshot_id'])
            snapshot['created_at'] += 1
            store.put('planning_contexts', snapshot['id'], snapshot)
        from robot_agent.actions import process_commands
        process_commands(store)
        rejected = store.get('commands', next_receipt['command_id'])
        expected_error = 'expired' if rejection == 'expired_memory' else 'planning snapshot binding changed'
        assert rejected['status'] == 'rejected' and expected_error in rejected['error']['message']
        assert store.get('tasks', next_receipt['task_id']) is None
        report[rejection + '_command'] = {'command_id': rejected['id'], 'status': rejected['status'], 'error': rejected['error']}
        report.update(status='passed', session_id=session['id'], task_id=task['id'], plan=draft['plan'], actual_result=actual,
            context_manifest=manifest, model_records=[{'id': r['id'], 'actual_model': r.get('actual_model'), 'response_id': r.get('response_id')} for r in store.list('model_responses')])
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('actual memory validation report:', root / 'report.json')
        store.close()
