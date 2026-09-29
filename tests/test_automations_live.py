"""Real file failures, persisted event queue, separate worker and actual model diagnostics."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from robot_agent.actions import Actions, local_principal
from robot_agent.runtime import Runtime
from robot_agent.store import Store
from robot_agent.model_transport import environment_config


def assert_diagnostic_context(store, response, job):
    from robot_agent.context_codec import decode_bundle
    from robot_agent.context_memory import record_hash
    from robot_agent.model_call import ModelCaller
    wire = store.get('context_bundles', response['context_bundle_id'])
    assert record_hash(wire) == response['context_bundle_hash']
    bundle = decode_bundle(wire)
    assert bundle.request.request_id == job['id']
    assert bundle.request.robot_id == job['robot_id']
    assert bundle.request.phase == 'automation_diagnosis'
    assert bundle.request.task_id is None  # Immutable event, not a current task version.
    assert bundle.request.goal.original_input == job['question']
    assert bundle.diagnostics == ()  # No Provider was invoked for this event snapshot.
    assert len(bundle.fragments) == 1
    fragment = bundle.fragments[0]
    assert fragment.content == {'event': {**job['event'], 'data': json.loads(job['event']['data'])},
                                'execution': job['execution']}
    assert fragment.metadata['event_hash'] == record_hash(job['event'])
    assert fragment.metadata['execution_hash'] == record_hash(job['execution'])
    rebuilt = ModelCaller(environment_config()).prepare(response['preparation']['method'],
        response['preparation']['arguments'], context=bundle.fragments)
    assert list(rebuilt.request.messages) == response['request']['messages']
    assert rebuilt.request.response_format == response['request']['response_format']
    assert rebuilt.allocation.as_dict() == response['context_allocation']
    manifest = store.get('context_manifests', response['context_manifest_id'])
    assert manifest['included'] == ['failure-event']
    assert manifest['sources'][0]['evidence_ids'] == list(fragment.evidence_ids)
    return {'record_id': response['id'], 'bundle_hash': response['context_bundle_hash'],
            'manifest_id': response['context_manifest_id'],
            'reconstruction': 'exact_messages_response_format_and_allocation',
            'event_snapshot_match': True}


def actual_failure(store, root, robot='r1'):
    runtime = Runtime(store)
    runtime.install_local_skills([str(root.resolve())])
    source = root.resolve() / (str(uuid.uuid4()) + '.md')
    source.write_bytes(Path('docs/SKILL_PROTOCOL.md').read_bytes())
    task = runtime.submit({'steps': [
        {'id': 'ingest', 'skill': 'file.ingest', 'args': {'path': str(source),
            'metadata': {'kind': 'document', 'encoding': 'utf8', 'source': str(source)}}},
        {'id': 'verify', 'skill': 'asset.verify', 'deps': ['ingest'], 'args': {'asset_id': {'$ref': 'ingest.asset_id'}}}],
        'verification': 'verify'}, robot)
    source.unlink()
    deadline = time.monotonic() + 15
    while task['status'] not in {'failed', 'succeeded'} and time.monotonic() < deadline:
        task = runtime.tick(task['id'])
    assert task['status'] == 'failed' and task['steps']['ingest']['result']['status'] == 'failed', task
    return task


@pytest.mark.live_model
def test_real_event_diagnosis_survives_queue_restart_without_duplicate_calls():
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('explicit actual model invocation required')
    root = Path('.runtime/automation-validation') / str(uuid.uuid4())
    store = Store(root / 'ledger')
    report = {'configured_model': environment_config()['model'], 'mock_used': False, 'simulation_used': False}
    try:
        old = actual_failure(store, root)
        actions = Actions(store)
        principal = local_principal()
        args = {'robot_id': 'r1', 'max_runs': 1,
            'question': '请解释实际文件归档失败的原因，引用事件和执行记录。说明哪些是已记录事实、哪些仍无法确定；不要声称已恢复。'}
        rule = actions.call('automation.create', args, principal, idempotency_key='rule')['result']['automation']
        assert actions.call('automation.create', args, principal, idempotency_key='rule')['result']['automation']['id'] == rule['id']
        other = actual_failure(store, root, 'r2')
        task = actual_failure(store, root)
        def worker(*flags):
            result = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root),
                'automation-worker', *flags], capture_output=True, text=True, timeout=150)
            assert result.returncode == 0, result.stderr + result.stdout
            return result
        worker('--scan-only')
        jobs = store.list('automation_runs')
        assert len(jobs) == 1 and jobs[0]['status'] == 'queued'
        assert jobs[0]['event']['task'] == task['id'] and not store.list('model_responses')
        worker('--scan-only')
        assert len(store.list('automation_runs')) == 1
        # A new actual process consumes persisted work after the scanning process exits.
        processes = [subprocess.Popen([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root),
            'automation-worker', '--once'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        try:
            for process in processes:
                stdout, stderr = process.communicate(timeout=150)
                assert process.returncode == 0, stderr + stdout
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
        job = store.get('automation_runs', jobs[0]['id'])
        assert job['status'] == 'completed', job
        result = job['result']
        response = store.get('model_responses', result['model_response_id'])
        report['context_evidence'] = assert_diagnostic_context(store, response, job)
        observed_error = task['steps']['ingest']['result']['error']
        assert result['explanation']['observed_error'] == observed_error
        assert result['is_execution_evidence'] is False
        assert response['raw'] and response['actual_model'] and response['response_id']
        manifest = store.get('context_manifests', response['context_manifest_id'])
        assert manifest['phase'] == 'automation_diagnosis' and manifest['sources'][0]['metadata']['event_hash'] == job['event_hash']
        messages = json.dumps(response['request']['messages'], ensure_ascii=False)
        source_path = task['plan']['steps'][0]['args']['path']
        assert source_path in messages and task['steps']['ingest']['execution_id'] in messages
        assert set(result['explanation']['record_refs']) == {f"event:{job['event']['seq']}", 'execution:' + job['execution']['id']}
        assert any(word in result['explanation']['summary'].lower() for word in ['不存在', '缺失', '找不到', 'missing', 'no such', 'not found'])
        assert store.get('tasks', task['id']) == task
        count = len(store.list('model_responses'))
        another = actual_failure(store, root)
        worker('--once')
        assert len(store.list('automation_runs')) == 1 and len(store.list('model_responses')) == count == 1
        assert store.get('tasks', another['id']) == another
        report.update(status='passed', rule=store.get('automations', rule['id']), run=job,
            actual_model_response={'id': response['id'], 'actual_model': response['actual_model'], 'response_id': response['response_id']},
            context_manifest=manifest, actual_failed_task_id=task['id'], ignored_old_task_id=old['id'], ignored_other_robot_task_id=other['id'],
            budget_excluded_task_id=another['id'], model_calls=count, actual_error=observed_error,
            checks=['old events excluded', 'robot scope', 'idempotent rule create', 'duplicate scan', 'queued process restart',
                    'actual request content', 'exact error and evidence references', 'semantic missing-file explanation',
                    'task state unchanged', 'bounded calls and repeated worker restart', 'concurrent workers deduplicated'])
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        print('actual automation report:', root / 'report.json')
        store.close()


def test_pause_scope_and_event_integrity_before_any_model_send(tmp_path):
    from robot_agent.actions import Principal
    from robot_agent.automations import run_once
    from robot_agent.contracts import ContractError
    store = Store(tmp_path / 'ledger')
    try:
        actions, principal = Actions(store), local_principal()
        def call(name, args, key):
            return actions.call(name, args, principal, idempotency_key=key)['result']
        rule = call('automation.create', {'robot_id': 'r1', 'max_runs': 3, 'question': '解释记录的失败'}, 'rule')['automation']
        stranger = Principal('another-owner', principal.permissions, principal.robots, 'cli')
        with pytest.raises(ContractError, match='not owned'):
            actions.call('automation.runs', {'automation_id': rule['id']}, stranger)
        restricted = Principal(principal.subject, principal.permissions, frozenset({'r2'}), 'cli')
        with pytest.raises(ContractError):
            run_once(store, restricted, scan_only=True)
        rule = call('automation.set-enabled', {'automation_id': rule['id'], 'expected_revision': rule['revision'], 'enabled': False}, 'pause')['automation']
        actual_failure(store, tmp_path)
        run_once(store, principal, scan_only=True)
        assert not store.list('automation_runs')
        rule = call('automation.set-enabled', {'automation_id': rule['id'], 'expected_revision': rule['revision'], 'enabled': True}, 'resume')['automation']
        run_once(store, principal, scan_only=True)
        assert not store.list('automation_runs')
        actual_failure(store, tmp_path)
        run_once(store, principal, scan_only=True)
        first = store.list('automation_runs')[0]
        rule = call('automation.set-enabled', {'automation_id': rule['id'], 'expected_revision': rule['revision'], 'enabled': False}, 'pause-queued')['automation']
        run_once(store, principal)
        assert store.get('automation_runs', first['id'])['status'] == 'canceled'
        rule = call('automation.set-enabled', {'automation_id': rule['id'], 'expected_revision': rule['revision'], 'enabled': True}, 'resume-again')['automation']
        actual_failure(store, tmp_path)
        run_once(store, principal, scan_only=True)
        pending = next(j for j in store.list('automation_runs') if j['status'] == 'queued')
        store.db.execute('UPDATE events SET data=? WHERE seq=?', ('{}', pending['event']['seq']))
        run_once(store, principal)
        failed = store.get('automation_runs', pending['id'])
        assert failed['status'] == 'failed' and failed['error'] == 'automation event changed'
        with pytest.raises(ContractError, match='not owned'):
            actions.call('automation.retry', {'run_id': failed['id'], 'expected_status': 'failed'}, stranger,
                         idempotency_key='foreign-retry')
        with pytest.raises(ContractError, match='not eligible'):
            call('automation.retry', {'run_id': first['id'], 'expected_status': 'failed'}, 'canceled-retry')
        retry = call('automation.retry', {'run_id': failed['id'], 'expected_status': 'failed'}, 'retry-corrupted')['run']
        run_once(store, principal)
        assert store.get('automation_runs', retry['id'])['status'] == 'failed'
        assert not store.list('model_responses')
    finally:
        store.close()


@pytest.mark.live_model
@pytest.mark.parametrize('stop_signal', ['kill', 'interrupt'])
def test_actual_worker_kill_does_not_replay_uncertain_request(stop_signal):
    if os.environ.get('RUN_LIVE_MODEL_TESTS') != '1':
        pytest.skip('explicit actual model invocation required')
    from urllib.parse import urlparse
    root = Path('.runtime/automation-crash-validation') / str(uuid.uuid4())
    store = Store(root / 'ledger')
    process = None
    report = {'mock_used': False, 'simulation_used': False, 'configured_model': environment_config()['model']}
    try:
        principal = local_principal()
        Actions(store).call('automation.create', {'robot_id': 'r1', 'max_runs': 3,
            'question': '解释这次实际文件缺失造成的失败，逐项区分观察到的错误与未知情况，准确引用事件和执行记录。'},
            principal, idempotency_key='crash-rule')
        first = actual_failure(store, root)
        command = [sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root), 'automation-worker', '--once']
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        endpoint = urlparse(environment_config()['endpoint'])
        port = endpoint.port or (443 if endpoint.scheme == 'https' else 80)
        deadline = time.monotonic() + 60
        connected = []
        while time.monotonic() < deadline and process.poll() is None:
            records = store.list('model_responses')
            if records and records[0]['status'] == 'requesting':
                sockets = set()
                for fd in (Path('/proc') / str(process.pid) / 'fd').iterdir():
                    try:
                        link = os.readlink(fd)
                    except FileNotFoundError:
                        continue
                    if link.startswith('socket:['):
                        sockets.add(link[8:-1])
                for family in ('tcp', 'tcp6'):
                    for line in (Path('/proc') / str(process.pid) / 'net' / family).read_text().splitlines()[1:]:
                        fields = line.split()
                        if fields[9] in sockets and fields[3] == '01' and int(fields[2].split(':')[-1], 16) == port:
                            connected.append({'family': family, 'socket_inode': fields[9], 'remote_port': port})
                if connected:
                    # Real OS termination while this worker owns a requesting record
                    # and an established model connection. Provider receipt is unknown.
                    if stop_signal == 'kill':
                        process.kill()
                    else:
                        import signal
                        process.send_signal(signal.SIGINT)
                    process.communicate(timeout=15)
                    break
            time.sleep(0.01)
        assert connected and process.returncode == (-9 if stop_signal == 'kill' else 130), 'did not interrupt an actual connected model worker'
        job = store.list('automation_runs')[0]
        response = store.get('model_responses', job['id'])
        assert job['status'] == ('running' if stop_signal == 'kill' else 'unresolved') and response['status'] == 'requesting'
        assert response['request']['messages'] and 'raw' not in response
        report['interrupted_context_evidence'] = assert_diagnostic_context(store, response, job)
        def restart():
            result = subprocess.run(command, capture_output=True, text=True, timeout=150)
            assert result.returncode == 0, result.stderr + result.stdout
        restart()
        unresolved = store.get('automation_runs', job['id'])
        assert unresolved['status'] == 'unresolved' and unresolved['model_response_id'] == response['id']
        assert len(store.list('model_responses')) == 1
        assert store.get('tasks', first['id']) == first
        second = actual_failure(store, root)
        restart()
        completed = next(j for j in store.list('automation_runs') if j['status'] == 'completed')
        real = store.get('model_responses', completed['model_response_id'])
        assert real['status'] == 'validated' and real['raw'] and real['response_id'] and real['actual_model']
        assert real['parsed']['observed_error'] == second['steps']['ingest']['result']['error']
        assert real['parsed'] == completed['result']['explanation']
        report['completed_context_evidence'] = assert_diagnostic_context(store, real, completed)
        restart()
        assert len(store.list('model_responses')) == 2 and store.get('automation_runs', job['id']) == unresolved
        assert store.get('tasks', second['id']) == second
        from robot_agent.contracts import ContractError
        retry_args = {'run_id': unresolved['id'], 'expected_status': 'unresolved'}
        actions = Actions(store)
        retry = actions.call('automation.retry', retry_args, principal, idempotency_key='explicit-retry')['result']['run']
        repeated = actions.call('automation.retry', retry_args, principal, idempotency_key='explicit-retry')['result']['run']
        assert retry['id'] == repeated['id'] and retry['retry_of'] == unresolved['id']
        restart()
        retried = store.get('automation_runs', retry['id'])
        retry_response = store.get('model_responses', retried['model_response_id'])
        assert retried['status'] == 'completed' and retry_response['raw'] and retry_response['response_id']
        assert retried['result']['explanation']['observed_error'] == first['steps']['ingest']['result']['error']
        report['retry_context_evidence'] = assert_diagnostic_context(store, retry_response, retried)
        original_bundle = store.get('context_bundles', response['context_bundle_id'])
        retry_bundle = store.get('context_bundles', retry_response['context_bundle_id'])
        assert original_bundle['fragments'] == retry_bundle['fragments']
        assert original_bundle['request']['request_id'] != retry_bundle['request']['request_id']
        assert store.get('automation_runs', unresolved['id']) == unresolved
        with pytest.raises(ContractError, match='budget exhausted'):
            actions.call('automation.retry', retry_args, principal, idempotency_key='over-budget-retry')
        restart()
        assert len(store.list('model_responses')) == 3
        report.update(status='passed', stop_signal=stop_signal, interrupted_pid=process.pid, exit_code=process.returncode,
            connected_sockets=connected, interrupted_request=unresolved, completed_run=completed,
            actual_response_id=real['response_id'], actual_model=real['actual_model'], actual_failed_task_ids=[first['id'], second['id']],
            provider_receipt_of_interrupted_request='unknown', interrupted_response='not received or persisted; never fabricated',
            explicit_retry=retried, explicit_retry_response_id=retry_response['response_id'],
            model_records=3, checks=['real process signal: ' + stop_signal, 'established model connection', 'unresolved after restart',
                'no automatic replay', 'next actual event completes with real response', 'response and job committed together',
                'task states unchanged', 'explicit retry is idempotent and budgeted', 'original uncertainty retained'])
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.communicate(timeout=15)
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        print('actual automation crash report:', root / 'report.json')
        store.close()
