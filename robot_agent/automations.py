"""Owner-scoped failure-event diagnostics with durable, at-most-once dispatch."""
import json
import time

from .context_memory import record_hash
from .contracts import require, schema_check
from .context_models import ContextBundle, ContextFragment, ContextRequest, GoalContext
from .context_codec import encode_bundle, decode_bundle
from .context_evidence import context_manifest
from .model_call import ModelCaller
from .model_transport import environment_config, ModelCallError
from .store import dumps


ACTIONS = {'automation.create', 'automation.set-enabled', 'automation.list', 'automation.runs', 'automation.retry'}


def latest_seq(store):
    return store.db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]


def check_rule(rule, principal):
    require(rule is not None and rule['subject'] == principal.subject, 'automation not owned by caller')
    for permission in ('automations.manage', 'tasks.read', 'planning.use'):
        principal.check(permission, rule['robot_id'])


def call(actions, name, args, principal, key):
    store = actions.store
    if name == 'automation.list':
        items = [r for r in store.list('automations') if r['subject'] == principal.subject
                 and ('*' in principal.robots or r['robot_id'] in principal.robots)]
        return {'items': items}
    if name == 'automation.runs':
        rule = store.get('automations', args['automation_id'])
        check_rule(rule, principal)
        return {'items': [j for j in store.list('automation_runs') if j['automation_id'] == rule['id']]}
    require(isinstance(key, str) and 0 < len(key) <= 256, 'automation mutation requires idempotency key')
    identity = record_hash([principal.subject, name, key])
    payload_hash = record_hash(args)
    from .actions import ActionError, check_idempotency_owner
    with store.transaction():
        check_idempotency_owner(store, principal.subject, key, ('automation_requests', identity))
        previous = store.get('automation_requests', identity)
        if previous:
            if previous['payload_hash'] != payload_hash:
                raise ActionError('IDEMPOTENCY_CONFLICT', 'idempotency key already has a different request')
            check_rule(store.get('automations', previous['rule_id']), principal)
            return previous['result']
        if name == 'automation.retry':
            old = store.get('automation_runs', args['run_id'])
            require(old is not None, 'unknown automation run')
            rule = store.get('automations', old['automation_id'])
            check_rule(rule, principal)
            require(old['status'] == args['expected_status'] and old['status'] in {'failed', 'unresolved'},
                    'diagnostic run is not eligible for explicit retry')
            require(rule['enabled'] and rule['enqueued'] < rule['max_runs'], 'automation disabled or call budget exhausted')
            job = {k: old[k] for k in ('automation_id', 'subject', 'robot_id', 'event', 'event_hash',
                                       'execution', 'execution_hash', 'question')}
            job.update(id=identity, status='queued', rule_revision=rule['revision'], created_at=time.time(),
                       retry_of=old['id'], retry_requested_by=principal.subject)
            rule['enqueued'] += 1
            store.put('automation_runs', identity, job)
            store.put('automations', rule['id'], rule)
            result = {'run': job}
            store.put('automation_requests', identity, {'rule_id': rule['id'], 'payload_hash': payload_hash, 'result': result})
            return result
        if name == 'automation.create':
            rule = {'id': identity, 'subject': principal.subject, 'robot_id': args['robot_id'],
                    'max_runs': args['max_runs'], 'revision': 0, 'enabled': True, 'enqueued': 0,
                    'cursor': latest_seq(store), 'created_at': time.time(), 'trigger': 'execution_result.failed',
                    'effect': 'explain_event', 'question': args['question']}
            check_rule(rule, principal)
        else:
            rule = store.get('automations', args['automation_id'])
            check_rule(rule, principal)
            require(rule['revision'] == args['expected_revision'], 'stale automation revision')
            rule.update(enabled=args['enabled'], revision=rule['revision'] + 1, cursor=latest_seq(store))
        store.put('automations', rule['id'], rule)
        result = {'automation': rule}
        store.put('automation_requests', identity, {'rule_id': rule['id'], 'payload_hash': payload_hash, 'result': result})
        return result


def enqueue_events(store, principal):
    """Cursor advancement and run insertion commit together; pauses skip their interval."""
    with store.transaction():
        for rule in store.list('automations'):
            if rule['subject'] != principal.subject:
                continue
            check_rule(rule, principal)
            if not rule['enabled'] or rule['enqueued'] >= rule['max_runs']:
                continue
            events = store.db.execute('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT 500', (rule['cursor'],)).fetchall()
            for row in events:
                event = dict(row)
                rule['cursor'] = event['seq']
                if event['type'] != 'execution_result':
                    continue
                result = json.loads(event['data'])
                if result.get('status') != 'failed':
                    continue
                task = store.get('tasks', event['task'])
                if task is None or task['robot_id'] != rule['robot_id']:
                    continue
                execution = store.get('executions', result.get('execution_id'))
                require(execution is not None and execution['task_id'] == task['id'], 'event execution missing or mismatched')
                require(record_hash(execution.get('result')) == record_hash(result), 'event execution result mismatch')
                identity = record_hash([rule['id'], event['seq']])
                if not store.get('automation_runs', identity):
                    job = {'id': identity, 'automation_id': rule['id'], 'rule_revision': rule['revision'],
                           'subject': rule['subject'], 'robot_id': rule['robot_id'], 'status': 'queued',
                           'event': event, 'event_hash': record_hash(event), 'execution': execution,
                           'execution_hash': record_hash(execution), 'question': rule['question'], 'created_at': time.time()}
                    store.put('automation_runs', identity, job)
                    rule['enqueued'] += 1
                if rule['enqueued'] >= rule['max_runs']:
                    break
            store.put('automations', rule['id'], rule)


def explain_event(store, job, config):
    """One real model call over immutable event evidence; no task-control capability."""
    event, execution = job['event'], job['execution']
    result = json.loads(event['data'])
    refs = [f"event:{event['seq']}", 'execution:' + execution['id']]
    caller = ModelCaller(config or environment_config())
    fragment = ContextFragment(id='failure-event', kind='task_state', source='runtime_event_ledger', authority='data',
        required=True, content={'event': {**event, 'data': result}, 'execution': execution},
        evidence_ids=tuple(refs), metadata={'event_hash': job['event_hash'], 'execution_hash': job['execution_hash']})
    # This request describes historical event evidence, not a current task snapshot.
    # task_id/revision binding remains absent; the exact task identity is in the event.
    encoded_bundle = encode_bundle(ContextBundle(
        ContextRequest(job['id'], 'automation_diagnosis', GoalContext.from_input(job['question']),
                       robot_id=job['robot_id']), (fragment,)))
    bundle = decode_bundle(encoded_bundle)
    arguments = json.loads(dumps({'question': job['question'], 'instruction':
        'Explain this actual failed execution in the question language. Distinguish observed error from hypotheses. '
        'Do not claim recovery, physical stop, or task success. Return JSON with summary (nonempty string), '
        'observed_error (copy the recorded error exactly), record_refs (all supplied refs), and unknowns (string array). '
        'Allowed refs: ' + json.dumps(refs), 'response_format': {'type': 'json_object'}}))
    prepared = caller.prepare('qa', arguments, context=bundle.fragments)
    manifest = context_manifest(bundle, prepared, caller._renderer.version)
    record = {'id': job['id'], 'method': 'automation_diagnosis', 'status': 'requesting',
              'context_manifest_id': job['id'],
              'automation_run_id': job['id'], 'model': caller.config.model, 'created_at': time.time(),
              'request': {'messages': list(prepared.request.messages), 'response_format': prepared.request.response_format,
                          'model': caller.config.model}, 'event_hash': job['event_hash'], 'execution_hash': job['execution_hash'],
              'context_allocation': prepared.allocation.as_dict(),
              'context_bundle_id': job['id'], 'context_bundle_hash': record_hash(encoded_bundle),
              'preparation': {'method': 'qa', 'arguments': arguments}}
    with store.transaction():
        store.put('context_bundles', job['id'], encoded_bundle)
        store.put('context_manifests', job['id'], {'id': job['id'], **manifest.as_dict()})
        store.put('model_responses', record['id'], record)
    try:
        response = caller.send_prepared(prepared)
        record.update(raw=response.transport.raw, http_status=response.transport.status_code,
                      actual_model=response.actual_model, response_id=response.response_id,
                      elapsed_ms=response.transport.elapsed_ms)
        parsed = json.loads(response.content)
        schema_check({'type': 'object', 'additionalProperties': False,
            'required': ['summary', 'observed_error', 'record_refs', 'unknowns'], 'properties': {
                'summary': {'type': 'string', 'minLength': 1}, 'observed_error': {'const': result.get('error', '')},
                'record_refs': {'type': 'array', 'minItems': 2, 'maxItems': 2, 'uniqueItems': True, 'items': {'enum': refs}},
                'unknowns': {'type': 'array', 'items': {'type': 'string'}}}}, parsed)
        record.update(status='validated', parsed=parsed)
        return {'explanation': parsed, 'model_response_id': record['id'], 'is_execution_evidence': False}
    except Exception as exc:
        if isinstance(exc, ModelCallError) and exc.response is not None:
            record.update(raw=exc.response.raw, http_status=exc.response.status_code)
        record.update(status='rejected', error=str(exc))
        raise
    finally:
        # Persist the terminal response and diagnostic outcome together: a crash
        # cannot leave a validated response attached to a still-running job.
        with store.transaction():
            store.put('model_responses', record['id'], record)
            if record['status'] == 'validated':
                job.update(status='completed', result={'explanation': record['parsed'],
                    'model_response_id': record['id'], 'is_execution_evidence': False}, finished_at=time.time())
            elif record['status'] == 'rejected':
                job.update(status='failed', error=record.get('error', 'model diagnosis rejected'), finished_at=time.time())
            else:
                job.update(status='unresolved', error='model call interrupted before a terminal response',
                           response_status_at_recovery=record['status'])
            job['model_response_id'] = record['id']
            store.put('automation_runs', job['id'], job)


def run_once(store, principal, *, scan_only=False, limit=10, model_config=None):
    principal.check('automations.manage')
    require(type(limit) is int and 1 <= limit <= 100, 'invalid automation batch limit')
    # Separate from the execution worker lock; slow models do not block robot control.
    with store.task_lock('automation-worker:' + principal.subject):
        enqueue_events(store, principal)
        processed = []
        for job in sorted(store.list('automation_runs'), key=lambda j: j['created_at']):
            if job['subject'] != principal.subject:
                continue
            rule = store.get('automations', job['automation_id'])
            check_rule(rule, principal)
            if job['status'] == 'running':
                response = store.get('model_responses', job['id'])
                job.update(status='unresolved', error='worker exited during model call; automatic replay disabled',
                           model_response_id=response['id'] if response else None,
                           response_status_at_recovery=response['status'] if response else 'not_recorded')
                store.put('automation_runs', job['id'], job)
            if scan_only or job['status'] != 'queued' or len(processed) >= limit:
                continue
            with store.transaction():
                rule = store.get('automations', job['automation_id'])
                if not rule['enabled'] or rule['revision'] != job['rule_revision']:
                    job.update(status='canceled', error='automation changed before dispatch')
                    store.put('automation_runs', job['id'], job)
                    processed.append(job)
                    continue
                job.update(status='running', started_at=time.time())
                store.put('automation_runs', job['id'], job)
            try:
                row = store.db.execute('SELECT * FROM events WHERE seq=?', (job['event']['seq'],)).fetchone()
                require(row is not None and record_hash(dict(row)) == job['event_hash'], 'automation event changed')
                require(record_hash(job['execution']) == job['execution_hash'], 'automation execution snapshot changed')
                result = explain_event(store, job, model_config)
                job.update(status='completed', result=result, finished_at=time.time())
            except Exception as exc:
                job.update(status='failed', error=str(exc), finished_at=time.time())
            store.put('automation_runs', job['id'], job)
            processed.append(job)
        return {'items': processed}
