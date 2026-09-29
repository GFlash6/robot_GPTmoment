"""Authenticated incremental reads over real worker-generated task events."""
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import threading

import httpx
import pytest

from robot_agent.actions import Principal
from robot_agent.application import make_server
from robot_agent.runtime import Runtime
from robot_agent.store import Store


def test_http_event_pages_preserve_checkpoint_and_scope_across_reconnect(tmp_path):
    store = Store(tmp_path / 'ledger')
    runtime = Runtime(store); runtime.install_local_skills([str(tmp_path)])
    source = tmp_path / 'protocol.md'; source.write_bytes(Path('docs/SKILL_PROTOCOL.md').read_bytes())
    plan = {'steps': [
        {'id': 'ingest', 'skill': 'file.ingest', 'args': {'path': str(source),
            'metadata': {'kind': 'document', 'encoding': 'utf8', 'source': str(source)}}},
        {'id': 'verify', 'skill': 'asset.verify', 'deps': ['ingest'], 'args': {'asset_id': {'$ref': 'ingest.asset_id'}}}],
        'verification': 'verify'}
    task = runtime.submit(plan, 'r1')
    other = runtime.submit(plan, 'r2')
    token, other_token = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    principal = Principal('reader', frozenset({'tasks.read'}), frozenset({'r1'}), 'http')
    server = make_server(store.root, {token: principal,
        other_token: Principal('other-reader', frozenset({'tasks.read'}), frozenset({'r2'}), 'http')}, port=0)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    def page(args, *, bearer=token, expected=200):
        # A new connection for every page exercises cursor-based reconnection.
        with httpx.Client(trust_env=False) as client:
            response = client.post(f'http://127.0.0.1:{port}/actions/task.events-page',
                headers={'Authorization': 'Bearer ' + bearer}, json={'task_id': task['id'], **args})
            assert response.status_code == expected, response.text
            return response.json().get('result')
    try:
        first = page({'limit': 1})
        assert len(first['events']) == 1 and first['events'][0]['type'] == 'submitted'
        assert not first['has_more']
        worker = subprocess.run([sys.executable, '-m', 'robot_agent.cli', '--root', str(store.root),
            'run', '--until', task['id']], capture_output=True, text=True, timeout=60)
        assert worker.returncode == 0, worker.stderr
        finished = store.get('tasks', task['id'])
        assert finished['status'] == 'succeeded'
        executions_before = store.list('executions')
        assert len([e for e in executions_before if e['task_id'] == task['id']]) == 2
        assert finished['steps']['verify']['result']['output']['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert page({'limit': 1, 'through_seq': first['through_seq']}) == first
        bounded = page({'after_seq': first['next_seq'], 'through_seq': first['through_seq']})
        assert bounded['events'] == [] and not bounded['has_more']
        next_page = page({'after_seq': first['next_seq'], 'limit': 1})
        assert next_page['has_more'] and next_page['through_seq'] > first['through_seq']
        assert page({'after_seq': first['next_seq'], 'through_seq': next_page['through_seq'], 'limit': 1}) == next_page
        raw_events = store.events(task['id'])
        expected = [{**event, 'data': json.loads(event['data'])} for event in raw_events]
        collected = first['events'] + next_page['events']
        cursor, upper = next_page['next_seq'], next_page['through_seq']
        server.shutdown(); server.server_close(); thread.join()
        server = make_server(store.root, {token: principal,
            other_token: Principal('other-reader', frozenset({'tasks.read'}), frozenset({'r2'}), 'http')}, port=port)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        while next_page['has_more']:
            next_page = page({'after_seq': cursor, 'through_seq': upper, 'limit': 1})
            assert next_page['next_seq'] > cursor
            collected.extend(next_page['events']); cursor = next_page['next_seq']
        assert collected == expected
        assert len({e['seq'] for e in collected}) == len(expected)
        assert any(b['seq'] > a['seq'] + 1 for a, b in zip(collected, collected[1:]))
        assert page({'after_seq': cursor})['events'] == []
        foreign_cursor = store.events(other['id'])[0]['seq']
        page({'after_seq': foreign_cursor}, expected=400)
        page({'after_seq': upper + 1}, expected=400)
        page({'limit': 501}, expected=400)
        page({'after_seq': cursor}, bearer=other_token, expected=403)
        assert store.events(task['id']) == raw_events
        assert store.list('executions') == executions_before and not store.list('model_responses')
    finally:
        server.shutdown(); server.server_close(); thread.join(); store.close()
