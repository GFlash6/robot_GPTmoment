"""Strict, versioned wire format for complete model context bundles."""
from copy import deepcopy
import math

from .context_models import ContextBundle, ContextFragment, ContextRequest, GoalContext
from .contracts import require


SCHEMA_VERSION = 1
REQUEST_FIELDS = {'request_id', 'phase', 'goal', 'robot_id', 'session_id',
                  'context_snapshot_id', 'task_id', 'revision', 'generation'}
FRAGMENT_FIELDS = {'id', 'content', 'priority', 'required', 'kind', 'source',
                   'authority', 'evidence_ids', 'metadata'}


def validate_json(value, *, depth=0, active=None):
    """Reject lossy coercion, non-finite numbers, cycles and excessive nesting."""
    require(depth <= 64, 'context JSON nesting exceeds 64')
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        require(math.isfinite(value), 'context JSON number must be finite')
        return
    require(type(value) in (dict, list), 'context value must be JSON data')
    active = set() if active is None else active
    require(id(value) not in active, 'context JSON cycle')
    active.add(id(value))
    try:
        if type(value) is dict:
            require(all(type(key) is str for key in value), 'context JSON keys must be strings')
            children = value.values()
        else:
            children = value
        for child in children:
            validate_json(child, depth=depth + 1, active=active)
    finally:
        active.remove(id(value))


def encode_bundle(bundle):
    require(isinstance(bundle, ContextBundle), 'context bundle required')
    request = bundle.request
    value = {
        'schema_version': SCHEMA_VERSION,
        'request': {name: request.goal.as_dict() if name == 'goal' else getattr(request, name)
                    for name in REQUEST_FIELDS},
        'fragments': [{name: list(f.evidence_ids) if name == 'evidence_ids' else getattr(f, name)
                       for name in FRAGMENT_FIELDS} for f in bundle.fragments],
        'diagnostics': list(bundle.diagnostics),
    }
    validate_json(value)
    return deepcopy(value)


def decode_bundle(value):
    validate_json(value)
    value = deepcopy(value)
    require(type(value) is dict and set(value) == {'schema_version', 'request', 'fragments', 'diagnostics'},
            'invalid context bundle fields')
    require(type(value['schema_version']) is int and value['schema_version'] == SCHEMA_VERSION,
            'unsupported context bundle version')
    raw = value['request']
    require(type(raw) is dict and set(raw) == REQUEST_FIELDS, 'invalid context request fields')
    goal_raw = raw['goal']
    require(type(goal_raw) is dict, 'invalid context goal')
    goal = GoalContext.from_analysis(goal_raw.get('original_input'),
        {k: v for k, v in goal_raw.items() if k not in {'original_input', 'disposition'}})
    require(goal.as_dict() == goal_raw, 'noncanonical context goal')
    for field in ('robot_id', 'session_id', 'context_snapshot_id', 'task_id'):
        require(raw[field] is None or (type(raw[field]) is str and bool(raw[field])),
                f'invalid context request {field}')
    require(type(raw['phase']) is str, 'invalid context phase')
    request = ContextRequest(**{**deepcopy(raw), 'goal': goal})
    require(type(value['fragments']) is list, 'context fragments must be a list')
    fragments = []
    for raw_fragment in value['fragments']:
        require(type(raw_fragment) is dict and set(raw_fragment) == FRAGMENT_FIELDS,
                'invalid context fragment fields')
        raw_fragment = deepcopy(raw_fragment)
        evidence = raw_fragment['evidence_ids']
        require(type(evidence) is list and all(type(x) is str and bool(x) for x in evidence),
                'invalid context evidence ids')
        require(type(raw_fragment['kind']) is str and type(raw_fragment['authority']) is str,
                'invalid context fragment classification')
        fragments.append(ContextFragment(**{**raw_fragment, 'evidence_ids': tuple(evidence)}))
    diagnostics = value['diagnostics']
    require(type(diagnostics) is list and all(type(d) is dict for d in diagnostics),
            'invalid context diagnostics')
    bundle = ContextBundle(request=request, fragments=tuple(fragments), diagnostics=tuple(deepcopy(diagnostics)))
    require(encode_bundle(bundle) == value, 'noncanonical context bundle')
    return bundle
