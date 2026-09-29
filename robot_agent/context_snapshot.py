"""Versioned planning snapshots, including explicit legacy reads and lineage checks."""
import time
import uuid

from .context_memory import record_hash
from .context_models import GoalContext
from .contracts import require


SCHEMA_VERSION = 1


def snapshot_goal(snapshot):
    raw = snapshot['goal']
    require(isinstance(raw, dict), 'invalid planning snapshot goal')
    goal = GoalContext.from_analysis(raw.get('original_input'), {
        k: v for k, v in raw.items() if k not in {'original_input', 'disposition'}})
    require(goal.as_dict() == raw, 'noncanonical planning snapshot goal')
    return goal


def read_snapshot(store, snapshot_id, *, robot_id=None, session_id=None, catalog_hash=None, expected_hash=None):
    """Read existing unversioned records as v0; never rewrite accepted history."""
    seen = set()
    root = None
    child = None
    current_id = snapshot_id
    while current_id:
        require(isinstance(current_id, str), 'invalid planning snapshot id')
        require(current_id not in seen and len(seen) < 32, 'invalid planning snapshot lineage')
        seen.add(current_id)
        snapshot = store.get('planning_contexts', current_id)
        require(isinstance(snapshot, dict), 'missing planning context snapshot')
        version = snapshot.get('schema_version', 0)
        require(type(version) is int and version in {0, SCHEMA_VERSION}, 'unsupported planning snapshot version')
        require(snapshot.get('id') == current_id, 'planning snapshot identity mismatch')
        session = snapshot.get('session')
        require(isinstance(session, dict), 'invalid planning snapshot session')
        require(record_hash(session) == snapshot.get('session_hash'), 'planning context snapshot changed')
        require(record_hash(snapshot.get('goal')) == snapshot.get('goal_hash'), 'planning goal snapshot changed')
        goal = snapshot_goal(snapshot)
        require(session.get('original_input') == goal.original_input, 'planning snapshot goal/session mismatch')
        require(isinstance(snapshot.get('catalog_hash'), str) and len(snapshot['catalog_hash']) == 64,
                'invalid planning snapshot catalog hash')
        require(isinstance(session.get('id'), str) and session['id'], 'planning snapshot session id required')
        require(isinstance(session.get('robot_id'), str) and session['robot_id'], 'planning snapshot robot required')
        if child:
            require(record_hash(snapshot) == child['parent_snapshot_hash'], 'planning snapshot parent changed')
            require(child['goal_hash'] == snapshot['goal_hash'] and child['catalog_hash'] == snapshot['catalog_hash'],
                    'derived planning snapshot changed goal or capabilities')
            # Only the history-summary binding may change during budget reduction.
            require({k: v for k, v in child['session'].items() if k != 'history_summary'} ==
                    {k: v for k, v in session.items() if k != 'history_summary'},
                    'derived planning snapshot changed original session')
        else:
            root = snapshot
            require(expected_hash is None or record_hash(snapshot) == expected_hash, 'planning snapshot binding changed')
            require(robot_id is None or session['robot_id'] == robot_id, 'planning snapshot robot mismatch')
            require(session_id is None or session['id'] == session_id, 'planning snapshot session mismatch')
            require(catalog_hash is None or snapshot['catalog_hash'] == catalog_hash, 'planning snapshot catalog mismatch')
        parent = snapshot.get('parent_snapshot_id')
        require(bool(parent) == bool(snapshot.get('parent_snapshot_hash')), 'incomplete planning snapshot lineage')
        if parent:
            require(isinstance(parent, str) and isinstance(snapshot['parent_snapshot_hash'], str), 'invalid planning snapshot parent')
        child, current_id = snapshot, parent
    require(root is not None, 'planning snapshot id required')
    return root


def create_snapshot(store, session, goal, catalog_hash):
    snapshot = {'id': str(uuid.uuid4()), 'schema_version': SCHEMA_VERSION,
                'session': session, 'session_hash': record_hash(session),
                'goal': goal.as_dict(), 'goal_hash': record_hash(goal.as_dict()),
                'catalog_hash': catalog_hash, 'created_at': time.time()}
    with store.transaction():
        store.put('planning_contexts', snapshot['id'], snapshot)
        return read_snapshot(store, snapshot['id'])
