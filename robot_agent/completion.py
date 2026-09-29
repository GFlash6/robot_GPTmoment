"""Operator-owned completion checks, separate from model-produced plans."""
import json
import math

from .contracts import ContractError, field, require
from .context_memory import record_hash


def numeric(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def validate_contract(value, catalog=None):
    if value is None:
        return None
    require(isinstance(value, dict) and set(value) == {'schema_version', 'verifier_skill', 'checks'},
            'invalid completion contract fields')
    require(type(value['schema_version']) is int and value['schema_version'] == 1,
            'unsupported completion contract version')
    require(isinstance(value['verifier_skill'], str) and bool(value['verifier_skill']),
            'completion verifier skill required')
    checks = value['checks']
    require(isinstance(checks, list) and 1 <= len(checks) <= 64, 'completion contract needs 1..64 checks')
    ids = []
    for check in checks:
        require(isinstance(check, dict), 'invalid completion check')
        op = check.get('op')
        require(isinstance(op, str) and op in {'eq', 'gte', 'lte', 'nonempty'}, 'unsupported completion operator')
        require(set(check) == ({'id', 'path', 'op'} if op == 'nonempty' else {'id', 'path', 'op', 'value'}),
                'invalid completion check fields')
        require(isinstance(check['id'], str) and 0 < len(check['id']) <= 128, 'completion check id required')
        require(isinstance(check['path'], str) and 0 < len(check['path']) <= 512
                and all(check['path'].split('.')), 'invalid completion output path')
        if op in {'gte', 'lte'}:
            require(numeric(check['value']),
                    'completion bound must be finite numeric value')
        ids.append(check['id'])
    require(len(set(ids)) == len(ids), 'duplicate completion check id')
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        canonical = json.loads(encoded)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ContractError('completion contract must be finite JSON') from exc
    require(len(encoded.encode()) <= 65536, 'completion contract exceeds 64 KiB')
    require(canonical == value, 'completion contract must use JSON values and string keys')
    if catalog is not None:
        skill = catalog.get(value['verifier_skill'])
        require(isinstance(skill, dict) and skill.get('verifier') is True,
                'completion contract requires registered verifier skill')
        for check in checks:
            schema = skill.get('output_schema', {})
            for part in check['path'].split('.'):
                if not isinstance(schema, dict) or any(k in schema for k in ('$ref', 'anyOf', 'oneOf', 'allOf', 'patternProperties')):
                    break
                if part in schema.get('properties', {}):
                    schema = schema['properties'][part]
                else:
                    require(schema.get('additionalProperties') is not False,
                            'completion output path is not declared by verifier')
                    break
    return canonical


def same_contract(left, right):
    return record_hash(validate_contract(left)) == record_hash(validate_contract(right))


def check_plan_contract(plan, catalog, contract):
    require('completion_contract' not in plan, 'completion contract must be supplied outside the model plan')
    contract = validate_contract(contract, catalog)
    if contract is None:
        return
    final = next(step for step in plan['steps'] if step['id'] == plan['verification'])
    require(all(item['skill'] == contract['verifier_skill'] for item in [final, *final.get('fallback', [])]),
            'final verifier differs from completion contract')


def task_contract(task):
    contract = validate_contract(task.get('completion_contract'), task['catalog'])
    require(task.get('completion_contract_hash') == (record_hash(contract) if contract is not None else None),
            'task completion contract binding changed')
    return contract


def evaluate(contract, output, execution_id):
    contract = validate_contract(contract)
    require(contract is not None, 'completion contract required')
    checks = []
    for check in contract['checks']:
        item = {**check, 'status': 'failed'}
        try:
            actual = field(output, check['path'])
            item['actual'] = actual
            if check['op'] == 'eq':
                valid = json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(check['value'], sort_keys=True, allow_nan=False)
            elif check['op'] == 'nonempty':
                valid = bool(actual)
            else:
                valid = numeric(actual) and (
                    actual >= check['value'] if check['op'] == 'gte' else actual <= check['value'])
            item['status'] = 'passed' if valid else 'failed'
        except (ContractError, ValueError, TypeError) as exc:
            item['error'] = str(exc)
        checks.append(item)
    return {'schema_version': 1, 'contract_hash': record_hash(contract), 'execution_id': execution_id,
            'verifier_skill': contract['verifier_skill'], 'checks': checks,
            'status': 'passed' if all(item['status'] == 'passed' for item in checks) else 'failed'}
