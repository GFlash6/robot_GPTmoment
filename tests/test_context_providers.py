"""Provider contracts checked against real actions, ledger and file execution."""
from dataclasses import replace
import hashlib
from pathlib import Path
import time
import uuid

import pytest

from robot_agent.actions import Actions, local_principal
from robot_agent.context_builder import ContextBuilder
from robot_agent.context_memory import record_hash
from robot_agent.context_models import ContextRequest, GoalContext
from robot_agent.context_providers import SessionProvider
from robot_agent.contracts import ContractError
from robot_agent.memory import Memory
from robot_agent.runtime import Runtime
from robot_agent.store import Store


def test_providers_resolve_actual_selected_execution_and_bytes(tmp_path):
    store = Store(tmp_path / 'ledger')
    try:
        runtime = Runtime(store)
        runtime.install_local_skills([str(tmp_path)])
        source = tmp_path / 'protocol.md'
        source.write_bytes(Path('docs/SKILL_PROTOCOL.md').read_bytes())
        plan = {'steps': [
            {'id': 'ingest', 'skill': 'file.ingest', 'args': {'path': str(source),
                'metadata': {'kind': 'document', 'encoding': 'utf8', 'source': str(source), 'robot_id': 'r1'}}},
            {'id': 'verify', 'skill': 'asset.verify', 'deps': ['ingest'],
                'args': {'asset_id': {'$ref': 'ingest.asset_id'}}}], 'verification': 'verify'}
        task = runtime.submit(plan, 'r1')
        deadline = time.monotonic() + 10
        while task['status'] not in {'succeeded', 'failed'} and time.monotonic() < deadline:
            task = runtime.tick(task['id'])
        assert task['status'] == 'succeeded'
        asset_id = task['steps']['ingest']['result']['output']['asset_id']
        entry = Memory(store).remember('document', 'Provider contract actual source', {'robot_id': 'r1'}, [asset_id])
        actions = Actions(store)
        def call(name, args):
            return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
        session = call('session.create', {'robot_id': 'r1', 'goal': '查看已执行文件的核验记录'})['session']
        for name, extra in [
            ('session.attach-assets', {'asset_ids': [asset_id]}),
            ('session.attach-memories', {'memories': [{'memory_id': entry['id'], 'record_hash': record_hash(entry)}]}),
            ('selection.set', {'task_id': task['id'], 'task_revision': task['revision'],
                'task_generation': task['generation'], 'step_ids': ['verify']})]:
            session = call(name, {'session_id': session['id'], 'expected_revision': session['revision'], **extra})['session']
        request = ContextRequest('actual-providers', 'planning', GoalContext.from_input(session['original_input']),
            robot_id='r1', session_id=session['id'], task_id=task['id'], revision=task['revision'], generation=task['generation'])
        bundle = ContextBuilder(store).build(request, runtime.catalog())
        fragments = {f.id: f for f in bundle.fragments}
        assert {d['provider'] for d in bundle.diagnostics} == {'goal-capabilities', 'task-state', 'session', 'memory', 'assets', 'selection'}
        assert all(d['fragment_ids'] for d in bundle.diagnostics)
        assert fragments['asset-evidence'].content[0]['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert fragments['ui-selection'].content['selected_steps']['verify']['result']['output']['verified'] is True
        nodes = fragments['task-state'].content['nodes']
        assert next(n for n in nodes if n['id'] == 'verify')['output']['verified'] is True
        assert all(f.authority == 'data' for f in bundle.fragments if f.id not in {'goal', 'capabilities'})
        with pytest.raises(ContractError, match='context task robot mismatch'):
            ContextBuilder(store).build(replace(request, session_id=None, robot_id='r2'), runtime.catalog())
        with pytest.raises(ContractError, match='stale task context'):
            ContextBuilder(store).build(replace(request, revision=request.revision + 1), runtime.catalog())
        from robot_agent.context_snapshot import create_snapshot
        snapshot = create_snapshot(store, session, request.goal, record_hash(runtime.catalog()))
        accepted = replace(request, context_snapshot_id=snapshot['id'])
        with pytest.raises(ContractError, match='cannot override'):
            ContextBuilder(store).build(accepted, runtime.catalog(), session_override={})
        with pytest.raises(ContractError, match='snapshot requires'):
            ContextBuilder(store).build(replace(accepted, session_id=None), runtime.catalog())
        # Damage actual source bytes; provider must fail rather than omit required evidence.
        asset = store.get('assets', asset_id)
        Path(asset['path']).write_bytes(b'corrupted actual stored document')
        with pytest.raises(ContractError, match='integrity failed'):
            ContextBuilder(store).build(request, runtime.catalog())
        assert not store.list('model_responses')
    finally:
        store.close()


def test_duplicate_builtin_provider_registration_is_rejected(tmp_path):
    store = Store(tmp_path / 'ledger')
    try:
        with pytest.raises(ContractError, match='duplicate context provider'):
            ContextBuilder(store, providers=(SessionProvider(), SessionProvider()))
    finally:
        store.close()


def test_builtin_provider_context_does_not_alias_caller_or_other_builds(tmp_path):
    store = Store(tmp_path / 'ledger')
    try:
        runtime = Runtime(store)
        runtime.install_local_skills([str(tmp_path)])
        catalog = runtime.catalog()
        goal = GoalContext('核验文档', '核验文档', entities=({'id': 'document', 'tags': ['original']},))
        request = ContextRequest('isolation', 'planning', goal, robot_id='r1')
        first = ContextBuilder(store).build(request, catalog)
        second = ContextBuilder(store).build(request, catalog)
        fragment = next(f for f in first.fragments if f.id == 'capabilities')
        original_schema = second.fragments[1].content['file.ingest']['input_schema'].copy()
        # Real built-in capability fragments used to share nested registry dictionaries.
        fragment.content['file.ingest']['input_schema']['description'] = 'changed by consumer'
        assert catalog['file.ingest']['input_schema'] == original_schema
        assert second.fragments[1].content['file.ingest']['input_schema'] == original_schema
        goal.entities[0]['tags'].append('caller edit')
        assert first.request.goal.entities[0]['tags'] == ['original']
        first.request.goal.entities[0]['tags'].append('bundle edit')
        assert next(f for f in first.fragments if f.id == 'goal').content['entities'][0]['tags'] == ['original']
        assert second.request.goal.entities[0]['tags'] == ['original']
        empty = [d for d in first.diagnostics if d['status'] == 'empty']
        assert {d['provider'] for d in empty} == {'task-state', 'session', 'memory', 'assets', 'selection'}
        assert all(not d['fragment_ids'] for d in empty)
        assert not store.list('model_responses')
    finally:
        store.close()
