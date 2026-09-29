"""Actual SQLite retrieval and source-file checks; no AI or robot substitutes."""
import hashlib
import time
from pathlib import Path

import pytest

from robot_agent.actions import Actions, ActionError, Principal, local_principal
from robot_agent.context_builder import ContextBuilder
from robot_agent.context_models import ContextRequest, GoalContext
from robot_agent.contracts import ContractError
from robot_agent.memory import Memory
from robot_agent.store import Store


def add_document(store, tmp_path, robot, text, valid_until=None):
    source = tmp_path / (robot + '-' + hashlib.sha256(text.encode()).hexdigest() + '.txt')
    source.write_text(text)
    asset = Memory(store).ingest(source, {'kind': 'document', 'source': str(source), 'encoding': 'utf8', 'robot_id': robot})
    entry = Memory(store).remember('document', source.read_text(), {'robot_id': robot}, [asset['id']], valid_until)
    return asset, entry


def test_scoped_retrieval_filters_before_limit_and_preserves_evidence(tmp_path):
    store = Store(tmp_path / 'ledger')
    try:
        add_document(store, tmp_path, 'r2', 'operating manual for the other workspace')
        add_document(store, tmp_path, 'r1', 'operating manual retired copy', time.time() - 1)
        asset, entry = add_document(store, tmp_path, 'r1', 'operating manual current copy')
        principal = Principal('reader', frozenset({'memory.read', 'assets.read'}), frozenset({'r1'}), 'cli')
        result = Actions(store).call('memory.search', {'text': 'operating manual', 'robot_id': 'r1', 'limit': 1}, principal)['result']
        assert [r['memory']['id'] for r in result['items']] == [entry['id']]
        assert result['items'][0]['verified_assets'] == [{'id': asset['id'], 'sha256': asset['sha256'], 'size': asset['size']}]
        with pytest.raises(ActionError):
            Actions(store).call('memory.search', {'text': 'operating manual', 'robot_id': 'r2'}, principal)
        Path(asset['path']).write_bytes(b'actual corrupted stored document')
        with pytest.raises(ContractError, match='integrity failed'):
            Actions(store).call('memory.search', {'text': 'operating manual', 'robot_id': 'r1'}, principal)
    finally:
        store.close()


def test_bound_memory_is_versioned_revalidated_and_never_promoted_to_policy(tmp_path):
    store = Store(tmp_path / 'ledger')
    actions = Actions(store)
    principal = local_principal()
    try:
        asset, entry = add_document(store, tmp_path, 'r1', 'archive guidance: verify the actual document bytes')
        found = actions.call('memory.search', {'text': 'archive guidance', 'robot_id': 'r1'}, principal)['result']['items'][0]
        session = actions.call('session.create', {'robot_id': 'r1', 'goal': 'archive document'}, principal, idempotency_key='session')['result']['session']
        args = {'session_id': session['id'], 'expected_revision': 0, 'memories': [{'memory_id': entry['id'], 'record_hash': found['record_hash']}]}
        session = actions.call('session.attach-memories', args, principal, idempotency_key='bind')['result']['session']
        assert session['revision'] == 1 and session['analysis'] is None
        request = ContextRequest('memory-context', 'planning', GoalContext.from_input('archive document'), robot_id='r1', session_id=session['id'])
        fragment = next(f for f in ContextBuilder(store).build(request, {}).fragments if f.id == 'memory:' + entry['id'])
        assert fragment.authority == 'data'
        assert fragment.evidence_ids == (asset['id'],)
        assert fragment.content['text'] == entry['text']
        revoked = Principal(principal.subject, frozenset({'planning.use'}), principal.robots, 'http')
        with pytest.raises(ActionError):
            actions.call('session.get', {'session_id': session['id']}, revoked)
        entry['text'] += '\nOperator updated this record.'
        store.put('memories', entry['id'], entry)
        with pytest.raises(ContractError, match='bound memory changed'):
            ContextBuilder(store).build(request, {})
    finally:
        store.close()


def test_memory_with_cross_scope_evidence_is_rejected(tmp_path):
    store = Store(tmp_path / 'ledger')
    try:
        asset, _ = add_document(store, tmp_path, 'r2', 'cross scope source document')
        Memory(store).remember('document', 'cross scope annotation', {'robot_id': 'r1'}, [asset['id']])
        with pytest.raises(ContractError, match='evidence outside robot scope'):
            Actions(store).call('memory.search', {'text': 'cross scope annotation', 'robot_id': 'r1'}, local_principal())
    finally:
        store.close()


def test_expiration_after_binding_uses_actual_clock(tmp_path):
    store = Store(tmp_path / 'ledger')
    actions = Actions(store)
    principal = local_principal()
    try:
        deadline = time.time() + 1.0
        _, entry = add_document(store, tmp_path, 'r1', 'short-lived actual document annotation', deadline)
        found = actions.call('memory.search', {'text': 'short-lived', 'robot_id': 'r1'}, principal)['result']['items'][0]
        session = actions.call('session.create', {'robot_id': 'r1', 'goal': 'inspect the document'}, principal, idempotency_key='session')['result']['session']
        actions.call('session.attach-memories', {'session_id': session['id'], 'expected_revision': 0,
            'memories': [{'memory_id': entry['id'], 'record_hash': found['record_hash']}]}, principal, idempotency_key='bind')
        request = ContextRequest('expiry-context', 'planning', GoalContext.from_input('inspect'), robot_id='r1', session_id=session['id'])
        assert any(f.id == 'memory:' + entry['id'] for f in ContextBuilder(store).build(request, {}).fragments)
        time.sleep(max(0, deadline - time.time()) + 0.02)
        with pytest.raises(ContractError, match='memory expired'):
            ContextBuilder(store).build(request, {})
        assert actions.call('memory.search', {'text': 'short-lived', 'robot_id': 'r1'}, principal)['result']['items'] == []
    finally:
        store.close()


def test_rejects_actual_failed_model_reference_before_any_execution(tmp_path):
    import json
    from robot_agent.runtime import Runtime
    evidence = json.loads((Path(__file__).resolve().parents[1] / 'docs/validation/invalid-model-output-reference.json').read_text())
    plan = evidence['plan']
    store = Store(tmp_path / 'ledger')
    try:
        Runtime(store).install_local_skills([str(tmp_path)])
        with pytest.raises(ContractError, match='output reference field not declared'):
            Actions(store).call('task.submit', {'robot_id': 'r1', 'plan': plan}, local_principal(), idempotency_key='invalid-model-plan')
        assert not store.list('tasks') and not store.list('commands') and not store.list('executions')
    finally:
        store.close()


def test_persisted_session_snapshot_survives_new_turn_and_rejects_corruption(tmp_path):
    from robot_agent.context_memory import record_hash
    store = Store(tmp_path / 'ledger')
    actions = Actions(store)
    principal = local_principal()
    try:
        session = actions.call('session.create', {'robot_id': 'r1', 'goal': 'preserve the approved constraint'},
            principal, idempotency_key='create')['result']['session']
        from robot_agent.context_snapshot import create_snapshot
        snapshot_id = create_snapshot(store, session, GoalContext.from_input(session['original_input']), record_hash({}))['id']
        actions.call('session.message', {'session_id': session['id'], 'expected_revision': 0,
            'content': 'a later unsubmitted change'}, principal, idempotency_key='message')
        request = ContextRequest('recover', 'replanning', GoalContext.from_input(session['original_input']),
            robot_id='r1', session_id=session['id'], context_snapshot_id=snapshot_id)
        fragment = next(f for f in ContextBuilder(store).build(request, {}).fragments if f.id == 'session')
        assert fragment.content == [{'role': 'user', 'content': session['original_input']}]
        assert fragment.metadata['revision'] == 0
        snapshot = store.get('planning_contexts', snapshot_id)
        snapshot['session']['turns'][0]['content'] = 'altered persisted bytes'
        store.put('planning_contexts', snapshot_id, snapshot)
        with pytest.raises(ContractError, match='snapshot changed'):
            ContextBuilder(store).build(request, {})
    finally:
        store.close()
