"""Live environment model -> persisted session -> real worker -> actual bytes.

No substitute responses or service doubles. Artifacts remain under .runtime.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from robot_agent.actions import Actions, local_principal
from robot_agent.model_transport import environment_config
from robot_agent.runtime import Runtime
from robot_agent.store import Store


def assert_goal_context_evidence(store):
    from robot_agent.context_codec import decode_bundle
    from robot_agent.context_memory import record_hash
    from robot_agent.model_call import ModelCaller
    evidence = []
    for record in store.list('model_responses'):
        if record['method'] not in {'goal_analysis', 'goal_clarification'}:
            continue
        wire = store.get('context_bundles', record['context_bundle_id'])
        assert record_hash(wire) == record['context_bundle_hash']
        bundle = decode_bundle(wire)
        assert bundle.request.session_id == record['session_id']
        manifest = store.get('context_manifests', record['context_manifest_id'])
        assert manifest['request_id'] == bundle.request.request_id
        assert {d['provider'] for d in manifest['provider_diagnostics']} == {d['provider'] for d in bundle.diagnostics}
        assert any(d['provider'] == 'session' and d['included'] for d in manifest['provider_diagnostics'])
        rebuilt = ModelCaller(environment_config()).prepare(record['preparation']['method'],
            record['preparation']['arguments'], context=bundle.fragments)
        assert list(rebuilt.request.messages) == record['request']['messages']
        assert rebuilt.request.response_format == record['request']['response_format']
        assert rebuilt.allocation.as_dict() == record['context_allocation']
        assert record['status'] == 'validated' and record['raw'] and record['response_id']
        assert json.loads(record['raw'])['id'] == record['response_id']
        evidence.append({'id': record['id'], 'method': record['method'],
            'bundle_hash': record['context_bundle_hash'], 'manifest_id': record['context_manifest_id'],
            'request_hash': record_hash(record['request']),
            'raw_response_sha256': hashlib.sha256(record['raw'].encode()).hexdigest(),
            'reconstruction': 'exact_messages_response_format_and_allocation'})
    assert evidence
    return evidence


@pytest.mark.live_model
def test_live_goal_session_plan_and_actual_file_execution():
    if os.environ.get("RUN_LIVE_MODEL_TESTS") != "1":
        pytest.skip("requires explicit live model invocation")
    config = environment_config()
    directory = Path(".runtime/application-validation") / str(uuid.uuid4())
    directory.mkdir(parents=True)
    source = (directory / "operator-note.txt").resolve()
    source.write_text("真实模型生成计划后的实际文件验收。\n任务标识：" + directory.name + "\n", encoding="utf-8")
    expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    store = Store(directory / "ledger")
    Runtime(store).install_local_skills([str(directory.resolve())])
    actions = Actions(store)
    principal = local_principal()
    def call(name, args):
        return actions.call(name, args, principal, idempotency_key=str(uuid.uuid4()))["result"]
    report = {"root": str(directory.resolve()), "configured_model": config["model"], "started_at": time.time()}
    try:
        goal = (
            f"请归档本机文件 {source}，并校验归档资产字节完整性。文件已经由操作者实际读取确认存在，"
            f"UTF-8 文本，SHA256 为 {expected_hash}。robot_id=r1 是本次文件任务的命名空间，不涉及机器人运动。"
            "使用已注册 file.ingest 读取并归档该路径，metadata 指定 kind=document、encoding=utf8、source=operator-note。"
            "后续使用已注册 asset.verify 校验上一步实际返回的 asset_id，最终验证步骤必须是该 asset.verify。"
            "不需要复制到另一个路径；资产存储目录由系统配置。完成标准是读取实际归档字节并确认哈希一致。"
        )
        session = call("session.create", {"robot_id": "r1", "goal": goal})["session"]
        report["session_id"] = session["id"]
        version = {"session_id": session["id"], "expected_revision": session["revision"]}
        session = call("goal.analyze", version)["session"]
        report["analysis"] = session["analysis"]
        assert session["analysis"]["status"] in {"ready", "needs_grounding"}, session["analysis"]
        version["expected_revision"] = session["revision"]
        draft = call("plan.propose", version)["draft"]
        report["draft_id"] = draft["id"]
        report["plan"] = draft["plan"]
        assert any(s["skill"] == "file.ingest" for s in draft["plan"]["steps"])
        assert draft["plan"]["steps"][-1]["skill"] == "asset.verify"
        receipt = call("plan.submit", {**version, "draft_id": draft["id"], "plan_hash": draft["plan_hash"]})
        report["command_id"] = receipt["command_id"]
        report["task_id"] = receipt["task_id"]
        assert receipt["status"] == "accepted" and not receipt["confirmed_stopped"]
        process = subprocess.run([sys.executable, "-m", "robot_agent.cli", "--root", str(store.root),
                                  "run", "--until", receipt["task_id"]], capture_output=True, text=True, timeout=60)
        assert process.returncode == 0, process.stderr
        task = store.get("tasks", receipt["task_id"])
        assert task["status"] == "succeeded", task
        result = task["steps"][task["plan"]["verification"]]["result"]
        assert result["output"]["sha256"] == expected_hash
        assert result["quiescent"] and result["evidence"]
        assert task["session_id"] == session["id"]
        assert task["model_response_id"] == draft["model_response_id"]
        model_records = store.list("model_responses")
        assert len(model_records) >= 2
        for record in model_records:
            assert record["request"]["messages"]
            assert record["raw"] and record["status"] == "validated"
            assert record["actual_model"] and record["response_id"]
        report['goal_context_evidence'] = assert_goal_context_evidence(store)
        report.update(status="passed", result=result, expected_sha256=expected_hash,
                      model_records=[{"id": r["id"], "method": r["method"], "actual_model": r["actual_model"],
                                      "response_id": r["response_id"]} for r in model_records])
    except Exception as exc:
        report.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        raise
    finally:
        report["finished_at"] = time.time()
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print("actual validation report:", directory / "report.json")
        store.close()


@pytest.mark.live_model
def test_live_multiturn_clarification_and_actual_failure_explanation():
    if os.environ.get("RUN_LIVE_MODEL_TESTS") != "1":
        pytest.skip("requires explicit live model invocation")
    from robot_agent.memory import Memory
    directory = Path('.runtime/application-validation') / str(uuid.uuid4())
    directory.mkdir(parents=True)
    store = Store(directory / 'ledger')
    Runtime(store).install_local_skills([str(directory.resolve())])
    actions = Actions(store)
    principal = local_principal()
    report = {'root': str(directory.resolve()), 'kind': 'clarification-and-failure-explanation'}
    def call(name, args):
        return actions.call(name, args, principal, idempotency_key=str(uuid.uuid4()))['result']
    try:
        session = call('session.create', {'robot_id': 'r1', 'goal': '帮我归档那个文件并检查归档是否完整。'})['session']
        session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
        assert session['analysis']['questions'], session['analysis']
        report['clarification_questions'] = session['analysis']['questions']
        path = (directory / 'actual-note.txt').resolve()
        path.write_text('多轮澄清的真实文件证据。', encoding='utf-8')
        asset = Memory(store).ingest(path, {'kind': 'document', 'source': str(path), 'encoding': 'utf8'})
        session = call('session.message', {'session_id': session['id'], 'expected_revision': session['revision'],
            'content': f'目标文件是 {path}，已实际读取。归档到系统资产库即可，metadata 为 kind=document、source=operator、encoding=utf8，使用 file.ingest 和 asset.verify。不要另建外部副本。'})['session']
        session = call('session.attach-assets', {'session_id': session['id'], 'expected_revision': session['revision'], 'asset_ids': [asset['id']]})['session']
        session = call('goal.analyze', {'session_id': session['id'], 'expected_revision': session['revision']})['session']
        assert not session['analysis']['questions'], session['analysis']
        missing = (directory / 'does-not-exist.txt').resolve()
        assert not missing.exists()
        plan = {'steps': [{'id': 'read', 'skill': 'file.ingest', 'args': {'path': str(missing),
            'metadata': {'kind': 'document', 'source': 'operator-selected-missing-file', 'encoding': 'utf8'}}},
            {'id': 'verify', 'skill': 'asset.verify', 'deps': ['read'], 'args': {'asset_id': {'$ref': 'read.asset_id'}}}], 'verification': 'verify'}
        task = Runtime(store).submit(plan, 'r1')
        for _ in range(10):
            task = Runtime(store).tick(task['id'])
            if task['status'] == 'failed':
                break
        assert task['status'] == 'failed', task
        assert task['steps']['read']['result']['status'] == 'failed'
        session = call('selection.set', {'session_id': session['id'], 'expected_revision': session['revision'],
            'task_id': task['id'], 'task_revision': task['revision'], 'task_generation': task['generation'], 'step_ids': ['read']})['session']
        result = call('task.explain', {'session_id': session['id'], 'expected_revision': session['revision'],
            'question': '这个节点为什么失败？请指出实际文件名和已记录错误，不要把猜测说成事实。'})
        assert result['is_execution_evidence'] is False
        assert result['explanation']['record_refs'] == [task['id'] + ':read']
        assert 'does-not-exist.txt' in result['explanation']['summary']
        assert any(x in result['explanation']['summary'] for x in ['不存在', '未找到', '找不到', 'No such file', 'not exist'])
        assert store.get('tasks', task['id'])['status'] == 'failed'
        from robot_agent.context_codec import decode_bundle
        from robot_agent.context_memory import record_hash
        from robot_agent.model_call import ModelCaller
        record = store.get('model_responses', result['model_response_id'])
        wire = store.get('context_bundles', record['context_bundle_id'])
        assert record_hash(wire) == record['context_bundle_hash']
        bundle = decode_bundle(wire)
        assert bundle.request.task_id == task['id']
        assert bundle.request.revision == task['revision']
        manifest = store.get('context_manifests', record['context_manifest_id'])
        assert manifest['request_id'] == bundle.request.request_id
        assert manifest['provider_diagnostics']
        assert {d['provider'] for d in manifest['provider_diagnostics']} == {d['provider'] for d in bundle.diagnostics}
        rebuilt = ModelCaller(environment_config()).prepare(record['preparation']['method'],
            record['preparation']['arguments'], context=bundle.fragments)
        assert list(rebuilt.request.messages) == record['request']['messages']
        assert rebuilt.request.response_format == record['request']['response_format']
        assert list(f.id for f in rebuilt.allocation.included) == manifest['included']
        assert record['raw'] and record['actual_model'] and record['response_id']
        task_fragment = next(f for f in bundle.fragments if f.kind == 'task_state')
        assert 'does-not-exist.txt' in json.dumps(task_fragment.content)
        report['context_evidence'] = {'bundle_id': record['context_bundle_id'],
            'bundle_hash': record['context_bundle_hash'], 'manifest_id': record['context_manifest_id'],
            'providers': manifest['provider_diagnostics'],
            'actual_request_reconstruction': 'exact_messages_and_response_format',
            'request_hash': record_hash(record['request']),
            'raw_response_sha256': hashlib.sha256(record['raw'].encode()).hexdigest()}
        report['goal_context_evidence'] = assert_goal_context_evidence(store)
        assert any(e['method'] == 'goal_clarification' for e in report['goal_context_evidence'])
        report.update(status='passed', session_id=session['id'], task_id=task['id'], explanation=result,
                      actual_model_records=[{'id': r['id'], 'method': r['method'], 'actual_model': r.get('actual_model'),
                                             'response_id': r.get('response_id')} for r in store.list('model_responses')])
    except Exception as exc:
        report.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('actual validation report:', directory / 'report.json')
        store.close()
