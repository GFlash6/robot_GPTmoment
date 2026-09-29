"""Assertions over actual summary records; never creates or replaces model output."""
import json

from robot_agent.context_codec import decode_bundle
from robot_agent.context_memory import record_hash
from robot_agent.model_call import ModelCaller
from robot_agent.model_transport import environment_config


def assert_summary_context(store, record, session, *, config=None, snapshot_id=None):
    wire = store.get('context_bundles', record['context_bundle_id'])
    assert record_hash(wire) == record['context_bundle_hash']
    bundle = decode_bundle(wire)
    assert bundle.request.phase == 'history_summary'
    assert bundle.request.request_id == record['id']
    assert bundle.request.session_id == session['id']
    assert bundle.request.robot_id == session['robot_id']
    assert bundle.request.context_snapshot_id == snapshot_id
    assert record['session_revision'] == session['revision']
    assert bundle.diagnostics == ()
    fragment, = bundle.fragments
    assert fragment.authority == 'data' and fragment.required
    assert fragment.content['original_goal'] == session['original_input']
    originals = {t['id']: t for t in session['turns']}
    for part in fragment.content['turns']:
        original = originals[part['id']]
        assert part['role'] == original['role']
        assert part['content'] == original['content'][part['start']:part['end']]
    assert fragment.metadata['source_parts'] == record['source_parts']
    for part, source in zip(fragment.content['turns'], record['source_parts']):
        assert record_hash(part['content']) == source['content_hash']
    caller = ModelCaller(config or environment_config())
    prepared = caller.prepare(record['preparation']['method'], record['preparation']['arguments'],
                              context=bundle.fragments)
    assert list(prepared.request.messages) == record['request']['messages']
    assert prepared.request.response_format == record['request']['response_format']
    assert prepared.request.temperature == record['request']['temperature'] == 0
    assert prepared.allocation.as_dict() == record['context_allocation']
    manifest = store.get('context_manifests', record['context_manifest_id'])
    assert manifest['included'] == ['summary-source'] and not manifest['dropped']
    assert manifest['sources'][0]['metadata']['source_parts'] == record['source_parts']
    assert record['status'] == 'validated' and record['raw'] and record['response_id']
    assert json.loads(record['raw'])['id'] == record['response_id']
    return {'model_response_id': record['id'], 'bundle_hash': record['context_bundle_hash'],
            'manifest_id': record['context_manifest_id'], 'source_snapshot_id': snapshot_id,
            'source_part_count': len(record['source_parts']),
            'reconstruction': 'exact_messages_response_format_temperature_and_allocation',
            'original_unicode_ranges': 'matched'}
