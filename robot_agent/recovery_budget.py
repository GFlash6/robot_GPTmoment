"""Reduce accepted history without consulting or changing the live session."""
from dataclasses import replace
from types import SimpleNamespace
import time
import uuid

from .context_builder import ContextBuilder
from .context_memory import record_hash
from .context_snapshot import read_snapshot, SCHEMA_VERSION
from .contracts import require
from .model_call import ModelCaller
from .model_context import ContextBudgetError
from .session_history import history_view, summarize


def fit_recovery(store, task, request):
    builder = ContextBuilder(store)
    caller = ModelCaller(task['model_config'])
    arguments = {'goal': request.goal.interpreted_intent, 'skills': builder.capabilities(task['catalog'])}
    snapshot = read_snapshot(store, request.context_snapshot_id, robot_id=task['robot_id'])
    snapshot_hash = record_hash(snapshot)

    def guard():
        current = store.get('tasks', task['id'])
        require(current is not None and current['status'] == 'replanning'
                and (current['revision'], current['generation']) == (request.revision, request.generation),
                'recovery task changed')
        require(record_hash(store.get('planning_contexts', request.context_snapshot_id)) == snapshot_hash,
                'recovery source snapshot changed')
        control = store.get('controls', task['id'])
        require(not control or control.get('failure'), 'recovery interrupted')
        require(not any(c['task_id'] == task['id'] and c['status'] == 'accepted'
                        and c['action'] in {'task.cancel', 'task.pause'}
                        for c in store.list('commands')), 'recovery control command pending')

    event = {'id': str(uuid.uuid4()), 'task_id': task['id'], 'revision': request.revision,
             'generation': request.generation, 'snapshot_id': request.context_snapshot_id,
             'method': 'replanning', 'created_at': time.time()}
    try:
        guard()
        fragments = builder.build(request, task['catalog']).fragments
        try:
            caller.prepare('planning', arguments, context=fragments)
            event['status'] = 'fits'
            return request, guard
        except ContextBudgetError as exc:
            event['trigger'] = str(exc)
        session = snapshot['session']
        policy = session.get('context_policy', {})
        require(policy.get('auto_summary', False), 'recovery history reduction policy disabled')
        _, previous = history_view(store, session)
        keep = policy.get('keep_recent', 6)
        pins = policy.get('pinned_turn_ids', previous['pinned_turn_ids'] if previous else [])
        covered = {t['id'] for t in session['turns'][:-keep] if t['id'] not in pins}
        require(bool(covered), 'no reducible recovery history')
        # Execution state and operator pins are mandatory; never summarize them.
        mandatory = tuple(replace(f, content=[{'role': t['role'], 'content': t['content']}
                          for t in session['turns'] if t['id'] not in covered]) if f.id == 'session' else f
                          for f in fragments if f.id != 'session-summary')
        caller.prepare('planning', arguments, context=mandatory)
        require(previous is None or covered != {t['id'] for t in previous['covered_turns']},
                'existing recovery summary cannot fit; no new reducible history')
        summary = summarize(SimpleNamespace(store=store, model_config=task['model_config']), session,
                            {'id': event['id']}, keep, pins, source_guard=guard, source_request=request)
        effective = {**session, 'history_summary': {'id': summary['id'], 'record_hash': record_hash(summary)}}
        derived_id = str(uuid.uuid4())
        derived = {**snapshot, 'id': derived_id, 'schema_version': SCHEMA_VERSION, 'session': effective, 'session_hash': record_hash(effective),
                   'parent_snapshot_id': request.context_snapshot_id, 'parent_snapshot_hash': snapshot_hash,
                   'recovery_task_id': task['id'], 'recovery_request_id': request.request_id,
                   'created_at': time.time()}
        guard()
        store.put('planning_contexts', derived_id, derived)
        candidate = replace(request, context_snapshot_id=derived_id)
        prepared = caller.prepare('planning', arguments, context=builder.build(candidate, task['catalog']).fragments)
        event.update(status='reduced', derived_snapshot_id=derived_id, summary_id=summary['id'],
                     allocation=prepared.allocation.as_dict())
        guard()
        return candidate, guard
    except Exception as exc:
        event.update(status='rejected', error=str(exc))
        raise
    finally:
        store.put('context_budget_events', event['id'], event)
