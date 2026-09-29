"""Actual HTTP endpoint rejects stale control and prevents further file writes."""
import json
from pathlib import Path
import threading

import httpx
import pytest

from robot_agent.contracts import ContractError
from robot_agent.runtime import Runtime
from robot_agent.service import skill_server
from robot_agent.store import Store


def test_stale_authority_cannot_advance_copy_after_endpoint_restart(tmp_path):
    source = tmp_path / 'source.md'
    source.write_bytes(Path('docs/SKILL_PROTOCOL.md').read_bytes())
    target = tmp_path / 'first-copy.md'
    service_store = Store(tmp_path / 'service')
    service_runtime = Runtime(service_store)
    service_runtime.install_local_skills([str(tmp_path)])
    local = {**service_runtime.catalog()['file.copy'], 'fencing_domain': 'disk'}
    service_runtime.register('file.copy', local)
    server = skill_server(service_store)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    client_store = Store(tmp_path / 'client')
    runtime = Runtime(client_store)
    url = f'http://127.0.0.1:{port}'
    runtime.register('file.copy', {**local, 'adapter': 'http', 'endpoint': url, 'resources': {'disk': 1}})
    client_store.set_capacity('r1/disk', 1)
    plan = {'steps': [{'id': 'copy', 'skill': 'file.copy', 'args': {
        'source': str(source), 'target': str(target), 'chunk_bytes': 64}}], 'verification': 'copy'}
    try:
        task = runtime.submit(plan, 'r1'); task = runtime.tick(task['id'])
        assert task['status'] == 'running' and target.stat().st_size == 64
        execution_id = task['steps']['copy']['execution_id']
        original = service_store.get('service_requests', execution_id)['body']
        assert original['authority'] == {'domain': 'disk', 'token': 1}
        with httpx.Client(trust_env=False) as client:
            endpoint = url + '/executions/' + execution_id
            assert client.get(endpoint).status_code == 409
            assert target.stat().st_size == 64
            takeover = {**original, 'execution_id': 'new-controller', 'authority': {'domain': 'disk', 'token': 2},
                'args': {**original['args'], 'target': str(tmp_path / 'second-copy.md')}}
            newer_headers = {'X-Execution-Authority': json.dumps(takeover['authority'])}
            newer = client.put(url + '/executions/new-controller', json=takeover, headers=newer_headers)
            assert newer.status_code == 200 and newer.json()['authority'] == takeover['authority']
            assert (tmp_path / 'second-copy.md').stat().st_size == 64
            old_headers = {'X-Execution-Authority': json.dumps(original['authority'])}
            for response in (client.get(endpoint, headers=old_headers),
                             client.put(endpoint, json=original, headers=old_headers),
                             client.post(endpoint + '/cancel', headers=old_headers)):
                assert response.status_code == 409
                assert 'stale or conflicting' in response.json()['message']
            assert target.stat().st_size == 64
            conflicting = {**takeover, 'execution_id': 'conflicting-owner',
                'args': {**takeover['args'], 'target': str(tmp_path / 'must-not-exist')}}
            assert client.put(url + '/executions/conflicting-owner', json=conflicting, headers=newer_headers).status_code == 409
            assert not (tmp_path / 'must-not-exist').exists()
            server.shutdown(); server.server_close(); thread.join(); service_store.close()
            service_store = Store(tmp_path / 'service')
            server = skill_server(service_store, port=port)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            assert client.get(endpoint, headers=old_headers).status_code == 409
            current = client.get(url + '/executions/new-controller', headers=newer_headers)
            assert current.status_code == 200
            assert (tmp_path / 'second-copy.md').stat().st_size == 128
        task = runtime.tick(task['id'])
        assert task['status'] == 'unknown' and client_store.leases()
        assert target.stat().st_size == 64
        assert len(service_store.list('service_requests')) == 2
        assert not client_store.list('model_responses')
        runtime.interrupt(task['id'], 'cancel')
        with httpx.Client(trust_env=False) as client:
            assert client.post(endpoint + '/reconcile', headers=old_headers).status_code == 409
            future = {'X-Execution-Authority': json.dumps({'domain': 'disk', 'token': 3})}
            assert client.post(endpoint + '/reconcile', headers=future).status_code == 409
            assert target.stat().st_size == 64 and client_store.leases()
            stopped = client.post(endpoint + '/reconcile', headers=newer_headers)
            assert stopped.status_code == 200
            proof = stopped.json()
            assert proof['status'] == 'canceled' and proof['quiescent'] is True
            assert proof['output']['bytes_copied'] == 64 and proof['authority'] == original['authority']
            assert proof['reconciliation']['authority'] == takeover['authority']
            assert client.post(endpoint + '/reconcile', headers=newer_headers).json() == proof
            assert client.get(endpoint, headers=old_headers).json() == proof
            assert client.put(endpoint, json=original, headers=old_headers).status_code == 409
        server.shutdown(); server.server_close(); thread.join(); service_store.close()
        service_store = Store(tmp_path / 'service')
        server = skill_server(service_store, port=port)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        task = runtime.tick(task['id'])
        assert task['status'] == 'canceled' and not client_store.leases()
        assert task['steps']['copy']['result'] == proof
        assert target.stat().st_size == 64 and (tmp_path / 'second-copy.md').stat().st_size == 128
        assert len(service_store.list('service_reconciliations')) == 1
    finally:
        server.shutdown(); server.server_close(); thread.join()
        service_store.close(); client_store.close()


def test_fencing_requires_exclusive_domain_resource(tmp_path):
    store = Store(tmp_path / 'ledger')
    try:
        runtime = Runtime(store); runtime.install_local_skills([str(tmp_path)])
        spec = {**runtime.catalog()['file.copy'], 'adapter': 'http', 'endpoint': 'http://127.0.0.1:1',
                'fencing_domain': 'disk', 'resources': {'disk': 1}}
        runtime.register('file.copy', spec)
        store.set_capacity('r1/disk', 2)
        with pytest.raises(ContractError, match='capacity must be one'):
            runtime.submit({'steps': [{'id': 'copy', 'skill': 'file.copy', 'args': {}}], 'verification': 'copy'}, 'r1')
        assert not store.list('tasks') and not store.list('executions')
    finally:
        store.close()
