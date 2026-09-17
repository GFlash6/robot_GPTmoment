"""A real HTTP server executes file operations, never mocked robot responses."""

import threading
import httpx
import pytest
from robot_agent.store import Store
from robot_agent.runtime import Runtime
from robot_agent.contracts import ContractError


def test_http_copy_cancel_has_real_partial_file_and_stop_evidence(tmp_path):
    from robot_agent.service import skill_server

    source = tmp_path / "source"
    source.write_bytes(__file__.encode() * 100)
    target = tmp_path / "copied"
    server_store = Store(tmp_path / "service")
    server_runtime = Runtime(server_store)
    server_runtime.install_local_skills([str(tmp_path)])
    server = skill_server(server_store, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client_store = Store(tmp_path / "client")
    rt = Runtime(client_store)
    spec = server_runtime.catalog()["file.copy"]
    spec = {
        **spec,
        "adapter": "http",
        "endpoint": f"http://127.0.0.1:{server.server_port}",
        "resources": {"disk": 1},
    }
    rt.register("file.copy", spec)
    client_store.set_capacity("r1/disk", 1)
    try:
        task = rt.submit(
            {
                "steps": [
                    {
                        "id": "copy",
                        "skill": "file.copy",
                        "args": {
                            "source": str(source),
                            "target": str(target),
                            "chunk_bytes": 64,
                        },
                    }
                ],
                "verification": "copy",
            },
            "r1",
        )["id"]
        state = rt.tick(task)
        assert state["status"] == "running"
        assert 0 < target.stat().st_size < source.stat().st_size
        assert client_store.leases()
        rt.interrupt(task, "pause")
        state = rt.tick(task)
        assert state["status"] == "paused"
        assert state["steps"]["copy"]["result"]["status"] == "canceled"
        assert state["steps"]["copy"]["result"]["quiescent"] is True
        assert not client_store.leases()
        size = target.stat().st_size
        with pytest.raises(ContractError):
            rt.resume(task)
        assert target.stat().st_size == size
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        server_store.close()
        client_store.close()


def test_http_same_execution_id_rejects_changed_request(tmp_path):
    from robot_agent.service import skill_server

    s = Store(tmp_path / "state")
    Runtime(s).install_local_skills([str(tmp_path)])
    server = skill_server(s, "127.0.0.1", 0)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    p = tmp_path / "real"
    p.write_text("actual input")
    body = {
        "execution_id": "fixed-id",
        "skill": "file.ingest",
        "robot_id": "r1",
        "args": {
            "path": str(p),
            "metadata": {"kind": "document", "source": "file", "encoding": "utf8"},
        },
    }
    try:
        with httpx.Client(trust_env=False) as c:
            url = f"http://127.0.0.1:{server.server_port}/executions/fixed-id"
            first = c.put(url, json=body)
            second = c.put(url, json=body)
            assert first.status_code == 200 and second.json() == first.json()
            body["args"]["path"] = str(tmp_path / "different")
            assert c.put(url, json=body).status_code == 409
        assert len(s.list("assets")) == 1
    finally:
        server.shutdown()
        server.server_close()
        t.join()
        s.close()


def test_worker_kill_recovers_same_remote_execution_without_redispatch(tmp_path):
    import subprocess
    import sys
    import time
    from pathlib import Path
    from robot_agent.service import skill_server

    source = tmp_path / "source"
    source.write_bytes(Path(__file__).read_bytes() * 4)
    target = tmp_path / "copy"
    service_store = Store(tmp_path / "service")
    service_rt = Runtime(service_store)
    service_rt.install_local_skills([str(tmp_path)])
    server = skill_server(service_store, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = tmp_path / "client"
    s = Store(root)
    rt = Runtime(s)
    spec = {
        **service_rt.catalog()["file.copy"],
        "adapter": "http",
        "endpoint": f"http://127.0.0.1:{server.server_port}",
        "resources": {"disk": 1},
    }
    rt.register("file.copy", spec)
    s.set_capacity("r1/disk", 1)
    task = rt.submit(
        {
            "steps": [
                {
                    "id": "copy",
                    "skill": "file.copy",
                    "args": {
                        "source": str(source),
                        "target": str(target),
                        "chunk_bytes": 512,
                    },
                }
            ],
            "verification": "copy",
        },
        "r1",
    )["id"]
    command = [
        sys.executable,
        "-m",
        "robot_agent.cli",
        "--root",
        str(root),
        "run",
        "--until",
        task,
    ]
    first = subprocess.Popen(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + 10
        while (
            not target.exists() or target.stat().st_size == 0
        ) and time.monotonic() < deadline:
            assert first.poll() is None, "worker exited before dispatch"
            time.sleep(0.02)
        assert target.exists() and 0 < target.stat().st_size < source.stat().st_size
        first.kill()
        first.wait(timeout=10)
        resumed = subprocess.run(command, capture_output=True, text=True, timeout=40)
        assert resumed.returncode == 0, resumed.stderr + resumed.stdout
        assert target.read_bytes() == source.read_bytes()
        assert s.get("tasks", task)["status"] == "succeeded"
        assert len(s.list("executions")) == 1
        assert len(service_store.list("service_requests")) == 1
        assert not s.leases()
    finally:
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join()
        service_store.close()
        s.close()
