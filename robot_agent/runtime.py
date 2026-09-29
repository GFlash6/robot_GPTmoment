"""Robot task coordination. All dispatches are journaled before external IO."""

import copy
import time
import uuid
from .contracts import (
    ContractError,
    require,
    schema_check,
    validate_plan,
    check_result,
    check_terminal,
    field,
)
from .skills import Skills, LOCAL_SPECS, validate_spec

TERMINAL = {"succeeded", "failed", "canceled"}
QUIET = TERMINAL | {"paused"}


class Runtime:
    def __init__(self, store):
        self.store = store
        self.skills = Skills(store)

    def install_local_skills(self, allowed_roots):
        for name, body in LOCAL_SPECS.items():
            spec = copy.deepcopy(body)
            spec.update(
                resources={},
                cancelable=True,
                replay_safe=name != "file.copy",
                allowed_roots=allowed_roots,
                verifier=name in {"asset.verify", "asset.verify-set", "file.copy"},
            )
            self.register(name, spec)

    def register(self, name, spec):
        validate_spec(name, spec)
        self.store.put("skills", name, {"name": name, **spec})

    def catalog(self):
        return {x["name"]: x for x in self.store.list("skills")}

    def analyze_goal(self, goal, model_config, conversation=()):
        from .goal_analysis import GoalAnalyzer

        return GoalAnalyzer(self.store, model_config).analyze(goal, conversation)

    def submit(self, plan, robot_id, priority=0, goal=None, *, agent_context=None, task_id=None, completion_contract=None):
        require(
            isinstance(robot_id, str) and robot_id and "/" not in robot_id,
            "robot_id must be one namespace segment",
        )
        require(type(priority) is int, "priority must be integer")
        catalog = self.catalog()
        self._check_plan(plan, catalog, robot_id, completion_contract)
        task = {
            "id": task_id or str(uuid.uuid4()),
            "robot_id": robot_id,
            "goal": goal,
            "priority": priority,
            "created_at": time.time(),
            "status": "queued",
            "plan": copy.deepcopy(plan),
            "catalog": catalog,
            "revision": 0,
            "generation": 0,
            "steps": {
                s["id"]: {"status": "pending", "attempts": 0, "alternative": 0}
                for s in plan["steps"]
            },
        }
        if completion_contract is not None:
            from .completion import validate_contract
            from .context_memory import record_hash
            task["completion_contract"] = validate_contract(completion_contract, catalog)
            task["completion_contract_hash"] = record_hash(task["completion_contract"])
        if agent_context is not None:
            require(
                set(agent_context)
                <= {"model_config", "max_replans", "replans", "model_response_id"},
                "invalid agent context fields",
            )
            task.update(copy.deepcopy(agent_context))
        with self.store.transaction():
            require(self.store.get("tasks", task["id"]) is None, "task already exists")
            self.store.put("tasks", task["id"], task)
            self.store.event(
                task["id"],
                "submitted",
                {"plan": plan, "robot_id": robot_id, "priority": priority},
            )
        return task

    def _check_plan(self, plan, catalog, robot_id, completion_contract=None):
        validate_plan(plan, catalog)
        from .completion import check_plan_contract
        check_plan_contract(plan, catalog, completion_contract)
        for step in plan["steps"]:
            for item in [step, *step.get("fallback", [])]:
                spec = catalog[item["skill"]]
                if spec.get('fencing_domain'):
                    domain = spec['fencing_domain']
                    require(spec['adapter'] == 'http', 'fenced runtime skills require enforcing HTTP endpoint')
                    require(spec.get('resources', {}).get(domain) == 1, 'fencing domain requires exclusive resource')
                    capacity = self.store.db.execute('SELECT capacity FROM resources WHERE name=?',
                        (self.resource_name(robot_id, domain),)).fetchone()
                    require(capacity is not None and capacity[0] == 1, 'fencing resource capacity must be one')
                if step.get("retries", 0):
                    require(
                        spec.get("replay_safe", False),
                        "retry requires replay_safe skill",
                    )
                names = [
                    self.resource_name(robot_id, k) for k in spec.get("resources", {})
                ]
                require(
                    len(set(names)) == len(names), "duplicate normalized resource names"
                )
                # Capacities must be configured before any task is accepted.
                for key, units in spec.get("resources", {}).items():
                    resource = self.resource_name(robot_id, key)
                    row = self.store.db.execute(
                        "SELECT capacity FROM resources WHERE name=?", (resource,)
                    ).fetchone()
                    require(
                        row is not None and row[0] >= units,
                        f"insufficient configured capacity: {resource}",
                    )

    def submit_goal(self, goal, robot_id, model_config, priority=0, max_replans=0):
        from .context_models import ContextRequest, GoalContext
        from .planner import Planner

        require(
            type(max_replans) is int and 0 <= max_replans <= 10,
            "replan budget must be 0..10",
        )
        planner = Planner(self.store, model_config)
        request = ContextRequest(
            request_id=str(uuid.uuid4()),
            phase="planning",
            goal=GoalContext.from_input(goal),
            robot_id=robot_id,
        )
        plan = planner.plan(goal, self.catalog(), context_request=request)
        context = {
            "model_config": {
                k: v
                for k, v in model_config.items()
                if k
                in {
                    "endpoint",
                    "model",
                    "token_env",
                    "timeout",
                    "max_input_tokens",
                    "max_output_tokens",
                }
            },
            "max_replans": max_replans,
            "replans": 0,
            "model_response_id": planner.last_response_id,
        }
        return self.submit(plan, robot_id, priority, goal, agent_context=context)

    def recover_plan(self, task_id):
        from .context_models import ContextRequest, GoalContext
        from .planner import Planner

        with self.store.transaction():
            task = self.store.get("tasks", task_id)
            if (
                task is None
                or task["status"] not in {"failed", "replanning"}
                or not task.get("goal")
                or task.get("replans", 0) >= task.get("max_replans", 0)
            ):
                return task
            task["replans"] = task.get("replans", 0) + 1
            task["status"] = "replanning"
            self._save(task)
        generation = task["generation"]
        try:
            snapshot_id = task.get("context_snapshot_id")
            from .context_snapshot import read_snapshot, snapshot_goal
            snapshot = read_snapshot(self.store, snapshot_id, robot_id=task["robot_id"],
                                     expected_hash=task.get("context_snapshot_hash")) if snapshot_id else None
            goal = GoalContext.from_input(task["goal"])
            if snapshot:
                goal = snapshot_goal(snapshot)
            planner = Planner(self.store, task["model_config"])
            request = ContextRequest(
                request_id=str(uuid.uuid4()),
                phase="replanning",
                goal=goal,
                robot_id=task["robot_id"],
                session_id=snapshot["session"]["id"] if snapshot else None,
                context_snapshot_id=snapshot_id,
                task_id=task_id,
                revision=task["revision"],
                generation=task["generation"],
            )
            recovery_guard = None
            if snapshot:
                from .recovery_budget import fit_recovery
                request, recovery_guard = fit_recovery(self.store, task, request)
            plan = planner.plan(
                goal.interpreted_intent, task["catalog"], context_request=request
            )
            if recovery_guard:
                recovery_guard()
            if snapshot:
                from .context_memory import verify_bindings
                verify_bindings(self.store, snapshot["session"].get("memory_bindings", []), task["robot_id"])
                from .context_assets import verify_session_assets
                verify_session_assets(self.store, snapshot["session"])
            return self.revise(
                task_id,
                plan,
                model_response_id=planner.last_response_id,
                automatic=True,
                expected_generation=generation,
            )
        except Exception as exc:
            with self.store.transaction():
                self.store.event(
                    task_id,
                    "replan_rejected",
                    {
                        "error": type(exc).__name__ + ": " + str(exc),
                        "attempt": task["replans"],
                    },
                )
                rejected = self.store.get("tasks", task_id)
                if rejected["generation"] != generation:
                    return rejected
                control = self.store.get("controls", task_id)
                # An accepted stop request still needs the worker to apply it.
                # Do not turn its target terminal while rejecting a late model result.
                if not control and any(c["task_id"] == task_id and c["status"] == "accepted"
                                       and c["action"] in {"task.cancel", "task.pause"}
                                       for c in self.store.list("commands")):
                    return rejected
                rejected["status"] = (
                    ("canceled" if control["mode"] == "cancel" else "paused")
                    if control and not control.get("failure")
                    else "failed"
                )
                self._save(rejected)
                return rejected

    @staticmethod
    def resource_name(robot_id, key):
        require(
            "/" not in key
            or key.startswith(robot_id + "/")
            or key.startswith("shared/"),
            "resource outside robot scope",
        )
        return key if "/" in key else robot_id + "/" + key

    def interrupt(self, task_id, mode):
        require(mode in {"pause", "cancel"}, "interrupt must be pause or cancel")
        with self.store.transaction():
            task = self.store.get("tasks", task_id)
            require(task is not None, "unknown task")
            require(task["status"] not in TERMINAL, "task already terminal")
            old = self.store.get("controls", task_id)
            if old and old["mode"] == "cancel":
                mode = "cancel"
            self.store.put(
                "controls", task_id, {"mode": mode, "requested_at": time.time()}
            )
            # Wake a paused task to process cancellation through a new durable run.
            if task["status"] == "paused" and mode == "cancel":
                task["generation"] += 1
                task["status"] = "canceling"
                self.store.put("tasks", task_id, task)
            self.store.event(task_id, "interrupt_requested", {"mode": mode})

    def resume(self, task_id):
        with self.store.transaction():
            task = self.store.get("tasks", task_id)
            require(
                task is not None and task["status"] == "paused",
                "only a safely paused task can resume",
            )
            for step in task["plan"]["steps"]:
                state = task["steps"][step["id"]]
                require(
                    state["status"] not in {"running", "unknown"},
                    "unresolved execution",
                )
                if state["status"] == "canceled":
                    spec = task["catalog"][self._choice(step, state)["skill"]]
                    require(
                        spec.get("replay_safe", False),
                        "canceled skill is not safe to re-enter",
                    )
                    state.update(status="pending", attempts=0)
                    state.pop("execution_id", None)
            self.store.db.execute(
                "DELETE FROM objects WHERE collection=? AND id=?", ("controls", task_id)
            )
            task["status"] = "queued"
            task["generation"] += 1
            self.store.put("tasks", task_id, task)
            self.store.event(task_id, "resumed", {})
        return task

    def revise(
        self,
        task_id,
        plan,
        *,
        model_response_id=None,
        automatic=False,
        expected_generation=None,
    ):
        with self.store.transaction():
            task = self.store.get("tasks", task_id)
            require(task is not None, "unknown task")
            if (
                automatic
                and expected_generation is not None
                and task["generation"] != expected_generation
            ):
                self.store.event(
                    task_id,
                    "stale_plan_discarded",
                    {"expected_generation": expected_generation},
                )
                return task

            require(
                task is not None
                and task["status"] in {"paused", "failed", "replanning"},
                "replan requires safely stopped task",
            )
            require(
                not any(
                    s.get("status") in {"running", "unknown"}
                    for s in task["steps"].values()
                ),
                "replan has unresolved execution",
            )
            control = self.store.get("controls", task_id)
            if automatic and any(c["task_id"] == task_id and c["action"] == "task.cancel" and c["status"] == "accepted"
                                 for c in self.store.list("commands")):
                self.store.event(task_id, "late_plan_discarded", {"reason": "accepted cancellation command", "model_response_id": model_response_id})
                return task
            if automatic and control and not control.get("failure"):
                task["status"] = "canceled" if control["mode"] == "cancel" else "paused"
                self.store.put("tasks", task_id, task)
                self.store.event(
                    task_id,
                    "late_plan_discarded",
                    {
                        "model_response_id": model_response_id,
                        "interrupt": control["mode"],
                    },
                )
                return task
            require(task["revision"] < 10, "plan revision budget exhausted")
            from .completion import task_contract
            self._check_plan(plan, self.catalog(), task["robot_id"], task_contract(task))
            # A revision is a new plan, never an implicit replay of completed side effects.
            for step in plan["steps"]:
                for item in [step, *step.get("fallback", [])]:
                    require(
                        self.catalog()[item["skill"]].get("replay_safe", False),
                        "new plan requires replay-safe skills; submit a separately reviewed task for irreversible actions",
                    )
            self.store.put(
                "plan_history",
                f"{task_id}:{task['revision']}",
                {
                    "revision": task["revision"],
                    "generation": task["generation"],
                    "saved_at": time.time(),
                    "plan": copy.deepcopy(task["plan"]),
                    "steps": copy.deepcopy(task["steps"]),
                    "catalog": copy.deepcopy(task["catalog"]),
                },
            )
            task.update(
                plan=copy.deepcopy(plan),
                catalog=self.catalog(),
                steps={
                    s["id"]: {"status": "pending", "attempts": 0, "alternative": 0}
                    for s in plan["steps"]
                },
                status="queued",
                revision=task["revision"] + 1,
                generation=task["generation"] + 1,
            )
            self.store.db.execute(
                "DELETE FROM objects WHERE collection=? AND id=?", ("controls", task_id)
            )
            if model_response_id is not None:
                task["model_response_id"] = model_response_id
            self.store.put("tasks", task_id, task)
            self.store.event(
                task_id, "plan_revised", {"revision": task["revision"], "plan": plan}
            )
        return task

    def preempt(self, task_id):
        target = self.store.get("tasks", task_id)
        require(target is not None, "unknown task")
        affected = []
        for task in self.store.list("tasks"):
            if (
                task["id"] != task_id
                and task["robot_id"] == target["robot_id"]
                and task["priority"] < target["priority"]
                and task["status"] not in QUIET
            ):
                self.interrupt(task["id"], "pause")
                affected.append(task["id"])
        return affected

    @staticmethod
    def _choice(step, state):
        return [step, *step.get("fallback", [])][state["alternative"]]

    def _args(self, value, task):
        if isinstance(value, dict):
            if "$ref" in value:
                origin, _, path = value["$ref"].partition(".")
                state = task["steps"][origin]
                require(
                    state["status"] == "succeeded", "dependency output not verified"
                )
                return field(state["result"]["output"], path)
            return {k: self._args(v, task) for k, v in value.items()}
        if isinstance(value, list):
            return [self._args(v, task) for v in value]
        return value

    def _higher_waiting(self, task, needs):
        for other in self.store.list("tasks"):
            if (
                other["id"] == task["id"]
                or other["status"] not in {"queued", "running"}
                or other["priority"] <= task["priority"]
            ):
                continue
            for step in other["plan"]["steps"]:
                state = other["steps"][step["id"]]
                if state["status"] != "pending" or not all(
                    other["steps"][d]["status"] == "succeeded"
                    for d in step.get("deps", [])
                ):
                    continue
                spec = other["catalog"][self._choice(step, state)["skill"]]
                wanted = {
                    self.resource_name(other["robot_id"], k)
                    for k in spec.get("resources", {})
                }
                if wanted.intersection(needs):
                    return True
        return False

    def _save(self, task):
        self.store.put("tasks", task["id"], task)

    def tick(self, task_id):
        # One worker owns this process; controls are a separate durable collection so
        # CLI interrupts are not overwritten by an in-flight response.
        with self.store.lock:
            task = self.store.get("tasks", task_id)
            require(task is not None, "unknown task")
            if task["status"] in QUIET:
                return task
            for step in task["plan"]["steps"]:
                state = task["steps"][step["id"]]
                control = self.store.get("controls", task_id)
                if state["status"] in TERMINAL:
                    continue
                choice = self._choice(step, state)
                spec = task["catalog"][choice["skill"]]
                if not state.get("execution_id"):
                    if control or any(
                        s["status"] in {"failed", "canceled"}
                        for s in task["steps"].values()
                    ):
                        continue
                    if not all(
                        task["steps"][d]["status"] == "succeeded"
                        for d in step.get("deps", [])
                    ):
                        continue
                    try:
                        args = self._args(choice.get("args", {}), task)
                        schema_check(spec["input_schema"], args)
                    except ContractError as exc:
                        state.update(status="failed", error=str(exc))
                        self.store.event(
                            task_id,
                            "input_rejected",
                            {"step": step["id"], "error": str(exc)},
                        )
                        continue
                    needs = {
                        self.resource_name(task["robot_id"], k): v
                        for k, v in spec.get("resources", {}).items()
                    }
                    if self._higher_waiting(task, needs):
                        continue
                    execution_id = str(uuid.uuid4())
                    with self.store.transaction():
                        try:
                            from .completion import task_contract, same_contract
                            completion = task_contract(task)
                            if task.get("context_snapshot_id"):
                                from .context_snapshot import read_snapshot
                                from .context_assets import verify_session_assets
                                snapshot = read_snapshot(self.store, task["context_snapshot_id"],
                                    robot_id=task["robot_id"], session_id=task.get("session_id"),
                                    expected_hash=task.get("context_snapshot_hash"))
                                verify_session_assets(self.store, snapshot["session"])
                                require(same_contract(snapshot["session"].get("completion_contract"), completion),
                                        "snapshot completion contract differs from task")
                        except ContractError as exc:
                            state.update(status="failed", error=str(exc))
                            self._save(task)
                            self.store.event(task_id, "context_rejected", {"step": step["id"], "error": str(exc)})
                            continue
                        if not self.store._acquire(execution_id, needs):
                            continue
                        state.update(
                            execution_id=execution_id,
                            status="running",
                            attempts=state["attempts"] + 1,
                        )
                        execution = {
                            "id": execution_id,
                            "task_id": task_id,
                            "step": step["id"],
                            "skill": choice["skill"],
                            "args": args,
                            "created_at": time.time(),
                            "status": "dispatched",
                        }
                        if spec.get('fencing_domain'):
                            from .fencing import issue
                            execution['authority'] = issue(self.store, task['robot_id'], spec['fencing_domain'])
                        self.store.put("executions", execution_id, execution)
                        self._save(task)
                        self.store.event(task_id, "dispatch_intent", execution)
                    operation = "start"
                else:
                    execution_id = state["execution_id"]
                    execution = self.store.get("executions", execution_id)
                    operation = "query"
                expired = time.time() - execution["created_at"] > spec.get(
                    "execution_timeout", 300
                )
                if (control or expired) and spec.get("cancelable", False):
                    operation = "cancel"
                try:
                    result = self.skills.call(
                        operation,
                        choice["skill"],
                        spec,
                        execution_id,
                        execution["args"],
                        task["robot_id"],
                        **({'authority': execution.get('authority')} if spec.get('fencing_domain') else {}),
                    )
                    require(
                        isinstance(result, dict)
                        and result.get("execution_id") == execution_id,
                        "execution response identity mismatch",
                    )
                    require(
                        result.get("status")
                        in TERMINAL | {"running", "accepted", "canceling", "unknown"},
                        "invalid skill state",
                    )
                    if result["status"] not in TERMINAL:
                        state["status"] = (
                            "unknown" if result["status"] == "unknown" else "running"
                        )
                        execution.update(status=state["status"], result=result)
                    else:
                        check_terminal(result, execution_id)
                        if result["status"] == "succeeded":
                            try:
                                check_result(spec, result, execution_id)
                                check_result(
                                    task["catalog"][step["skill"]], result, execution_id
                                )
                                if step["id"] == task["plan"]["verification"]:
                                    from .completion import task_contract, evaluate
                                    completion = task_contract(task)
                                    if completion is not None:
                                        evaluation = evaluate(completion, result["output"], execution_id)
                                        result = {**result, "reported_status": result["status"], "completion_evaluation": evaluation}
                                        require(evaluation["status"] == "passed", "task completion criteria failed")
                            except ContractError as exc:
                                result = {
                                    **result,
                                    "status": "failed",
                                    "error": str(exc),
                                }
                        if expired and result["status"] == "canceled" and not control:
                            result = {
                                **result,
                                "status": "failed",
                                "error": "execution deadline exceeded",
                            }
                        state.update(status=result["status"], result=result)
                        execution.update(status=result["status"], result=result)
                        with self.store.transaction():
                            self.store.release(execution_id)
                            self.store.put("executions", execution_id, execution)
                            self.store.event(task_id, "execution_result", result)
                            if state["status"] == "failed" and not self.store.get(
                                "controls", task_id
                            ):
                                if spec.get("replay_safe", False) and state[
                                    "attempts"
                                ] <= step.get("retries", 0):
                                    state.update(status="pending")
                                    state.pop("execution_id")
                                elif state["alternative"] < len(
                                    step.get("fallback", [])
                                ):
                                    state.update(
                                        status="pending",
                                        alternative=state["alternative"] + 1,
                                        attempts=0,
                                    )
                                    state.pop("execution_id")
                            self._save(task)
                except Exception as exc:
                    state.update(
                        status="unknown", error=type(exc).__name__ + ": " + str(exc)
                    )
                    execution.update(status="unknown", error=state["error"])
                    self.store.event(
                        task_id,
                        "execution_unknown",
                        {"execution_id": execution_id, "error": state["error"]},
                    )
                self.store.put("executions", execution_id, execution)
            control = self.store.get("controls", task_id)
            active = any(
                s["status"] in {"running", "unknown"} for s in task["steps"].values()
            )
            if control:
                if active:
                    task["status"] = (
                        "canceling" if control["mode"] == "cancel" else "pausing"
                    )
                else:
                    task["status"] = (
                        "canceled" if control["mode"] == "cancel" else "paused"
                    )
            elif any(s["status"] == "unknown" for s in task["steps"].values()):
                task["status"] = "unknown"
            elif any(
                s["status"] in {"failed", "canceled"} for s in task["steps"].values()
            ):
                # Stop still-active siblings before marking the whole task failed.
                if active:
                    self.store.put(
                        "controls",
                        task_id,
                        {
                            "mode": "cancel",
                            "requested_at": time.time(),
                            "failure": True,
                        },
                    )
                    task["status"] = "canceling"
                else:
                    task["status"] = "failed"
            elif all(s["status"] == "succeeded" for s in task["steps"].values()):
                task["status"] = "succeeded"
            else:
                task["status"] = "running"
            if control and control.get("failure") and not active:
                task["status"] = "failed"
            if (
                task["status"] == "failed"
                and task.get("goal")
                and task.get("replans", 0) < task.get("max_replans", 0)
            ):
                task["status"] = "replanning"
            self._save(task)
            return task
