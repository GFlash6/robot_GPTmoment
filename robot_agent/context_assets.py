"""Version-bound stored assets, checked against real bytes at use boundaries."""
from .context_memory import record_hash
from .context_models import AssetBinding
from .contracts import require
from .memory import Memory


def asset_record(store, asset_id, robot_id):
    asset = store.get('assets', asset_id)
    require(isinstance(asset, dict) and asset.get('id') == asset_id, 'context asset missing or identity mismatch')
    require(isinstance(asset.get('metadata'), dict), 'invalid context asset metadata')
    require(asset['metadata'].get('robot_id') is None or asset['metadata'].get('robot_id') == robot_id, 'context asset robot mismatch')
    return asset


def bind_assets(store, asset_ids, robot_id):
    require(isinstance(asset_ids, list) and all(isinstance(key, str) and key for key in asset_ids),
            'invalid context asset ids')
    require(len(asset_ids) == len(set(asset_ids)), 'duplicate context asset binding')
    with store.transaction():
        bindings = []
        for key in asset_ids:
            asset = asset_record(store, key, robot_id)
            Memory(store).read(key)
            bindings.append(AssetBinding(key, robot_id, record_hash(asset), asset['sha256'], asset['size']).as_dict())
        return bindings


def verify_session_assets(store, session):
    """Old IDs alone cannot establish what metadata an earlier plan actually used."""
    ids = session.get('asset_ids', [])
    bindings = session.get('asset_bindings', [])
    require(isinstance(ids, list) and all(isinstance(key, str) and key for key in ids),
            'invalid context asset ids')
    require(isinstance(bindings, list), 'invalid context asset bindings')
    require(not ids or 'asset_bindings' in session, 'legacy asset context has no version binding; reattach assets')
    parsed = [AssetBinding.from_dict(value) for value in bindings]
    require([binding.asset_id for binding in parsed] == ids and len(ids) == len(set(ids)),
            'asset bindings do not match session attachments')
    assets = []
    with store.transaction():
        for binding in parsed:
            require(binding.robot_id == session['robot_id'], 'asset binding robot mismatch')
            asset = asset_record(store, binding.asset_id, session['robot_id'])
            require(record_hash(asset) == binding.record_hash, 'bound asset record changed; reattach assets')
            require((asset.get('sha256'), asset.get('size')) == (binding.sha256, binding.size),
                    'bound asset byte identity mismatch')
            Memory(store).read(binding.asset_id)
            assets.append(asset)
    return assets
