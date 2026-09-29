"""Actual in-flight model response loses to a concurrent real session edit."""
import json
import os
from pathlib import Path
import threading
import time
import uuid

import pytest
from summary_evidence import assert_summary_context

from robot_agent.actions import Actions, local_principal
from robot_agent.contracts import ContractError
from robot_agent.model_transport import environment_config
from robot_agent.store import Store


@pytest.mark.live_model
def test_actual_partial_summary_is_not_bound_after_operator_edit():
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('explicit actual model invocation required')
    root = Path('.runtime/summary-concurrency-validation') / str(uuid.uuid4())
    store = Store(root / 'ledger')
    actions = Actions(store)
    principal = local_principal()
    def call(name, args):
        return actions.call(name, args, principal, idempotency_key=str(uuid.uuid4()))['result']
    session = call('session.create', {'robot_id': 'r1', 'goal': '阅读项目文档，为后续框架开发保留历史背景，本次不执行设备动作。'})['session']
    for name in ('docs/PROJECT_STATUS.md', 'docs/DETAILED_ARCHITECTURE.md'):
        source = Path(name).read_text()
        for start in range(0, len(source), 15000):
            session = call('session.message', {'session_id': session['id'], 'expected_revision': session['revision'],
                'content': '实际项目文档原文：\n' + source[start:start + 15000]})['session']
    for text in ('暂时保留最近的原文。', '仅请求历史摘要。'):
        session = call('session.message', {'session_id': session['id'], 'expected_revision': session['revision'], 'content': text})['session']
    errors, edits = [], []
    def edit_during_model_call():
        other = Store(root / 'ledger')
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if any(r.get('method') == 'session_summary' and r['status'] == 'requesting' for r in other.list('model_responses')):
                    result = Actions(other).call('session.message', {'session_id': session['id'], 'expected_revision': session['revision'],
                        'content': '操作员在摘要请求进行时修改了会话；旧摘要不得绑定到这个新版本。'}, principal, idempotency_key='concurrent-edit')
                    edits.append(result['result']['session']['revision'])
                    return
                time.sleep(0.02)
            raise AssertionError('did not observe an actual in-flight summary request')
        except Exception as exc:
            errors.append(str(exc))
        finally:
            other.close()
    thread = threading.Thread(target=edit_during_model_call)
    report = {'configured_model': environment_config()['model'], 'mock_used': False, 'simulation_used': False}
    thread.start()
    try:
        with pytest.raises(ContractError, match='session changed during summary'):
            call('session.summarize', {'session_id': session['id'], 'expected_revision': session['revision'], 'keep_recent': 2})
        thread.join(timeout=5)
        assert not thread.is_alive() and not errors and edits == [session['revision'] + 1], errors
        current = store.get('sessions', session['id'])
        assert current['revision'] == edits[0] and not current.get('history_summary')
        runs = store.list('summary_runs')
        assert len(runs) == 1 and runs[0]['status'] == 'rejected' and runs[0]['chunk_count'] > 1
        responses = store.list('model_responses')
        assert len(responses) == 1, 'no further model calls after concurrent edit'
        response = responses[0]
        assert response['raw'] and response['actual_model'] and response['response_id']
        assert response['status'] == 'validated' and response['parsed']['points']
        report['summary_context_evidence'] = assert_summary_context(store, response, session)
        source_ids = {p['turn_id'] for p in response['source_parts']}
        assert all(set(p['turn_ids']) <= source_ids for p in response['parsed']['points'])
        assert not store.list('session_summaries') and not store.list('tasks')
        report.update(status='passed', session_id=session['id'], actual_revision=current['revision'], summary_run=runs[0],
            model_response_id=response['id'], actual_response_id=response['response_id'], partial_points=response['parsed']['points'])
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        thread.join(timeout=95)
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('actual concurrent summary report:', root / 'report.json')
        store.close()
