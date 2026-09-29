"""Real authenticated HTTP discovery, commands, worker and byte evidence."""
import hashlib
import secrets
import threading

import httpx
from robot_agent.actions import ACTIONS, Principal, action_catalog, local_principal
from robot_agent.contracts import schema_check
from robot_agent.application import make_server
from test_application_actions import setup_ledger, worker


def test_discovered_contracts_match_real_http_execution_and_audit(tmp_path):
    store, source, body = setup_ledger(tmp_path)
    operator = local_principal()
    reader = Principal('discovery-reader', frozenset({'tasks.read'}), frozenset({'r2'}), 'http')
    token, read_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    server = make_server(store.root, {token: operator, read_token: reader}, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    headers = {'Authorization': 'Bearer ' + token}
    try:
        with httpx.Client(trust_env=False) as client:
            assert client.get(url + '/actions').status_code == 401
            before = store.list('action_calls')
            response = client.get(url + '/actions', headers=headers)
            assert response.status_code == 200
            catalog = response.json()
            assert catalog['catalog_version'] == 1
            entries = catalog['actions']
            assert set(entries) == set(ACTIONS)
            assert entries == action_catalog(operator)
            assert store.list('action_calls') == before  # Discovery itself is not an invocation.
            for name, contract in entries.items():
                assert contract['contract_version'] == 1 and len(contract['contract_hash']) == 64
                assert not contract['dispatches_skill'] and contract['writes_audit_record']
                assert contract['requires_idempotency_key'] == (contract['effect_kind'] != 'read')
            assert entries['plan.propose']['calls_model']
            assert not entries['automation.create']['calls_model']
            assert entries['automation.create']['may_schedule_model']
            assert entries['automation.retry']['effect_kind'] == 'diagnosis_queue'
            assert entries['task.submit']['effect_kind'] == 'task_command'
            restricted = client.get(url + '/actions', headers={'Authorization': 'Bearer ' + read_token}).json()['actions']
            assert set(restricted) == {'task.list', 'task.get', 'task.events', 'task.events-page', 'command.get'}
            schema_check(entries['task.submit']['input_schema'], body)
            missing = client.post(url + '/actions/task.submit', json=body, headers=headers)
            assert missing.status_code == 400 and not store.list('commands')
            submitted = client.post(url + '/actions/task.submit', json=body,
                headers={**headers, 'Idempotency-Key': 'discovery-execution'})
            assert submitted.status_code == 202
            envelope = submitted.json(); receipt = envelope['result']
            schema_check(entries['task.submit']['output_schema'], receipt)
            assert receipt['confirmed_stopped'] is False and not store.list('tasks')
            audit = store.get('action_calls', envelope['action_call_id'])
            assert audit['contract_hash'] == entries['task.submit']['contract_hash']
            assert audit['contract_version'] == 1 and audit['effect_kind'] == 'task_command'
            result = worker(store.root, receipt['task_id'])
            assert result['status'] == 'succeeded'
            assert result['steps']['verify']['result']['output']['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
            denied = client.post(url + '/actions/task.get', json={'task_id': receipt['task_id']},
                headers={'Authorization': 'Bearer ' + read_token})
            assert denied.status_code == 403  # Discoverable is not authorized for this robot.
            read = client.post(url + '/actions/task.get', json={'task_id': receipt['task_id']}, headers=headers)
            assert read.status_code == 200
            schema_check(entries['task.get']['output_schema'], read.json()['result'])
            read_audit = store.get('action_calls', read.json()['action_call_id'])
            assert read_audit['effect_kind'] == 'read'
            assert read_audit['contract_hash'] == entries['task.get']['contract_hash']
            detached = action_catalog(operator)
            detached['task.submit']['input_schema']['properties']['robot_id']['type'] = 'number'
            assert action_catalog(operator)['task.submit']['input_schema']['properties']['robot_id']['type'] == 'string'
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3); store.close()
