"""Set verification uses actual project bytes and persisted execution results."""
from pathlib import Path
import uuid

import pytest

from robot_agent.memory import Memory
from robot_agent.runtime import Runtime
from robot_agent.store import Store


@pytest.mark.parametrize('damage', [None, 'digest', 'bytes', 'duplicate', 'robot'])
def test_verifies_every_actual_asset_and_rejects_invalid_sets(tmp_path, damage):
    store = Store(tmp_path / 'ledger')
    try:
        runtime = Runtime(store); runtime.install_local_skills([str(tmp_path)])
        items = []
        for name in ('SKILL_PROTOCOL.md', 'CONTEXT_PROVIDERS.md'):
            source = tmp_path / name; source.write_bytes((Path('docs') / name).read_bytes())
            asset = Memory(store).ingest(source, {'kind': 'document', 'encoding': 'utf8', 'robot_id': 'r1', 'source': str(source)})
            items.append({'asset_id': asset['id'], 'sha256': asset['sha256']})
        if damage == 'digest': items[-1]['sha256'] = '0' * 64
        elif damage == 'bytes': Path(asset['path']).write_bytes(b'actual corrupted asset bytes')
        elif damage == 'duplicate': items.append(items[0].copy())
        elif damage == 'robot':
            asset['metadata']['robot_id'] = 'r2'; store.put('assets', asset['id'], asset)
        execution_id = str(uuid.uuid4()); spec = runtime.catalog()['asset.verify-set']
        result = runtime.skills.call('start', 'asset.verify-set', spec, execution_id, {'items': items}, 'r1')
        if damage:
            assert result['status'] == 'failed' and result['output'] == {}
            assert result['error']
        else:
            assert result['status'] == 'succeeded'
            assert result['output']['verified'] and result['output']['count'] == 2
            assert [{k: i[k] for k in ('asset_id', 'sha256')} for i in result['output']['items']] == items
            assert len(result['evidence']) == 2
        assert runtime.skills.call('query', 'asset.verify-set', spec, execution_id, {'items': items}, 'r1') == result
        assert not store.list('model_responses')
    finally:
        store.close()
