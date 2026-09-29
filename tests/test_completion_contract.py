"""Actual local file execution with operator-owned final-output requirements."""
import copy
import hashlib
from pathlib import Path
import uuid

import pytest

from robot_agent.actions import Actions, local_principal, process_commands
from robot_agent.completion import validate_contract
from robot_agent.context_builder import ContextBuilder
from robot_agent.context_models import ContextRequest, GoalContext
from robot_agent.contracts import ContractError
from robot_agent.runtime import Runtime
from robot_agent.store import Store


def setup(store, tmp_path):
    runtime = Runtime(store); runtime.install_local_skills([str(tmp_path)])
    source = tmp_path / 'protocol.md'; source.write_bytes(Path('docs/SKILL_PROTOCOL.md').read_bytes())
    plan = {'steps': [{'id': 'ingest', 'skill': 'file.ingest', 'args': {'path': str(source),
        'metadata': {'kind': 'document', 'source': 'actual-protocol', 'encoding': 'utf8'}}},
        {'id': 'verify', 'skill': 'asset.verify', 'deps': ['ingest'], 'args': {'asset_id': {'$ref': 'ingest.asset_id'}}}],
        'verification': 'verify'}
    contract = {'schema_version': 1, 'verifier_skill': 'asset.verify', 'checks': [
        {'id': 'expected-bytes', 'path': 'sha256', 'op': 'eq', 'value': hashlib.sha256(source.read_bytes()).hexdigest()},
        {'id': 'min-size', 'path': 'size', 'op': 'gte', 'value': 1},
        {'id': 'max-size', 'path': 'size', 'op': 'lte', 'value': len(source.read_bytes())},
        {'id': 'integrity', 'path': 'verified', 'op': 'eq', 'value': True},
        {'id': 'hash-present', 'path': 'sha256', 'op': 'nonempty'}]}
    return runtime, source, plan, contract


def test_actual_skill_success_is_not_task_completion_and_revision_keeps_contract(tmp_path):
    store = Store(tmp_path / 'ledger')
    try:
        runtime, source, plan, contract = setup(store, tmp_path)
        actions = Actions(store)
        def call(name, args):
            return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
        receipt = call('task.submit', {'plan': plan, 'robot_id': 'r1', 'completion_contract': contract})
        original = source.read_bytes(); source.write_bytes(original + b'\nActual changed source file.')
        process_commands(store)
        task = runtime.tick(receipt['task_id'])
        assert task['status'] == 'failed'
        result = task['steps']['verify']['result']
        assert result['reported_status'] == 'succeeded' and result['output']['verified'] is True
        assert result['output']['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
        evaluation = result['completion_evaluation']
        assert evaluation['status'] == 'failed' and evaluation['contract_hash'] == task['completion_contract_hash']
        assert {c['id'] for c in evaluation['checks'] if c['status'] == 'failed'} == {'expected-bytes', 'max-size'}
        assert result['quiescent'] and result['evidence']
        request = ContextRequest('failed-completion', 'replanning', GoalContext.from_input('Inspect actual failed checks'),
                                 robot_id='r1', task_id=task['id'])
        fragments = {f.id: f for f in ContextBuilder(store).build(request, runtime.catalog()).fragments}
        assert fragments['completion-evaluation'].content == evaluation
        assert fragments['completion-evaluation'].authority == 'data' and fragments['completion-evaluation'].required
        assert fragments['completion-evaluation'].metadata['execution_id'] == result['execution_id']
        assert not store.db.execute('SELECT * FROM leases').fetchall()
        source.write_bytes(original)
        call('task.revise', {'task_id': task['id'], 'expected_revision': task['revision'],
                            'expected_generation': task['generation'], 'plan': plan})
        process_commands(store)
        completed = runtime.tick(task['id'])
        assert completed['status'] == 'succeeded' and completed['completion_contract'] == contract
        assert completed['completion_contract_hash'] == task['completion_contract_hash']
        assert completed['steps']['verify']['result']['completion_evaluation']['status'] == 'passed'
        assert all(c['status'] == 'passed' for c in completed['steps']['verify']['result']['completion_evaluation']['checks'])
        assert not store.list('model_responses')
    finally:
        store.close()


def test_session_contract_is_required_context_and_registry_checked(tmp_path):
    store = Store(tmp_path / 'ledger')
    try:
        runtime, _, plan, contract = setup(store, tmp_path)
        actions = Actions(store)
        def call(name, args):
            return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
        session = call('session.create', {'robot_id': 'r1', 'goal': '归档协议并核对指定哈希'})['session']
        session = call('session.completion-contract', {'session_id': session['id'], 'expected_revision': session['revision'],
                                                      'contract': contract})['session']
        request = ContextRequest('completion-context', 'planning', GoalContext.from_input(session['original_input']),
                                 robot_id='r1', session_id=session['id'])
        bundle = ContextBuilder(store).build(request, runtime.catalog())
        fragment = next(f for f in bundle.fragments if f.id == 'completion-contract')
        assert fragment.required and fragment.authority == 'operator' and fragment.content['contract'] == contract
        task = runtime.submit(plan, 'r1', completion_contract=contract)
        request = ContextRequest('completion-recovery', 'replanning', request.goal, robot_id='r1', task_id=task['id'])
        fragment = next(f for f in ContextBuilder(store).build(request, runtime.catalog()).fragments if f.id == 'completion-contract')
        assert fragment.source == 'accepted_task_completion_contract' and fragment.content['contract'] == contract
        malformed = copy.deepcopy(plan); malformed['steps'][-1]['skill'] = 'file.ingest'
        with pytest.raises(ContractError, match='final verifier differs'):
            runtime._check_plan(malformed, runtime.catalog(), 'r1', contract)
        malformed = copy.deepcopy(plan); malformed['steps'][-1]['fallback'] = [{'skill': 'file.ingest', 'args': {}}]
        with pytest.raises(ContractError, match='final verifier differs'):
            runtime._check_plan(malformed, runtime.catalog(), 'r1', contract)
        with pytest.raises(ContractError, match='outside the model plan'):
            runtime._check_plan({**plan, 'completion_contract': None}, runtime.catalog(), 'r1', contract)
        changed = copy.deepcopy(task); changed['completion_contract']['checks'][0]['value'] = 'changed without rebinding'
        store.put('tasks', task['id'], changed)
        assert runtime.tick(task['id'])['status'] == 'failed'
        assert not store.list('executions')
        assert any(e['type'] == 'context_rejected' for e in store.events(task['id']))
        session = call('session.completion-contract', {'session_id': session['id'], 'expected_revision': session['revision'],
                                                      'contract': None})['session']
        assert session['analysis'] is None and session['completion_contract'] is None
        # Viewing a task from another session doesn't require adopting its contract.
        store.put('tasks', task['id'], task)
        request = ContextRequest('read-from-clear-session', 'replanning', GoalContext.from_input(session['original_input']),
                                 robot_id='r1', session_id=session['id'], task_id=task['id'])
        viewed = ContextBuilder(store).build(request, runtime.catalog())
        assert next(f for f in viewed.fragments if f.id == 'completion-contract').content['contract'] == contract
    finally:
        store.close()


@pytest.mark.parametrize('damage', ['version', 'duplicate', 'boolean_bound', 'nonfinite', 'bad_path', 'unknown_skill', 'nonverifier', 'bad_operator'])
def test_contract_rejects_invalid_requirements_against_actual_catalog(tmp_path, damage):
    store = Store(tmp_path / 'ledger')
    try:
        runtime, _, _, contract = setup(store, tmp_path)
        if damage == 'version': contract['schema_version'] = True
        elif damage == 'duplicate': contract['checks'].append(copy.deepcopy(contract['checks'][0]))
        elif damage == 'boolean_bound': contract['checks'][1]['value'] = True
        elif damage == 'nonfinite': contract['checks'][0]['value'] = float('nan')
        elif damage == 'bad_path': contract['checks'][0]['path'] = 'undeclared_output'
        elif damage == 'unknown_skill': contract['verifier_skill'] = 'unregistered-verifier'
        elif damage == 'nonverifier': contract['verifier_skill'] = 'file.ingest'
        elif damage == 'bad_operator': contract['checks'][0]['op'] = {}
        with pytest.raises(ContractError):
            validate_contract(contract, runtime.catalog())
        assert not store.list('executions') and not store.list('model_responses')
    finally:
        store.close()
