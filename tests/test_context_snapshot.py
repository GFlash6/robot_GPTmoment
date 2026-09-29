"""Version and integrity checks using actual persisted application sessions."""
import copy

import pytest

from robot_agent.actions import Actions, local_principal
from robot_agent.context_memory import record_hash
from robot_agent.context_models import GoalContext
from robot_agent.context_snapshot import create_snapshot, read_snapshot
from robot_agent.contracts import ContractError
from robot_agent.runtime import Runtime
from robot_agent.store import Store


def seed(store):
    session = Actions(store).call('session.create', {'robot_id': 'r1', 'goal': '查看当前项目文档'},
        local_principal(), idempotency_key='snapshot-session')['result']['session']
    return create_snapshot(store, session, GoalContext.from_input(session['original_input']), record_hash(Runtime(store).catalog()))


def test_versioned_and_legacy_reads_do_not_rewrite_history(tmp_path):
    store = Store(tmp_path)
    try:
        snapshot = seed(store)
        assert snapshot['schema_version'] == 1
        assert read_snapshot(store, snapshot['id'], expected_hash=record_hash(snapshot)) == snapshot
        legacy = {k: v for k, v in snapshot.items() if k != 'schema_version'}
        store.put('planning_contexts', snapshot['id'], legacy)
        assert read_snapshot(store, snapshot['id']) == legacy
        assert 'schema_version' not in store.get('planning_contexts', snapshot['id'])
        with pytest.raises(ContractError, match='binding changed'):
            read_snapshot(store, snapshot['id'], expected_hash=record_hash(snapshot))
        with pytest.raises(ContractError, match='robot mismatch'):
            read_snapshot(store, snapshot['id'], robot_id='r2')
        with pytest.raises(ContractError, match='catalog mismatch'):
            read_snapshot(store, snapshot['id'], catalog_hash='0' * 64)
        assert not store.list('model_responses')
    finally:
        store.close()


@pytest.mark.parametrize('damage', ['version', 'session', 'goal', 'identity', 'parent', 'derived_session'])
def test_corrupt_snapshot_or_lineage_rejected(tmp_path, damage):
    store = Store(tmp_path)
    try:
        parent = seed(store)
        target = copy.deepcopy(parent)
        if damage == 'version':
            target['schema_version'] = 99
        elif damage == 'session':
            target['session']['original_input'] += ' altered'
        elif damage == 'goal':
            target['goal']['interpreted_intent'] += ' altered'
        elif damage == 'identity':
            target['id'] = 'wrong-id'
        else:
            target.update(id='derived', parent_snapshot_id=parent['id'], parent_snapshot_hash=record_hash(parent))
            if damage == 'parent':
                parent['created_at'] += 1
                store.put('planning_contexts', parent['id'], parent)
            else:
                target['session']['priority'] += 1
                target['session_hash'] = record_hash(target['session'])
        key = 'derived' if damage in {'parent', 'derived_session'} else parent['id']
        store.put('planning_contexts', key, target)
        with pytest.raises(ContractError):
            read_snapshot(store, key)
        assert not store.list('model_responses') and not store.list('tasks')
    finally:
        store.close()
