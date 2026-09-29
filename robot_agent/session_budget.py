"""Explicit session policy gates model-backed reduction before an over-budget call."""
import time
import uuid

from .context_builder import ContextBuilder
from .context_memory import record_hash
from .context_models import ContextFragment
from .contracts import require
from .model_call import ModelCaller
from .model_context import ContextBudgetError
from .model_transport import environment_config
from .session_history import history_view, summarize


def fit_session(actions, session, request, catalog, method, arguments, action_record):
    """Return the effective session and exact preflight bundle, including provenance."""
    builder = ContextBuilder(actions.store)
    caller = ModelCaller(actions.model_config or environment_config())
    bundle = builder.build(request, catalog, session_override=session)
    fragments = bundle.fragments
    event = {'id': str(uuid.uuid4()), 'session_id': session['id'], 'session_revision': session['revision'],
        'action_call_id': action_record['id'], 'method': method, 'created_at': time.time()}
    try:
        try:
            prepared = caller.prepare(method, arguments, context=fragments)
            event.update(status='fits', allocation=prepared.allocation.as_dict())
            return session, bundle
        except ContextBudgetError as exc:
            event.update(trigger=str(exc), fragment_id=exc.fragment_id)
            policy = session.get('context_policy', {})
            if not policy.get('auto_summary', False):
                event['status'] = 'policy_disabled'
                raise
        keep_recent = policy.get('keep_recent', 6)
        pinned = set(policy.get('pinned_turn_ids', []))
        # Previously pinned turns remain protected unless the policy explicitly replaces them.
        visible, previous = history_view(actions.store, session)
        if 'pinned_turn_ids' not in policy and previous:
            pinned.update(previous['pinned_turn_ids'])
        covered = [t for t in session['turns'][:-keep_recent] if t['id'] not in pinned]
        require(bool(covered), 'no reducible history; fixed context exceeds budget')
        covered_ids = {t['id'] for t in covered}
        fixed = [t for t in session['turns'] if t['id'] not in covered_ids]
        mandatory = tuple(f for f in fragments if f.id not in {'session', 'session-summary'}) + (
            ContextFragment(id='session', kind='session', authority='data', source='session_ledger', priority=85,
                required=True, content=[{'role': t['role'], 'content': t['content']} for t in fixed]),)
        # Fail before spending model calls if history reduction cannot possibly fit.
        caller.prepare(method, arguments, context=mandatory)
        require(previous is None or covered_ids != {t['id'] for t in previous['covered_turns']},
            'existing summary still exceeds budget; no new reducible history')
        summary = summarize(actions, session, action_record, keep_recent, sorted(pinned))
        event.update(summary_id=summary['id'], summary_run_id=summary['summary_run_id'])
        current = actions.store.get('sessions', session['id'])
        require(current is not None and current['revision'] == session['revision'], 'session changed during budget reduction')
        effective = {**session, 'history_summary': {'id': summary['id'], 'record_hash': record_hash(summary)}}
        bundle = builder.build(request, catalog, session_override=effective)
        fragments = bundle.fragments
        prepared = caller.prepare(method, arguments, context=fragments)
        event.update(status='reduced', allocation=prepared.allocation.as_dict())
        return effective, bundle
    except Exception as exc:
        event.update(status=event.get('status', 'rejected'), error=str(exc))
        raise
    finally:
        actions.store.put('context_budget_events', event['id'], event)
