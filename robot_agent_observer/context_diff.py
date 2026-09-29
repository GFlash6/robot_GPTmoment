"""Deterministic comparison of persisted context evidence, without model execution."""
import hashlib
import json


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def changes(before, after):
    """Top-level fields; presence and JSON types matter, including false versus 0."""
    return [
        {'field': key, 'before_present': key in before, 'after_present': key in after,
         'before': before.get(key), 'after': after.get(key)}
        for key in sorted(before.keys() | after.keys())
        if key not in before or key not in after or canonical(before[key]) != canonical(after[key])
    ]


def shape_issues(context):
    """Check only the structural preconditions needed to avoid ambiguous comparisons."""
    bundle, manifest = context['bundle'], context['manifest']
    if not isinstance(bundle, dict) or not isinstance(manifest, dict):
        return ['missing_comparison_evidence']
    if not isinstance(bundle.get('request'), dict):
        return ['invalid_request_shape']
    fragments = bundle.get('fragments')
    if not isinstance(fragments, list) or any(
        not isinstance(f, dict) or not isinstance(f.get('id'), str) or not f['id']
        or 'content' not in f for f in fragments
    ):
        return ['invalid_fragment_shape']
    ids = [f['id'] for f in fragments]
    if len(ids) != len(set(ids)):
        return ['duplicate_fragment_ids']
    included, dropped = manifest.get('included'), manifest.get('dropped')
    if not isinstance(included, list) or any(not isinstance(i, str) for i in included):
        return ['invalid_included_shape']
    if not isinstance(dropped, list) or any(
        not isinstance(d, dict) or not isinstance(d.get('id'), str) for d in dropped
    ):
        return ['invalid_dropped_shape']
    allocated = included + [d['id'] for d in dropped]
    if len(allocated) != len(set(allocated)) or set(allocated) != set(ids):
        return ['ambiguous_fragment_allocation']
    return []


def fragment_views(context):
    included = set(context['manifest']['included'])
    dropped = {d['id']: d for d in context['manifest']['dropped']}
    return {
        f['id']: {**{k: v for k, v in f.items() if k not in {'id', 'content'}},
                  'content_sha256': hashlib.sha256(canonical(f['content']).encode()).hexdigest(),
                  'allocation': {'status': 'included'} if f['id'] in included else
                                {'status': 'dropped', 'detail': dropped[f['id']]}}
        for f in context['bundle']['fragments']
    }


def compare_contexts(before, after):
    # The caller supplies redacted display fields. Integrity hashes remain the
    # original persisted hashes; these two hash scopes must not be mixed.
    sides = {}
    for name, context in [('before', before), ('after', after)]:
        sides[name] = {key: context[key] for key in
                       ('model_record_id', 'method', 'model_status', 'bundle_id', 'manifest_id', 'integrity')}
        sides[name]['comparison_issues'] = shape_issues(context)
    blocked = any(side['integrity']['status'] != 'matched' or side['comparison_issues']
                  for side in sides.values())
    result = {**sides, 'status': 'unavailable' if blocked else 'compared', 'changes': None,
              'scope': 'redacted_persisted_context_only', 'lineage': 'explicit_pair_not_verified',
              'content_hash_encoding': 'sha256_of_display_json_ensure_ascii_false_sort_keys_default_separators'}
    if blocked:
        return result
    left, right = fragment_views(before), fragment_views(after)
    common = left.keys() & right.keys()
    changed = [{'id': key, 'fields': changes(left[key], right[key])} for key in sorted(common)
               if canonical(left[key]) != canonical(right[key])]
    left_order = [f['id'] for f in before['bundle']['fragments']]
    right_order = [f['id'] for f in after['bundle']['fragments']]
    request_before, request_after = before['bundle']['request'], after['bundle']['request']
    result['scope_differences'] = [key for key in ('robot_id', 'session_id', 'task_id', 'goal')
                                 if canonical(request_before.get(key)) != canonical(request_after.get(key))]
    result['changes'] = {
        'request': changes(request_before, request_after),
        'fragments': {
            'added': [{'id': key, **right[key]} for key in sorted(right.keys() - left.keys())],
            'removed': [{'id': key, **left[key]} for key in sorted(left.keys() - right.keys())],
            'changed': changed,
            'unchanged_ids': sorted(common - {item['id'] for item in changed}),
            'order': {'changed': left_order != right_order, 'before': left_order, 'after': right_order},
        },
        'manifest': changes(before['manifest'], after['manifest']),
        'allocation': changes({'value': before['allocation']}, {'value': after['allocation']}),
        'provider_diagnostics': changes(
            {k: before['bundle'][k] for k in ('diagnostics',) if k in before['bundle']},
            {k: after['bundle'][k] for k in ('diagnostics',) if k in after['bundle']}),
    }
    return result
