"""Actual model recovery after an actual file disappears; no substituted transport."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

import pytest
from summary_evidence import assert_summary_context

from robot_agent.actions import Actions, local_principal, process_commands
from robot_agent.memory import Memory
from robot_agent.model_transport import environment_config
from robot_agent.runtime import Runtime
from robot_agent.store import Store


@pytest.mark.live_model
@pytest.mark.parametrize('recovery_budget', [False, True, 'cancel'], ids=['snapshot', 'budget', 'cancel'])
def test_recovery_retains_submitted_session_and_memory(recovery_budget):
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('requires explicit actual model invocation')
    root = Path('.runtime/replanning-context-validation') / str(uuid.uuid4())
    root.mkdir(parents=True)
    primary = (root / 'primary.md').resolve()
    backup = (root / 'backup.md').resolve()
    content = Path('docs/SKILL_PROTOCOL.md').read_bytes()
    primary.write_bytes(content)
    backup.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    store = Store(root / 'ledger')
    runtime = Runtime(store)
    runtime.install_local_skills([str(root.resolve())])
    asset = Memory(store).ingest(backup, {'kind': 'document', 'source': str(backup), 'encoding': 'utf8', 'robot_id': 'r1'})
    memory = Memory(store).remember('document', 'protocol recovery sources',
        {'robot_id': 'r1', 'primary_path': str(primary), 'backup_path': str(backup), 'sha256': digest}, [asset['id']])
    actions = Actions(store)
    def call(name, args):
        return actions.call(name, args, local_principal(), idempotency_key=str(uuid.uuid4()))['result']
    report = {'configured_model': environment_config()['model'], 'mock_used': False, 'simulation_used': False}
    try:
        observed_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                           for name, path in [('primary_path', primary), ('backup_path', backup)]}
        assert set(observed_hashes.values()) == {digest}
        report['operator_read_hashes_before_planning'] = observed_hashes
        found = call('memory.search', {'text': 'protocol recovery sources', 'robot_id': 'r1'})['items'][0]
        session = call('session.create', {'robot_id': 'r1', 'max_replans': 1, 'goal':
            '归档绑定记忆中的协议文档并验证字节。首次计划只用 primary_path 执行 file.ingest，然后 asset.verify；'
            '不要增加 fallback。只有实际文件读取失败后的重规划才允许改用同一记忆中的 backup_path。'
            '路径和哈希均从绑定记忆获取，归档位置已配置，无须提问，不涉及机器人运动。'})['session']
        session = call('session.message', {'session_id': session['id'], 'expected_revision': session['revision'],
            'content': '持久约束：所有 file.ingest 的 metadata 必须是 kind=document、encoding=utf8、robot_id=r1、source=operator-recovery-constraint。最终节点必须是 asset.verify。'
                + ' 操作者刚刚实际读取了绑定记忆中 primary_path 和 backup_path 对应的两个文件，SHA256 分别为 '
                + json.dumps(observed_hashes, ensure_ascii=False)
                + '。这是规划前的实际读取记录，不保证未来文件仍存在；执行时变化由 file.ingest 的实际结果判定。本任务不要求增加独立文件探测步骤。'})['session']
        if recovery_budget:
            pin = session['turns'][-1]['id']
            for text in ['背景参考文档，仅供理解协议，不是新增任务：\n' + Path('docs/DETAILED_ARCHITECTURE.md').read_text()[:4500],
                         '本次仅执行文件归档。', '实际失败后允许使用已绑定的备用路径。']:
                session = call('session.message', {'session_id': session['id'], 'expected_revision': session['revision'], 'content': text})['session']
            session = call('session.context-policy', {'session_id': session['id'], 'expected_revision': session['revision'],
                'auto_summary': True, 'keep_recent': 2, 'pinned_turn_ids': [pin]})['session']
        session = call('session.attach-memories', {'session_id': session['id'], 'expected_revision': session['revision'],
            'memories': [{'memory_id': memory['id'], 'record_hash': found['record_hash']}]})['session']
        session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
        version = {'session_id': session['id'], 'expected_revision': session['revision']}
        draft = call('plan.propose', version)['draft']
        ingest = next(s for s in draft['plan']['steps'] if s['skill'] == 'file.ingest')
        assert ingest['args']['path'] == str(primary)
        receipt = call('plan.submit', {**version, 'draft_id': draft['id'], 'plan_hash': draft['plan_hash']})
        process_commands(store)
        # Real operator edit after submission must not alter the accepted context.
        call('session.message', {**version, 'content': '下一项任务备注：UNSUBMITTED_LATER_MESSAGE，不修改已经提交的任务。'})
        primary.unlink()
        task = store.get('tasks', receipt['task_id'])
        deadline = time.monotonic() + 30
        while task['status'] not in {'failed', 'replanning', 'succeeded'} and time.monotonic() < deadline:
            task = runtime.tick(task['id'])
            time.sleep(0.02)
        assert task['status'] == 'replanning', task
        assert task['steps'][ingest['id']]['status'] == 'failed', task
        report['actual_failure'] = task
        original_snapshot = store.get('planning_contexts', draft['context_snapshot_id'])
        if recovery_budget:
            from robot_agent.context_builder import ContextBuilder
            from robot_agent.context_models import ContextRequest, GoalContext
            from robot_agent.model_call import ModelCaller
            from robot_agent.model_context import ContextBudgetError
            from dataclasses import replace
            goal = GoalContext.from_analysis(original_snapshot['goal']['original_input'],
                {k: v for k, v in original_snapshot['goal'].items() if k not in {'original_input', 'disposition'}})
            req = ContextRequest('measure-recovery', 'replanning', goal, robot_id='r1', session_id=session['id'],
                context_snapshot_id=draft['context_snapshot_id'], task_id=task['id'], revision=task['revision'], generation=task['generation'])
            fragments = ContextBuilder(store).build(req, task['catalog']).fragments
            fixed = tuple(replace(f, content=[{'role': t['role'], 'content': t['content']} for t in original_snapshot['session']['turns']
                if t['id'] == pin or t in original_snapshot['session']['turns'][-2:]]) if f.id == 'session' else f
                for f in fragments if f.id != 'session-summary')
            arguments = {'goal': goal.interpreted_intent, 'skills': ContextBuilder.capabilities(task['catalog'])}
            caller = ModelCaller(task['model_config'])
            cost = caller.prepare('planning', arguments, context=fixed).allocation.estimated_input_tokens
            task['model_config']['max_input_tokens'] = cost + caller.config.max_output_tokens + 4000
            limited = ModelCaller(task['model_config'])
            with pytest.raises(ContextBudgetError):
                limited.prepare('planning', arguments, context=fragments)
            store.put('tasks', task['id'], task)
            report['recovery_input_limit'] = task['model_config']['max_input_tokens']
        if recovery_budget == 'cancel':
            errors, receipts = [], []
            def cancel_during_summary():
                other = Store(store.root)
                try:
                    deadline = time.monotonic() + 90
                    while time.monotonic() < deadline:
                        if any(r.get('method') == 'session_summary' and r['status'] == 'requesting'
                               for r in other.list('model_responses')):
                            receipts.append(Actions(other).call('task.cancel', {'task_id': task['id'],
                                'expected_revision': task['revision'], 'expected_generation': task['generation']},
                                local_principal(), idempotency_key='cancel-during-recovery-summary'))
                            return
                        time.sleep(0.02)
                    raise AssertionError('no actual in-flight summary observed')
                except Exception as exc:
                    errors.append(str(exc))
                finally:
                    other.close()
            before = {r['id'] for r in store.list('model_responses')}
            thread = threading.Thread(target=cancel_during_summary)
            thread.start()
            try:
                task = runtime.recover_plan(task['id'])
            finally:
                thread.join(timeout=100)
            assert not thread.is_alive() and not errors and receipts, errors
            new = [r for r in store.list('model_responses') if r['id'] not in before]
            assert new and all(r['method'] == 'session_summary' and r['raw'] for r in new)
            report['summary_context_evidence'] = [assert_summary_context(store, r, original_snapshot['session'],
                config=task['model_config'], snapshot_id=draft['context_snapshot_id']) for r in new]
            assert all(r['status'] == 'rejected' for r in store.list('summary_runs'))
            assert task['revision'] == 0 and len(store.list('planning_contexts')) == 1
            process_commands(store)
            result = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root),
                'run', '--until', task['id']], capture_output=True, text=True, timeout=60)
            assert result.returncode == 0, result.stderr
            task = store.get('tasks', task['id'])
            assert task['status'] == 'canceled', task
            report.update(status='passed', scenario='cancel_during_actual_summary', task_id=task['id'],
                retained_model_response_ids=[r['id'] for r in new], budget_events=store.list('context_budget_events'),
                final_task_status=task['status'], plan_revision=task['revision'])
            return
        task = runtime.recover_plan(task['id'])
        assert task['status'] == 'queued' and task['revision'] == 1, task
        recovered = next(s for s in task['plan']['steps'] if s['skill'] == 'file.ingest')
        assert recovered['args']['path'] == str(backup)
        assert recovered['args']['metadata']['source'] == 'operator-recovery-constraint'
        response = store.get('model_responses', task['model_response_id'])
        messages = json.dumps(response['request']['messages'], ensure_ascii=False)
        assert 'operator-recovery-constraint' in messages and str(backup) in messages
        assert 'UNSUBMITTED_LATER_MESSAGE' not in messages
        assert response['raw'] and response['response_id'] and response['actual_model']
        manifest = store.get('context_manifests', response['context_manifest_id'])
        assert manifest['phase'] == 'replanning'
        assert next(s for s in manifest['sources'] if s['id'] == 'task-state')['metadata']['provider'] == 'task-state'
        assert next(s for s in manifest['sources'] if s['id'] == 'session')['metadata']['provider'] == 'session'
        assert {'session', 'task-state', 'memory:' + memory['id']} <= set(manifest['included'])
        used_snapshot = next(s for s in manifest['sources'] if s['id'] == 'session')['metadata']['snapshot_id']
        if recovery_budget:
            report['summary_context_evidence'] = [assert_summary_context(store, r, original_snapshot['session'],
                config=task['model_config'], snapshot_id=draft['context_snapshot_id'])
                for r in store.list('model_responses') if r['method'] == 'session_summary']
            derived = store.get('planning_contexts', used_snapshot)
            assert derived['parent_snapshot_id'] == draft['context_snapshot_id']
            assert store.get('planning_contexts', draft['context_snapshot_id']) == original_snapshot
            assert 'session-summary' in manifest['included']
            assert any(e['method'] == 'replanning' and e['status'] == 'reduced' for e in store.list('context_budget_events'))
            report['derived_snapshot_id'] = used_snapshot
            report['budget_events'] = store.list('context_budget_events')
        else:
            assert used_snapshot == draft['context_snapshot_id']
        result = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root), 'run', '--until', task['id']], capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        task = store.get('tasks', task['id'])
        actual = task['steps'][task['plan']['verification']]['result']
        assert task['status'] == 'succeeded' and actual['output']['sha256'] == digest
        assert actual['quiescent'] and actual['evidence']
        report.update(status='passed', task_id=task['id'], snapshot_id=draft['context_snapshot_id'],
            recovered_plan=task['plan'], actual_result=actual, context_manifest=manifest,
            model_response_id=response['id'], provider_response_id=response['response_id'])
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('actual recovery report:', root / 'report.json')
        store.close()
