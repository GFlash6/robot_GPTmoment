"""Real cross-action key conflicts and concurrent authenticated requests."""
from concurrent.futures import ThreadPoolExecutor
import itertools
import secrets
import threading

import httpx
import pytest

from robot_agent.actions import Actions, ActionError, local_principal
from robot_agent.application import make_server
from test_application_actions import setup_ledger, worker


NAMES = ('automation.create', 'session.create', 'task.submit')


def arguments(body):
    return {'automation.create': {'robot_id': 'r1', 'max_runs': 1, 'question': 'Explain actual failed executions.'},
            'session.create': {'robot_id': 'r1', 'goal': 'Archive the explicitly selected actual file.'},
            'task.submit': body}


@pytest.mark.parametrize('first,second', list(itertools.permutations(NAMES, 2)))
def test_cross_action_key_has_one_owner(tmp_path, first, second):
    store, _, body = setup_ledger(tmp_path)
    actions = Actions(store); principal = local_principal(); args = arguments(body)
    try:
        accepted = actions.call(first, args[first], principal, idempotency_key='one-intent')['result']
        with pytest.raises(ActionError) as rejected:
            actions.call(second, args[second], principal, idempotency_key='one-intent')
        assert rejected.value.code == 'IDEMPOTENCY_CONFLICT'
        assert actions.call(first, args[first], principal, idempotency_key='one-intent')['result'] == accepted
        assert sum(len(store.list(c)) for c in ('commands', 'sessions', 'automations')) == 1
        assert not store.list('model_responses') and not store.list('automation_runs')
    finally:
        store.close()


def test_automation_mutations_share_key_and_keep_original_receipt(tmp_path):
    store, _, body = setup_ledger(tmp_path)
    actions = Actions(store); principal = local_principal(); args = arguments(body)['automation.create']
    try:
        original = actions.call('automation.create', args, principal, idempotency_key='create')['result']
        rule = original['automation']
        edit = {'automation_id': rule['id'], 'expected_revision': 0, 'enabled': False}
        with pytest.raises(ActionError) as conflict:
            actions.call('automation.set-enabled', edit, principal, idempotency_key='create')
        assert conflict.value.code == 'IDEMPOTENCY_CONFLICT'
        with pytest.raises(ActionError) as changed:
            actions.call('automation.create', {**args, 'max_runs': 2}, principal, idempotency_key='create')
        assert changed.value.code == 'IDEMPOTENCY_CONFLICT'
        updated = actions.call('automation.set-enabled', edit, principal, idempotency_key='edit')['result']
        assert not updated['automation']['enabled'] and updated['automation']['revision'] == 1
        assert actions.call('automation.set-enabled', edit, principal, idempotency_key='edit')['result'] == updated
        assert actions.call('automation.create', args, principal, idempotency_key='create')['result'] == original
        assert not store.get('automations', rule['id'])['enabled']
        assert len(store.list('automation_requests')) == 2
    finally:
        store.close()


def test_concurrent_http_cross_action_key_and_real_worker(tmp_path):
    store, source, body = setup_ledger(tmp_path)
    token = secrets.token_urlsafe(32)
    server = make_server(store.root, {token: local_principal()}, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    args = arguments(body)
    headers = {'Authorization': 'Bearer ' + token, 'Idempotency-Key': 'concurrent-intent'}
    barrier = threading.Barrier(3)
    def send(name):
        with httpx.Client(trust_env=False) as client:
            barrier.wait(timeout=10)
            response = client.post(url + '/actions/' + name, headers=headers, json=args[name])
            return name, response.status_code, response.json()
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            responses = list(pool.map(send, NAMES))
        winners = [r for r in responses if r[1] in (200, 202)]
        assert len(winners) == 1, responses
        assert all(r[1] == 409 and r[2]['error']['code'] == 'IDEMPOTENCY_CONFLICT'
                   for r in responses if r not in winners)
        with httpx.Client(trust_env=False) as client:
            name, _, accepted = winners[0]
            replay = client.post(url + '/actions/' + name, headers=headers, json=args[name])
            assert replay.json()['result'] == accepted['result']
            if name == 'task.submit':
                receipt = accepted['result']
            else:
                receipt = client.post(url + '/actions/task.submit', headers={**headers, 'Idempotency-Key': 'file-task'},
                    json=body).json()['result']
        task = worker(store.root, receipt['task_id'])
        import hashlib
        assert task['status'] == 'succeeded'
        assert task['steps']['verify']['result']['output']['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert len(store.list('tasks')) == 1 and not store.list('model_responses')
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3); store.close()
