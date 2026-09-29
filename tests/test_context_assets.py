"""Bound asset references checked through real actions, SQLite and file bytes."""
import copy
from pathlib import Path
import uuid

import pytest

from robot_agent.actions import Actions, local_principal
from robot_agent.context_assets import verify_session_assets
from robot_agent.context_builder import ContextBuilder
from robot_agent.context_memory import record_hash
from robot_agent.context_models import AssetBinding, ContextRequest, GoalContext
from robot_agent.contracts import ContractError
from robot_agent.memory import Memory
from robot_agent.store import Store


def test_actual_asset_binding_rechecks_catalog_bytes_and_legacy(tmp_path):
    store = Store(tmp_path / 'ledger')
    try:
        actions = Actions(store)
        def call(name, args):
            return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
        asset = Memory(store).ingest(Path('docs/SKILL_PROTOCOL.md'),
            {'kind': 'document', 'encoding': 'utf8', 'source': 'project-protocol', 'robot_id': 'r1'})
        session = call('session.create', {'robot_id': 'r1', 'goal': '核验实际项目协议资产'})['session']
        session = call('session.attach-assets', {'session_id': session['id'], 'expected_revision': session['revision'],
                                              'asset_ids': [asset['id']]})['session']
        binding = AssetBinding.from_dict(session['asset_bindings'][0])
        assert binding.record_hash == record_hash(asset) and binding.sha256 == asset['sha256']
        assert binding.size == len(Path('docs/SKILL_PROTOCOL.md').read_bytes())
        request = ContextRequest('asset-reference-check', 'planning', GoalContext.from_input(session['original_input']),
                                 robot_id='r1', session_id=session['id'])
        fragment = next(f for f in ContextBuilder(store).build(request, {}).fragments if f.id == 'asset-evidence')
        assert fragment.metadata['asset_bindings'] == session['asset_bindings']
        assert fragment.authority == 'data' and fragment.metadata['scope'] == 'stored_asset_bytes_and_bound_record'
        edited = copy.deepcopy(asset); edited['metadata']['source'] = 'changed catalog annotation'
        store.put('assets', asset['id'], edited)
        with pytest.raises(ContractError, match='bound asset record changed'):
            ContextBuilder(store).build(request, {})
        store.put('assets', asset['id'], asset)
        blob = Path(asset['path']); original = blob.read_bytes(); blob.write_bytes(original + b'\nactual storage corruption')
        with pytest.raises(ContractError, match='asset integrity failed'):
            verify_session_assets(store, session)
        blob.write_bytes(original)
        legacy = {k: v for k, v in session.items() if k != 'asset_bindings'}
        store.put('sessions', session['id'], legacy)
        assert call('session.get', {'session_id': session['id']})['session'] == legacy
        with pytest.raises(ContractError, match='legacy asset context'):
            ContextBuilder(store).build(request, {})
        repaired = call('session.attach-assets', {'session_id': session['id'], 'expected_revision': legacy['revision'],
                                               'asset_ids': [asset['id']]})['session']
        assert verify_session_assets(store, repaired) == [asset]
        foreign = Memory(store).ingest(Path('docs/ARCHITECTURE.md'),
            {'kind': 'document', 'encoding': 'utf8', 'source': 'other-robot', 'robot_id': 'r2'})
        with pytest.raises(ContractError, match='robot mismatch'):
            call('session.attach-assets', {'session_id': session['id'], 'expected_revision': repaired['revision'],
                                          'asset_ids': [foreign['id']]})
        assert store.get('sessions', session['id']) == repaired
        cleared = call('session.attach-assets', {'session_id': session['id'], 'expected_revision': repaired['revision'],
                                               'asset_ids': []})['session']
        assert cleared['asset_ids'] == cleared['asset_bindings'] == []
        assert not store.list('model_responses') and not store.list('executions')
    finally:
        store.close()


@pytest.mark.parametrize('damage', ['version', 'boolean_size', 'hash', 'unknown_field', 'reordered_ids', 'binding_robot'])
def test_actual_bound_reference_rejects_malformed_versions(tmp_path, damage):
    store = Store(tmp_path / 'ledger')
    try:
        from robot_agent.context_assets import bind_assets
        assets = [Memory(store).ingest(Path('docs') / name,
            {'kind': 'document', 'encoding': 'utf8', 'source': name, 'robot_id': 'r1'})
            for name in ('ARCHITECTURE.md', 'SKILL_PROTOCOL.md')]
        session = {'robot_id': 'r1', 'asset_ids': [a['id'] for a in assets]}
        session['asset_bindings'] = bind_assets(store, session['asset_ids'], 'r1')
        assert verify_session_assets(store, session) == assets
        first = session['asset_bindings'][0]
        if damage == 'version': first['schema_version'] = True
        elif damage == 'boolean_size': first['size'] = True
        elif damage == 'hash': first['record_hash'] = 'invalid'
        elif damage == 'unknown_field': first['physical_pose'] = 'not a stored-asset field'
        elif damage == 'reordered_ids': session['asset_ids'].reverse()
        elif damage == 'binding_robot': first['robot_id'] = 'r2'
        with pytest.raises(ContractError):
            verify_session_assets(store, session)
        assert not store.list('model_responses')
    finally:
        store.close()
