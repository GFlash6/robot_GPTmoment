"""Wire contract checks over the actual built-in skill catalog and session ledger."""
import json

import pytest

from robot_agent.actions import Actions, local_principal
from robot_agent.context_builder import ContextBuilder
from robot_agent.context_codec import encode_bundle, decode_bundle, validate_json
from robot_agent.context_models import ContextRequest, GoalContext
from robot_agent.context_render import RoleAwareRenderer
from robot_agent.contracts import ContractError
from robot_agent.runtime import Runtime
from robot_agent.store import Store


def actual_bundle(store, directory):
    runtime = Runtime(store)
    runtime.install_local_skills([str(directory)])
    session = Actions(store).call('session.create', {'robot_id': 'r1', 'goal': '核验当前项目文档'},
        local_principal(), idempotency_key='codec-session')['result']['session']
    request = ContextRequest('codec', 'planning', GoalContext.from_input(session['original_input']),
        robot_id='r1', session_id=session['id'])
    return ContextBuilder(store).build(request, runtime.catalog())


def test_persisted_bundle_roundtrip_preserves_rendered_model_input(tmp_path):
    store = Store(tmp_path / 'ledger')
    try:
        bundle = actual_bundle(store, tmp_path)
        encoded = encode_bundle(bundle)
        store.put('context_bundles', 'actual', encoded)
        restored = decode_bundle(store.get('context_bundles', 'actual'))
        assert RoleAwareRenderer().render(restored.fragments) == RoleAwareRenderer().render(bundle.fragments)
        assert encode_bundle(restored) == json.loads(json.dumps(encoded, ensure_ascii=False, allow_nan=False))
        restored.fragments[0].content['entities'].append({'id': 'local-consumer-edit'})
        assert not bundle.fragments[0].content['entities']
        assert not encoded['fragments'][0]['content']['entities']
        assert not store.list('model_responses')
    finally:
        store.close()


@pytest.mark.parametrize('damage', ['version', 'extra', 'goal', 'request', 'evidence', 'duplicate', 'metadata'])
def test_damaged_real_bundle_is_rejected_before_model_call(tmp_path, damage):
    store = Store(tmp_path / 'ledger')
    try:
        encoded = encode_bundle(actual_bundle(store, tmp_path))
        if damage == 'version': encoded['schema_version'] = 2
        elif damage == 'extra': encoded['unrecognized'] = True
        elif damage == 'goal': encoded['request']['goal']['disposition'] = 'succeeded'
        elif damage == 'request': encoded['request']['robot_id'] = 3
        elif damage == 'evidence': encoded['fragments'][0]['evidence_ids'] = [3]
        elif damage == 'duplicate': encoded['fragments'].append(encoded['fragments'][0])
        else: encoded['fragments'][0]['metadata']['unsupported'] = float('nan')
        with pytest.raises(ContractError): decode_bundle(encoded)
        assert not store.list('model_responses')
    finally:
        store.close()


@pytest.mark.parametrize('value', [float('nan'), float('inf'), {1: 'lossy key'}, {'binary': b'bytes'}, {'tuple': (1,)}])
def test_non_json_values_are_not_silently_coerced(value):
    with pytest.raises(ContractError): validate_json(value)


def test_cycle_depth_and_shared_reference_handling():
    cyclic = []; cyclic.append(cyclic)
    with pytest.raises(ContractError, match='cycle'): validate_json(cyclic)
    nested = 0
    for _ in range(66): nested = [nested]
    with pytest.raises(ContractError, match='nesting'): validate_json(nested)
    shared = {'actual': 'same reference is not a cycle'}
    validate_json([shared, shared])
