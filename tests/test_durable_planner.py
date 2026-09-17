import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import sys
import threading
import pytest
from robot_agent.contracts import ContractError
from robot_agent.store import Store
from robot_agent.runtime import Runtime


def test_model_prompt_requires_verification_to_be_a_step_id_string(tmp_path):
    from robot_agent.planner import Planner

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            request = json.loads(self.rfile.read(length))
            instruction = request["messages"][0]["content"]
            verification = (
                "check"
                if '"verification":"step_id"' in instruction
                else {"step_id": "check"}
            )
            content = json.dumps(
                {
                    "steps": [
                        {"id": "read", "skill": "read", "args": {}},
                        {
                            "id": "check",
                            "skill": "check",
                            "args": {},
                            "deps": ["read"],
                        },
                    ],
                    "verification": verification,
                }
            )
            body = json.dumps(
                {
                    "id": "response-1",
                    "model": "qwen3.8-max",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": content, "refusal": None},
                        }
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = Store(tmp_path)
    catalog = {
        "read": {"input_schema": {"type": "object"}},
        "check": {"input_schema": {"type": "object"}, "verifier": True},
    }
    try:
        plan = Planner(
            store,
            {
                "endpoint": f"http://127.0.0.1:{server.server_port}",
                "model": "qwen3.8-max",
            },
        ).plan("read and check", catalog)
        assert plan["verification"] == "check"
    finally:
        store.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_missing_model_config_refuses_planning(tmp_path):
    from robot_agent.planner import Planner

    s = Store(tmp_path)
    with pytest.raises(ContractError):
        Planner(s, {}).plan("inspect", {})
    assert not s.list("model_responses")
    s.close()


def test_cli_durable_workflow_and_second_process_read(tmp_path):
    s = Store(tmp_path / "state")
    rt = Runtime(s)
    rt.install_local_skills([str(tmp_path)])
    p = tmp_path / "document"
    p.write_text("real persistent workflow input")
    body = {
        "steps": [
            {
                "id": "save",
                "skill": "file.ingest",
                "args": {
                    "path": str(p),
                    "metadata": {
                        "kind": "document",
                        "source": "test-file",
                        "encoding": "utf8",
                    },
                },
            },
            {
                "id": "check",
                "skill": "asset.verify",
                "args": {"asset_id": {"$ref": "save.asset_id"}},
                "deps": ["save"],
            },
        ],
        "verification": "check",
    }
    task = rt.submit(body, "r1")["id"]
    s.close()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "robot_agent.cli",
            "--root",
            str(tmp_path / "state"),
            "run",
            "--until",
            task,
        ],
        capture_output=True,
        text=True,
        timeout=35,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "robot_agent.cli",
            "--root",
            str(tmp_path / "state"),
            "status",
            task,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "succeeded"
    assert (tmp_path / "state/workflows.sqlite").exists()
    s = Store(tmp_path / "state")
    assert len(s.list("assets")) == 1
    s.close()


def test_agent_does_not_submit_task_without_actual_model_response(tmp_path):
    s = Store(tmp_path)
    rt = Runtime(s)
    rt.install_local_skills([str(tmp_path)])
    with pytest.raises(ContractError):
        rt.submit_goal("organize observations", "r1", {})
    assert s.list("tasks") == []
    s.close()


def test_failed_actual_model_replan_consumes_budget_without_default_plan(tmp_path):
    s = Store(tmp_path / "state")
    rt = Runtime(s)
    rt.install_local_skills([str(tmp_path)])
    plan = {
        "steps": [
            {
                "id": "read",
                "skill": "file.ingest",
                "args": {
                    "path": str(tmp_path / "absent"),
                    "metadata": {
                        "kind": "document",
                        "source": "local",
                        "encoding": "utf8",
                    },
                },
            }
        ],
        "verification": "read",
    }
    task = rt.submit(
        plan,
        "r1",
        goal="read input",
        agent_context={
            "model_config": {
                "endpoint": "http://127.0.0.1:1",
                "model": "unavailable",
                "timeout": 0.1,
            },
            "max_replans": 1,
            "replans": 0,
        },
    )["id"]
    assert rt.tick(task)["status"] == "replanning"
    failed = rt.recover_plan(task)
    assert failed["status"] == "failed"
    assert failed["replans"] == 1 and failed["revision"] == 0
    assert len(s.list("model_responses")) == 1
    assert s.list("model_responses")[0]["status"] == "rejected"
    rt.recover_plan(task)
    assert len(s.list("model_responses")) == 1
    assert not s.leases()
    s.close()
