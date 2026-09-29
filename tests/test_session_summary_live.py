"""Actual model summary -> actual planning -> worker verification of real bytes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import hashlib

import pytest
from summary_evidence import assert_summary_context

from robot_agent.actions import Actions, local_principal
from robot_agent.context_builder import ContextBuilder
from robot_agent.context_models import ContextRequest, GoalContext
from robot_agent.contracts import ContractError
from robot_agent.model_transport import environment_config
from robot_agent.runtime import Runtime
from robot_agent.store import Store


@pytest.mark.live_model
@pytest.mark.parametrize("large_history,automatic", [(False, False), (True, False), (True, True)], ids=["single", "chunked", "automatic"])
def test_actual_history_summary_preserves_pinned_constraint_and_file_goal(large_history, automatic):
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('explicit actual model invocation required')
    root = Path('.runtime/session-summary-validation') / str(uuid.uuid4())
    root.mkdir(parents=True)
    source = (root / 'protocol.md').resolve()
    document = Path('docs/SKILL_PROTOCOL.md').read_text()
    source.write_text(document)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    store = Store(root / 'ledger')
    Runtime(store).install_local_skills([str(root.resolve())])
    actions = Actions(store)
    def call(name, args):
        return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
    report = {'large_history': large_history, 'automatic': automatic, 'configured_model': environment_config()['model'], 'mock_used': False, 'simulation_used': False}
    try:
        session = call('session.create', {'robot_id': 'r1', 'goal': '归档会话中指定的实际协议文档，并验证字节。使用 file.ingest 后接 asset.verify，系统资产库存储位置已配置，无须询问其他目标路径；不涉及机器人运动。'})['session']
        def message(content):
            nonlocal session
            session = call('session.message', {'session_id': session['id'], 'expected_revision': session['revision'], 'content': content})['session']
        message(f'实际源文件路径为 {source}，SHA256 为 {digest}。这是唯一需要归档的文件。')
        message('固定约束：file.ingest metadata 必须为 kind=document、encoding=utf8、robot_id=r1、source=pinned-summary-constraint；最后一个步骤必须是 asset.verify。')
        pinned = session['turns'][-1]['id']
        # Real project documentation supplied as operator background, not canned AI output.
        if large_history:
            for name in ('docs/PROJECT_STATUS.md', 'docs/DETAILED_ARCHITECTURE.md'):
                background = Path(name).read_text()
                for start in range(0, len(background), 15700):
                    message('以下是实际项目文档背景，不是额外执行任务：\n' + background[start:start + 15700])
        else:
            for start in range(0, min(len(document), 9000), 1500):
                message('以下是实际项目协议原文背景，不是额外执行任务：\n' + document[start:start + 1500])
        message('协议原文仅供理解现有技能。请保留归档目标，不能将协议中的示例当成真实执行结果。')
        message('文件已由测试操作员实际创建；请使用注册的本地技能完成归档和字节验证，不需要机器人接口。')
        original_turns = session['turns']
        if large_history:
            from robot_agent.model_call import ModelCaller
            from robot_agent.session_history import prepare_chunk
            caller = ModelCaller(environment_config())
            # Prove the original history cannot be sent in one actual configured request.
            with pytest.raises(ContractError, match='input budget'):
                prepare_chunk(caller, session['original_input'], [
                    {'id': t['id'], 'role': t['role'], 'content': t['content'],
                     'start': 0, 'end': len(t['content'])} for t in original_turns[:-2]])
        if automatic:
            from robot_agent.model_context import ContextBudgetError
            with pytest.raises(ContextBudgetError):
                call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})
            assert not store.list('model_responses')
            session = call('session.context-policy', {'session_id': session['id'], 'expected_revision': session['revision'],
                'auto_summary': True, 'keep_recent': 2, 'pinned_turn_ids': [t['id'] for t in session['turns'][:-3]]})['session']
            with pytest.raises(ContextBudgetError):
                call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})
            assert not store.list('model_responses') and not store.list('summary_runs')
            session = call('session.context-policy', {'session_id': session['id'], 'expected_revision': session['revision'],
                'auto_summary': True, 'keep_recent': 2, 'pinned_turn_ids': [pinned]})['session']
            summary_source_session = session
            session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
            summary = store.get('session_summaries', session['history_summary']['id'])
            # Analysis appends its genuine response turn; every original stays unchanged.
            assert session['turns'][:-1] == original_turns
        else:
            summary_source_session = session
            result = call('session.summarize', {'session_id': session['id'], 'expected_revision': session['revision'], 'keep_recent': 2, 'pinned_turn_ids': [pinned]})
            session, summary = result['session'], result['summary']
        assert session['turns'][:len(original_turns)] == original_turns and pinned not in {t['id'] for t in summary['covered_turns']}
        assert str(source) in json.dumps(summary['points'], ensure_ascii=False), summary
        report['summary_context_evidence'] = [assert_summary_context(store,
            store.get('model_responses', chunk['model_response_id']), summary_source_session)
            for chunk in summary['chunks']]
        if large_history:
            assert len(summary['chunks']) > 1
            original = {t['id']: t for t in original_turns}
            ranges = {}
            for chunk in summary['chunks']:
                record = store.get('model_responses', chunk['model_response_id'])
                allocation = record['context_allocation']
                assert allocation['estimated_input_tokens'] <= allocation['input_token_limit'] - allocation['reserved_output_tokens']
                assert record['raw'] and record['response_id'] and record['status'] == 'validated'
                sent = next(json.loads(m['content'])['content']['turns'] for m in record['request']['messages']
                            if m['role'] == 'user' and '"context_id": "summary-source"' in m['content'])
                for part in sent:
                    assert part['content'] == original[part['id']]['content'][part['start']:part['end']]
                    ranges.setdefault(part['id'], []).append((part['start'], part['end']))
            for source_ref in summary['covered_turns']:
                spans = ranges[source_ref['id']]
                assert spans[0][0] == 0 and spans[-1][1] == len(original[source_ref['id']]['content'])
                assert all(a[1] == b[0] for a, b in zip(spans, spans[1:]))
        summary_response = store.get('model_responses', summary['model_response_id'])
        assert summary_response['raw'] and summary_response['response_id'] and summary_response['actual_model']
        assert str(source) in json.dumps(summary_response['request']['messages'])
        request = ContextRequest('summary-view', 'planning', GoalContext.from_input(session['original_input']), robot_id='r1', session_id=session['id'])
        fragments = ContextBuilder(store).build(request, Runtime(store).catalog()).fragments
        visible = next(f for f in fragments if f.id == 'session')
        assert any('pinned-summary-constraint' in t['content'] for t in visible.content)
        tail = visible.content[-3:-1] if automatic else visible.content[-2:]
        assert tail == [{'role': t['role'], 'content': t['content']} for t in original_turns[-2:]]
        assert next(f for f in fragments if f.id == 'session-summary').authority == 'data'
        if not automatic:
            session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
        from robot_agent.context_codec import decode_bundle
        from robot_agent.context_memory import record_hash
        from robot_agent.model_call import ModelCaller
        analysis_record = store.get('model_responses', session['analysis']['analysis_response_id'])
        analysis_wire = store.get('context_bundles', analysis_record['context_bundle_id'])
        assert record_hash(analysis_wire) == analysis_record['context_bundle_hash']
        analysis_bundle = decode_bundle(analysis_wire)
        analysis_manifest = store.get('context_manifests', analysis_record['context_manifest_id'])
        assert 'session-summary' in analysis_manifest['included']
        assert next(f for f in analysis_bundle.fragments if f.id == 'session-summary').authority == 'data'
        reconstructed = ModelCaller(environment_config()).prepare('goal_analysis',
            analysis_record['preparation']['arguments'], context=analysis_bundle.fragments)
        assert list(reconstructed.request.messages) == analysis_record['request']['messages']
        assert reconstructed.request.response_format == analysis_record['request']['response_format']
        assert reconstructed.allocation.as_dict() == analysis_record['context_allocation']
        report['analysis_context_evidence'] = {'model_response_id': analysis_record['id'],
            'bundle_hash': analysis_record['context_bundle_hash'], 'manifest': analysis_manifest,
            'reconstruction': 'exact_messages_response_format_and_allocation'}
        version = {'session_id': session['id'], 'expected_revision': session['revision']}
        draft = call('plan.propose', version)['draft']
        ingest = next(s for s in draft['plan']['steps'] if s['skill'] == 'file.ingest')
        assert ingest['args']['path'] == str(source)
        assert ingest['args']['metadata']['source'] == 'pinned-summary-constraint'
        response = store.get('model_responses', draft['model_response_id'])
        manifest = store.get('context_manifests', response['context_manifest_id'])
        assert 'session-summary' in manifest['included']
        receipt = call('plan.submit', {**version, 'draft_id': draft['id'], 'plan_hash': draft['plan_hash']})
        completed = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root), 'run', '--until', receipt['task_id']], capture_output=True, text=True, timeout=60)
        assert completed.returncode == 0, completed.stderr
        task = store.get('tasks', receipt['task_id'])
        actual = task['steps'][task['plan']['verification']]['result']
        assert task['status'] == 'succeeded' and actual['output']['sha256'] == digest
        assert actual['quiescent'] and actual['evidence']
        if automatic:
            events = store.list('context_budget_events')
            assert {'policy_disabled', 'rejected', 'reduced', 'fits'} <= {e['status'] for e in events}
            assert len(store.list('summary_runs')) == 1
            session = call('session.context-policy', {'session_id': session['id'], 'expected_revision': session['revision'],
                'auto_summary': True, 'pinned_turn_ids': [pinned, original_turns[1]['id']]})['session']
            newly_visible = next(f for f in ContextBuilder(store).build(request, Runtime(store).catalog()).fragments if f.id == 'session')
            assert any(t['content'] == original_turns[1]['content'] for t in newly_visible.content)
            report['budget_events'] = events
        # Corrupt an actual covered source and ensure old summary cannot conceal it.
        changed = store.get('sessions', session['id'])
        covered_id = summary['covered_turns'][0]['id']
        next(t for t in changed['turns'] if t['id'] == covered_id)['content'] += '\nChanged source record.'
        store.put('sessions', changed['id'], changed)
        with pytest.raises(ContractError, match='summary source turn changed'):
            ContextBuilder(store).build(request, Runtime(store).catalog())
        report.update(status='passed', task_id=task['id'], summary=summary, actual_result=actual,
            source_bytes=len(json.dumps(original_turns).encode()), summary_bytes=len(json.dumps(summary['points']).encode()),
            summary_response_id=summary_response['response_id'], planning_response_id=response['response_id'], context_manifest=manifest)
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('actual summary validation report:', root / 'report.json')
        store.close()
