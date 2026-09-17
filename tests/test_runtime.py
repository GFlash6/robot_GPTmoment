"""Real local file operations exercise orchestration; no robot/LLM doubles."""

import hashlib
import pytest
from robot_agent.store import Store
from robot_agent.contracts import ContractError


def setup(tmp_path):
    from robot_agent.runtime import Runtime

    s = Store(tmp_path / "state")
    runtime = Runtime(s)
    runtime.install_local_skills([str(tmp_path)])
    path = tmp_path / "source.txt"
    path.write_text("actual local document")
    return s, runtime, path


def plan(path):
    return {
        "steps": [
            {
                "id": "ingest",
                "skill": "file.ingest",
                "args": {
                    "path": str(path),
                    "metadata": {
                        "kind": "document",
                        "encoding": "utf8",
                        "source": "local-file",
                    },
                },
            },
            {
                "id": "verify",
                "skill": "asset.verify",
                "args": {"asset_id": {"$ref": "ingest.asset_id"}},
                "deps": ["ingest"],
            },
        ],
        "verification": "verify",
    }


def finish(rt, task):
    for _ in range(20):
        result = rt.tick(task)
        if result["status"] in {"succeeded", "failed", "paused", "canceled"}:
            return result
    raise AssertionError("did not finish local operations")


def test_real_dag_evidence_and_restart(tmp_path):
    s, rt, p = setup(tmp_path)
    task = rt.submit(plan(p), "r1")["id"]
    result = finish(rt, task)
    assert result["status"] == "succeeded"
    assert (
        result["steps"]["verify"]["result"]["output"]["sha256"]
        == hashlib.sha256(p.read_bytes()).hexdigest()
    )
    assert not s.leases()
    s.close()
    from robot_agent.runtime import Runtime

    s = Store(tmp_path / "state")
    rt = Runtime(s)
    assert rt.tick(task)["status"] == "succeeded"
    assert len(s.list("assets")) == 1
    s.close()


def test_fallback_uses_actual_failure_and_preserves_original_contract(tmp_path):
    s, rt, p = setup(tmp_path)
    body = plan(tmp_path / "missing")
    body["steps"][0]["fallback"] = [
        {"skill": "file.ingest", "args": plan(p)["steps"][0]["args"]}
    ]
    task = rt.submit(body, "r1")["id"]
    result = finish(rt, task)
    assert result["status"] == "succeeded"
    assert any("FileNotFoundError" in e["data"] for e in s.events(task))
    assert len(s.list("executions")) == 3
    s.close()


def test_pause_before_dispatch_and_resume(tmp_path):
    s, rt, p = setup(tmp_path)
    task = rt.submit(plan(p), "r1")["id"]
    rt.interrupt(task, "pause")
    assert rt.tick(task)["status"] == "paused"
    assert not s.list("assets")
    rt.resume(task)
    assert finish(rt, task)["status"] == "succeeded"
    s.close()


def test_unreachable_service_does_not_release_or_retry(tmp_path):
    s, rt, p = setup(tmp_path)
    rt.register(
        "remote",
        {
            "adapter": "http",
            "endpoint": "http://127.0.0.1:1",
            "timeout": 0.1,
            "resources": {"base": 1},
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "checks": [],
            "cancelable": True,
            "replay_safe": True,
        },
    )
    s.set_capacity("r1/base", 1)
    task = rt.submit(
        {
            "steps": [{"id": "go", "skill": "remote", "args": {}, "retries": 2}],
            "verification": "go",
        },
        "r1",
    )["id"]
    rt.tick(task)
    rt.tick(task)
    assert s.get("tasks", task)["status"] == "unknown"
    assert len(s.list("executions")) == 1
    assert len(s.leases()) == 1
    rt.interrupt(task, "cancel")
    rt.tick(task)
    assert len(s.leases()) == 1
    with pytest.raises(ContractError):
        rt.resume(task)
    s.close()


def test_resource_claims_across_connections_do_not_overallocate(tmp_path):
    import concurrent.futures

    a = Store(tmp_path)
    a.set_capacity("r1/base", 1)
    b = Store(tmp_path)
    with concurrent.futures.ThreadPoolExecutor() as pool:
        futures = [
            pool.submit(s.acquire, key, {"r1/base": 1})
            for s, key in [(a, "a"), (b, "b")]
        ]
        assert sum(f.result() for f in futures) == 1
    a.close()
    b.close()


def test_cancel_wins_over_late_automatic_plan_revision(tmp_path):
    s, rt, p = setup(tmp_path)
    task = rt.submit(
        plan(tmp_path / "missing"),
        "r1",
        goal="read",
        agent_context={"max_replans": 1, "replans": 0},
    )["id"]
    assert rt.tick(task)["status"] == "replanning"
    rt.interrupt(task, "cancel")
    result = rt.revise(task, plan(p), automatic=True)
    assert result["status"] == "canceled"
    assert result["revision"] == 0
    assert not s.list("assets")
    assert s.get("controls", task)["mode"] == "cancel"
    s.close()


def test_resource_alias_collision_cannot_underclaim_capacity(tmp_path):
    s, rt, p = setup(tmp_path)
    spec = rt.catalog()["file.ingest"]
    spec["resources"] = {"disk": 2, "r1/disk": 1}
    rt.register("file.ingest", spec)
    s.set_capacity("r1/disk", 2)
    with pytest.raises(ContractError):
        rt.submit(plan(p), "r1")
    assert not s.leases()
    s.close()


def test_late_automatic_revision_cannot_replace_newer_operator_generation(tmp_path):
    s, rt, p = setup(tmp_path)
    task = rt.submit(plan(tmp_path / "missing"), "r1")["id"]
    assert rt.tick(task)["status"] == "failed"
    newer = rt.revise(task, plan(p))
    result = rt.revise(
        task, plan(tmp_path / "missing"), automatic=True, expected_generation=0
    )
    assert result["generation"] == newer["generation"]
    assert result["plan"] == plan(p)
    assert finish(rt, task)["status"] == "succeeded"
    s.close()


def test_plan_history_keeps_the_catalog_used_by_that_revision(tmp_path):
    s, rt, p = setup(tmp_path)
    task_id = rt.submit(plan(tmp_path / "missing"), "r1")["id"]
    assert rt.tick(task_id)["status"] == "failed"

    updated = rt.catalog()["file.ingest"]
    updated["contract_version"] = "later-contract"
    rt.register("file.ingest", updated)

    revised = rt.revise(task_id, plan(p))
    history = s.get("plan_history", f"{task_id}:0")
    assert history["revision"] == 0
    assert history["generation"] == 0
    assert isinstance(history["saved_at"], float)
    assert "contract_version" not in history["catalog"]["file.ingest"]
    assert revised["catalog"]["file.ingest"]["contract_version"] == "later-contract"
    s.close()
