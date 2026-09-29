"""Actual analysis fits; larger planning prompt triggers versioned auto reduction."""
import json
import os
from pathlib import Path
import hashlib
import subprocess
import sys
import uuid

import pytest

from robot_agent.actions import Actions, local_principal
from robot_agent.context_builder import ContextBuilder
from robot_agent.context_models import ContextRequest, GoalContext
from robot_agent.model_call import ModelCaller
from robot_agent.model_context import ContextBudgetError
from robot_agent.model_transport import environment_config
from robot_agent.runtime import Runtime
from robot_agent.store import Store
from robot_agent.contracts import ContractError


@pytest.mark.live_model
def test_planning_budget_reduction_returns_new_session_revision():
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('explicit actual model invocation required')
    root = Path('.runtime/plan-budget-validation') / str(uuid.uuid4())
    root.mkdir(parents=True)
    source = (root / 'protocol.md').resolve()
    source.write_bytes(Path('docs/SKILL_PROTOCOL.md').read_bytes())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    store = Store(root / 'ledger')
    runtime = Runtime(store)
    runtime.install_local_skills([str(root.resolve())])
    actions = Actions(store)
    def call(name, args):
        return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
    report = {'configured_model': environment_config()['model'], 'mock_used': False, 'simulation_used': False}
    try:
        goal = '归档会话指定的实际文件，以 file.ingest 后接 asset.verify 验证字节。系统资产库已配置，无须另一个目标路径，不涉及机器人运动。'
        session = call('session.create', {'robot_id': 'r1', 'goal': goal})['session']
        def message(text):
            nonlocal session
            session = call('session.message', {'session_id': session['id'], 'expected_revision': session['revision'], 'content': text})['session']
        message(f'实际源路径为 {source}，预期 SHA256 为 {digest}。')
        message('固定约束：file.ingest metadata 为 kind=document、encoding=utf8、robot_id=r1、source=plan-budget-constraint；最终验证节点 asset.verify。')
        pinned = session['turns'][-1]['id']
        # Select a real document excerpt against the actual configured preflight budget.
        document = Path('docs/PROJECT_STATUS.md').read_text()
        caller = ModelCaller(environment_config())
        request = ContextRequest('measure-plan-budget', 'planning', GoalContext.from_input(goal), robot_id='r1', session_id=session['id'])
        tail = [{'id': 'measurement-background', 'role': 'user', 'content': ''},
                {'id': 'measurement-recent-a', 'role': 'user', 'content': '背景文档不增加执行任务。'},
                {'id': 'measurement-recent-b', 'role': 'user', 'content': '按指定源路径归档，随后验证实际字节。'}]
        def measured(size):
            candidate = {**session, 'turns': session['turns'] + [{**tail[0], 'content': '背景项目文档原文：\n' + document[:size]}] + tail[1:]}
            return ContextBuilder(store).build(request, runtime.catalog(), session_override=candidate).fragments
        low, high = 1, min(len(document), 15900)
        while low < high:
            mid = (low + high + 1) // 2
            try:
                caller.prepare('goal_analysis', {'original_input': goal, 'conversation': []}, context=measured(mid))
                low = mid
            except ContextBudgetError:
                high = mid - 1
        # Leave room for the short genuine analysis turn, while retaining plan overhead pressure.
        size = max(1, low - 350)
        fragments = measured(size)
        caller.prepare('goal_analysis', {'original_input': goal, 'conversation': []}, context=fragments)
        with pytest.raises(ContextBudgetError):
            caller.prepare('planning', {'goal': goal, 'skills': ContextBuilder.capabilities(runtime.catalog())}, context=fragments)
        message('背景项目文档原文：\n' + document[:size])
        for turn in tail[1:]:
            message(turn['content'])
        session = call('session.context-policy', {'session_id': session['id'], 'expected_revision': session['revision'],
            'auto_summary': True, 'keep_recent': 2, 'pinned_turn_ids': [pinned]})['session']
        session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
        assert not store.list('summary_runs'), 'analysis should fit without a summary call'
        before = session['revision']
        result = call('plan.propose', {'session_id': session['id'], 'expected_revision': before})
        session, draft = result['session'], result['draft']
        assert session['revision'] == before + 1 == draft['session_revision']
        assert session['analysis_revision'] == session['revision'] and session['analysis']
        assert any(e['method'] == 'planning' and e['status'] == 'reduced' for e in store.list('context_budget_events'))
        ingest = next(s for s in draft['plan']['steps'] if s['skill'] == 'file.ingest')
        assert ingest['args']['path'] == str(source) and ingest['args']['metadata']['source'] == 'plan-budget-constraint'
        with pytest.raises(ContractError):
            call('plan.submit', {'session_id': session['id'], 'expected_revision': before, 'draft_id': draft['id'], 'plan_hash': draft['plan_hash']})
        receipt = call('plan.submit', {'session_id': session['id'], 'expected_revision': session['revision'], 'draft_id': draft['id'], 'plan_hash': draft['plan_hash']})
        completed = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root), 'run', '--until', receipt['task_id']], capture_output=True, text=True, timeout=60)
        assert completed.returncode == 0, completed.stderr
        task = store.get('tasks', receipt['task_id'])
        actual = task['steps'][task['plan']['verification']]['result']
        assert task['status'] == 'succeeded' and actual['output']['sha256'] == digest and actual['quiescent'] and actual['evidence']
        response = store.get('model_responses', draft['model_response_id'])
        manifest = store.get('context_manifests', response['context_manifest_id'])
        assert 'session-summary' in manifest['included'] and response['raw'] and response['response_id']
        assert 'plan-budget-constraint' in json.dumps(response['request']['messages'])
        report.update(status='passed', before_revision=before, after_revision=session['revision'], task_id=task['id'],
            actual_result=actual, budget_events=store.list('context_budget_events'), model_response_id=response['id'],
            provider_response_id=response['response_id'], summary_runs=store.list('summary_runs'), manifest=manifest)
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('actual plan-budget report:', root / 'report.json')
        store.close()
