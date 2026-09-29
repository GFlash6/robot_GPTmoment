"""Actual file/HTTP/process integration; no model or robot substitutes."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading

import httpx
import pytest

from robot_agent.actions import Actions, ActionError, Principal, local_principal, process_commands
from robot_agent.application import make_server
from robot_agent.runtime import Runtime
from robot_agent.store import Store


def setup_ledger(tmp_path):
    store = Store(tmp_path / "ledger")
    Runtime(store).install_local_skills([str(tmp_path)])
    source = tmp_path / "source.txt"
    source.write_text("实际文件操作 · application action integration\n", encoding="utf-8")
    plan = {"steps": [
        {"id": "read", "skill": "file.ingest", "args": {"path": str(source),
            "metadata": {"kind": "document", "source": "actual-integration-file", "encoding": "utf8"}}},
        {"id": "verify", "skill": "asset.verify", "deps": ["read"], "args": {"asset_id": {"$ref": "read.asset_id"}}},
    ], "verification": "verify"}
    return store, source, {"plan": plan, "robot_id": "r1"}


def worker(root, task_id):
    result = subprocess.run([sys.executable, "-m", "robot_agent.cli", "--root", str(root),
                             "run", "--until", task_id], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_actual_http_submission_concurrency_worker_restart_and_file_evidence(tmp_path):
    store, source, body = setup_ledger(tmp_path)
    token = secrets.token_urlsafe(32)
    server = make_server(store.root, {token: local_principal()}, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": "same-intent"}
    try:
        def submit(_):
            with httpx.Client(trust_env=False) as client:
                response = client.post(url + "/actions/task.submit", json=body, headers=headers)
                assert response.status_code == 202, response.text
                return response.json()["result"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(submit, range(4)))
        assert len({r["task_id"] for r in receipts}) == 1
        assert len(store.list("commands")) == 1
        assert not store.list("tasks")
        task_id = receipts[0]["task_id"]
        result = worker(store.root, task_id)
        assert result["status"] == "succeeded"
        actual = result["steps"]["verify"]["result"]
        assert actual["quiescent"] is True
        assert actual["output"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert actual["evidence"]
        before = store.list("executions")
        assert worker(store.root, task_id)["status"] == "succeeded"
        assert store.list("executions") == before
        with httpx.Client(trust_env=False) as client:
            response = client.post(url + "/actions/task.submit", json=body, headers=headers)
            assert response.json()["result"]["status"] == "applied"
            assert response.json()["result"]["confirmed_stopped"] is False
            conflict = client.post(url + "/actions/task.submit", json={**body, "priority": 7}, headers=headers)
            assert conflict.status_code == 409
            denied = client.post(url + "/actions/task.submit", json=body)
            assert denied.status_code == 401
        assert len(store.list("tasks")) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        store.close()


def test_cancel_precedes_resume_and_task_version_is_rechecked(tmp_path):
    store, _, body = setup_ledger(tmp_path)
    actions = Actions(store)
    principal = local_principal()
    try:
        receipt = actions.call("task.submit", body, principal, idempotency_key="submit")["result"]
        process_commands(store)
        version = {"task_id": receipt["task_id"], "expected_revision": 0, "expected_generation": 0}
        pause = actions.call("task.pause", version, principal, idempotency_key="pause")["result"]
        process_commands(store)
        assert store.get("commands", pause["command_id"])["status"] == "applied"
        assert Runtime(store).tick(receipt["task_id"])["status"] == "paused"
        actions.call("task.cancel", version, principal, idempotency_key="cancel")
        resume = actions.call("task.resume", version, principal, idempotency_key="resume")["result"]
        process_commands(store)
        assert store.get("commands", resume["command_id"])["status"] == "rejected"
        result = worker(store.root, receipt["task_id"])
        assert result["status"] == "canceled"
        assert not store.list("executions")
        with pytest.raises(ActionError, match="version changed"):
            actions.call("task.pause", version, principal, idempotency_key="stale")
    finally:
        store.close()


def test_scope_checks_and_catalog_binding(tmp_path):
    store, _, body = setup_ledger(tmp_path)
    try:
        principal = Principal("reader", frozenset({"tasks.read"}), frozenset({"r2"}), "http")
        actions = Actions(store)
        with pytest.raises(ActionError):
            actions.call("task.submit", body, principal, idempotency_key="forbidden")
        receipt = actions.call("task.submit", body, local_principal(), idempotency_key="submit")["result"]
        spec = store.get("skills", "asset.verify")
        spec["execution_timeout"] = 88
        Runtime(store).register("asset.verify", spec)
        process_commands(store)
        command = store.get("commands", receipt["command_id"])
        assert command["status"] == "rejected" and command["error"]["code"] == "STALE_CATALOG"
        assert not store.list("tasks")
        task = Runtime(store).submit(body["plan"], "r1")
        with pytest.raises(ActionError):
            actions.call("task.get", {"task_id": task["id"]}, principal)
        assert actions.call("task.list", {}, principal)["result"]["items"] == []
    finally:
        store.close()


def test_process_exit_before_command_commit_rolls_back_task_and_receipt(tmp_path):
    store, _, body = setup_ledger(tmp_path)
    try:
        receipt = Actions(store).call("task.submit", body, local_principal(), idempotency_key="crash")["result"]
        # Exercise an actual uncommitted transition in a process that exits abruptly.
        script = '''import os,sys
from robot_agent.store import Store
from robot_agent.actions import apply_command
s=Store(sys.argv[1])
with s.transaction():
    apply_command(s,s.get("commands",sys.argv[2]))
    os._exit(17)
'''
        result = subprocess.run([sys.executable, "-c", script, str(store.root), receipt["command_id"]])
        assert result.returncode == 17
        assert store.get("tasks", receipt["task_id"]) is None
        assert store.get("commands", receipt["command_id"])["status"] == "accepted"
        assert worker(store.root, receipt["task_id"])["status"] == "succeeded"
        assert len(store.list("tasks")) == 1
    finally:
        store.close()


def test_session_selection_actual_version_change_and_verified_asset_context(tmp_path):
    from robot_agent.context_builder import ContextBuilder
    from robot_agent.context_models import ContextRequest, GoalContext
    from robot_agent.contracts import ContractError
    from robot_agent.memory import Memory
    store, source, body = setup_ledger(tmp_path)
    principal = local_principal()
    actions = Actions(store)
    def call(name, args, key):
        return actions.call(name, args, principal, idempotency_key=key)['result']
    try:
        session = call('session.create', {'robot_id': 'r1', 'goal': '检查实际文件归档结果'}, 'session')['session']
        task = Runtime(store).submit(body['plan'], 'r1')
        session = call('selection.set', {'session_id': session['id'], 'expected_revision': session['revision'],
            'task_id': task['id'], 'task_revision': 0, 'task_generation': 0, 'step_ids': ['read']}, 'selection')['session']
        asset = Memory(store).ingest(source, {'kind': 'document', 'encoding': 'utf8', 'source': str(source)})
        session = call('session.attach-assets', {'session_id': session['id'], 'expected_revision': session['revision'], 'asset_ids': [asset['id']]}, 'evidence')['session']
        request = ContextRequest('context-request', 'planning', GoalContext.from_input(session['original_input']), robot_id='r1', session_id=session['id'])
        bundle = ContextBuilder(store).build(request, Runtime(store).catalog())
        evidence = next(f for f in bundle.fragments if f.id == 'asset-evidence')
        assert evidence.content[0]['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert next(f for f in bundle.fragments if f.id == 'ui-selection').content['selected_steps']['read']['status'] == 'pending'
        Runtime(store).interrupt(task['id'], 'pause')
        assert Runtime(store).tick(task['id'])['status'] == 'paused'
        Runtime(store).resume(task['id'])
        with pytest.raises(ContractError, match='old task version'):
            ContextBuilder(store).build(request, Runtime(store).catalog())
        other = Principal('different-operator', principal.permissions, principal.robots, 'http')
        with pytest.raises(ActionError, match='another operator'):
            actions.call('session.get', {'session_id': session['id']}, other)
        stale = {'session_id': session['id'], 'expected_revision': 0, 'content': 'old turn'}
        with pytest.raises(ActionError, match='session changed'):
            call('session.message', stale, 'stale-session')
        Path(asset['path']).write_bytes(b'actual on-disk corruption')
        with pytest.raises(ContractError, match='integrity failed'):
            ContextBuilder(store).build(request, Runtime(store).catalog())
    finally:
        store.close()


def test_accepted_cancel_blocks_earlier_queued_revision_and_late_automatic_plan(tmp_path):
    store, _, body = setup_ledger(tmp_path)
    try:
        runtime = Runtime(store)
        task = runtime.submit(body['plan'], 'r1')
        runtime.interrupt(task['id'], 'pause')
        assert runtime.tick(task['id'])['status'] == 'paused'
        version = {'task_id': task['id'], 'expected_revision': 0, 'expected_generation': 0}
        actions = Actions(store)
        revision = actions.call('task.revise', {**version, 'plan': body['plan']}, local_principal(), idempotency_key='revise-first')['result']
        actions.call('task.cancel', version, local_principal(), idempotency_key='cancel-second')
        unchanged = runtime.revise(task['id'], body['plan'], automatic=True, expected_generation=0)
        assert unchanged['revision'] == 0 and unchanged['status'] == 'paused'
        process_commands(store)
        assert store.get('commands', revision['command_id'])['error']['code'] == 'CANCEL_PENDING'
        assert runtime.tick(task['id'])['status'] == 'canceled'
        assert not store.list('executions')
    finally:
        store.close()
