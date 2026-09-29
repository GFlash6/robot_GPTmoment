"""Single-ledger fencing issuance and persistent execution-endpoint enforcement."""
import json
import re

from .contracts import require


def validate_authority(authority, domain):
    require(isinstance(authority, dict) and set(authority) == {'domain', 'token'}, 'execution authority required')
    require(authority['domain'] == domain, 'execution authority domain mismatch')
    require(type(authority['token']) is int and 0 < authority['token'] < 2**63, 'invalid fencing token')
    return authority


def validate_domain(domain):
    require(isinstance(domain, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', domain), 'invalid fencing domain')


def domain_key(robot_id, domain):
    return json.dumps([robot_id, domain], ensure_ascii=True)


def issue(store, robot_id, domain):
    """Must be in the dispatch transaction; one persistent issuer per control domain."""
    key = domain_key(robot_id, domain)
    previous = store.get('fencing_counters', key) or {'token': 0}
    authority = validate_authority({'domain': domain, 'token': previous['token'] + 1}, domain)
    store.put('fencing_counters', key, authority)
    return authority


def accept(store, robot_id, execution_id, authority, *, new_execution):
    """Caller holds endpoint process lock through the actual side effect."""
    key = domain_key(robot_id, authority['domain'])
    current = store.get('service_authorities', key)
    if current is not None:
        if current['token'] == authority['token'] and current['execution_id'] == execution_id:
            return
        require(new_execution and authority['token'] > current['token'], 'stale or conflicting execution authority')
    else:
        require(new_execution, 'execution authority has no registered owner')
    store.put('service_authorities', key, {**authority, 'execution_id': execution_id, 'robot_id': robot_id})
