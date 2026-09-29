"""Trusted context providers over actual ledger records and verified source bytes."""
from dataclasses import dataclass
from typing import Protocol
import time

from .context_models import ContextFragment, ContextRequest, TaskEdge, TaskNode, TaskStateContext
from .contracts import require


@dataclass(frozen=True)
class ProviderInput:
    request: ContextRequest
    catalog: dict
    session: dict | None = None


class ContextProvider(Protocol):
    name: str

    def collect(self, store, inputs: ProviderInput) -> tuple[ContextFragment, ...]:
        """Return source-backed fragments, or raise when required data is invalid."""
        ...


CAPABILITY_FIELDS = {
    "input_schema",
    "output_schema",
    "checks",
    "resources",
    "cancelable",
    "replay_safe",
    "verifier",
}


def capabilities(catalog):
    return {
        name: {key: value for key, value in spec.items() if key in CAPABILITY_FIELDS}
        for name, spec in sorted(catalog.items())
    }

def task_state(task):
    root_id = "task:" + task["id"]
    nodes = [
        TaskNode(
            id=root_id,
            title=task.get("goal") or "operator supplied plan",
            node_type="task",
            status=task["status"],
            priority=task.get("priority", 0),
        )
    ]
    edges = []
    verification = task["plan"]["verification"]
    require(
        root_id not in {step["id"] for step in task["plan"]["steps"]},
        "task root id collides with step id",
    )
    for step in task["plan"]["steps"]:
        state = task["steps"][step["id"]]
        result = state.get("result") or {}
        evidence = tuple(
            item.get("source")
            for item in result.get("evidence", [])
            if isinstance(item, dict) and item.get("source")
        )
        nodes.append(
            TaskNode(
                id=step["id"],
                title=step["skill"],
                node_type="verification" if step["id"] == verification else "step",
                status=state["status"],
                parent_id=root_id,
                output=result.get("output") if state["status"] == "succeeded" else None,
                failure=result.get("error") or state.get("error"),
                evidence_ids=evidence,
            )
        )
        edges.append(TaskEdge(root_id, step["id"], "decomposes_to"))
        edges.extend(
            TaskEdge(dep, step["id"], "depends_on")
            for dep in step.get("deps", [])
        )
        if step["id"] == verification:
            edges.append(TaskEdge(step["id"], root_id, "verifies"))
    return TaskStateContext(
        task_id=task["id"],
        status=task["status"],
        revision=task["revision"],
        generation=task["generation"],
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


class GoalCapabilityProvider:
    name = "goal-capabilities"

    def collect(self, store, inputs):
        request = inputs.request
        fragments = [
            ContextFragment(
                id="goal",
                kind="goal",
                content=request.goal.as_dict(),
                source="goal_context",
                authority="operator",
                priority=100,
                required=True,
            ),
            ContextFragment(
                id="capabilities",
                kind="capability",
                content=capabilities(inputs.catalog),
                source="frozen_skill_catalog" if request.task_id else "skill_registry",
                authority="framework",
                priority=90,
                required=True,
            ),
        ]
        return tuple(fragments)


class TaskStateProvider:
    name = "task-state"

    def collect(self, store, inputs):
        request = inputs.request
        fragments = []
        if request.task_id:
            task = store.get("tasks", request.task_id)
            require(task is not None, "unknown context task")
            require(request.robot_id is None or task["robot_id"] == request.robot_id, "context task robot mismatch")
            require(
                task["revision"] == request.revision
                and task["generation"] == request.generation,
                "stale task context request",
            )
            from .completion import task_contract
            completion = task_contract(task)
            if completion is not None:
                fragments.append(completion_fragment(completion, "accepted_task_completion_contract"))
                final = task["steps"][task["plan"]["verification"]].get("result") or {}
                if final.get("completion_evaluation"):
                    fragments.append(ContextFragment(id="completion-evaluation", kind="task_state", authority="data",
                        source="runtime_completion_evaluation", priority=96, required=True,
                        content=final["completion_evaluation"],
                        evidence_ids=tuple(e["source"] for e in final.get("evidence", []) if e.get("source")),
                        metadata={"task_id": task["id"], "revision": task["revision"], "generation": task["generation"],
                                  "execution_id": final.get("execution_id")}))
            fragments.append(
                ContextFragment(
                    id="task-state",
                    kind="task_state",
                    content=task_state(task).as_dict(),
                    source="runtime_ledger",
                    authority="data",
                    priority=95,
                    required=request.phase in {"replanning", "subplanning"},
                )
            )
        return tuple(fragments)


def completion_fragment(contract, source):
    return ContextFragment(id="completion-contract", kind="goal", authority="operator", required=True, priority=100,
        source=source, content={"contract": contract,
            "enforcement": "Operator-owned final verifier requirements. The plan must use this verifier; checks are applied independently to its actual output. Do not put completion_contract in the plan or weaken these checks."})


class SessionProvider:
    name = "session"

    def collect(self, store, inputs):
        request, session = inputs.request, inputs.session
        fragments = []
        if session is not None:
            from .completion import validate_contract
            completion = validate_contract(session.get("completion_contract"), inputs.catalog) if not request.task_id else None
            if completion is not None:
                fragments.append(completion_fragment(completion, "operator_session_completion_contract"))
            from .session_history import history_view
            visible_turns, summary = history_view(store, session)
            if summary:
                fragments.append(ContextFragment(id="session-summary", kind="memory", authority="data",
                    source="session_summary", priority=86, required=True,
                    content={"points": summary["points"], "content_authority": summary["content_authority"]},
                    metadata={"summary_id": summary["id"], "model_response_id": summary["model_response_id"],
                        "model_response_ids": summary.get("model_response_ids", [summary["model_response_id"]]),
                        "covered_turns": summary["covered_turns"], "pinned_turn_ids": summary["pinned_turn_ids"],
                        "record_hash": session["history_summary"]["record_hash"]}))
            fragments.append(ContextFragment(
                id="session", kind="session", content=[{"role": t["role"], "content": t["content"]} for t in visible_turns],
                source="session_ledger", authority="data", priority=85, required=True,
                metadata={"session_id": session["id"], "revision": session["revision"], "snapshot_id": request.context_snapshot_id},
            ))
        return tuple(fragments)


class MemoryProvider:
    name = "memory"

    def collect(self, store, inputs):
        request, session = inputs.request, inputs.session
        fragments = []
        if session is not None:
            if session.get("memory_bindings"):
                from .context_memory import record_hash, resolve_memory
                for binding in session["memory_bindings"]:
                    item, evidence = resolve_memory(store, binding["memory_id"], request.robot_id)
                    require(record_hash(item) == binding["record_hash"], "bound memory changed; retrieve and bind again")
                    fragments.append(ContextFragment(
                        id="memory:" + item["id"], kind="memory", source="scoped_memory_catalog",
                        authority="data", priority=80, required=True,
                        content={"memory_id": item["id"], "text": item["text"], "attributes": item["attributes"],
                                 "content_authority": "stored_annotation", "verified_assets": evidence},
                        evidence_ids=tuple(item["evidence"]), metadata={"record_hash": binding["record_hash"],
                            "valid_until": item["valid_until"], "verified_at": time.time()},
                    ))
        return tuple(fragments)


class AssetProvider:
    name = "assets"

    def collect(self, store, inputs):
        request, session = inputs.request, inputs.session
        fragments = []
        if session is not None:
            from .context_assets import verify_session_assets
            verified = verify_session_assets(store, session)
            if verified:
                assets = [{k: asset[k] for k in ("id", "sha256", "size", "metadata", "created_at")} for asset in verified]
                fragments.append(ContextFragment(id="asset-evidence", kind="memory", content=assets,
                    source="verified_asset_catalog", authority="data", priority=85, required=True,
                    evidence_ids=tuple(session["asset_ids"]), metadata={"verified_at": time.time(),
                        "scope": "stored_asset_bytes_and_bound_record", "asset_bindings": session["asset_bindings"]}))
        return tuple(fragments)


class SelectionProvider:
    name = "selection"

    def collect(self, store, inputs):
        request, session = inputs.request, inputs.session
        fragments = []
        if session is not None:
            # Automatic recovery uses current task-state, not an expired UI selection.
            selection = None if request.context_snapshot_id and request.phase == "replanning" else session.get("selection")
            if selection:
                require(selection["expires_at"] > time.time(), "UI selection expired; select the task again")
                task = store.get("tasks", selection["task_id"])
                require(task is not None and task["robot_id"] == request.robot_id, "selected task unavailable")
                require((task["revision"], task["generation"]) == (selection["revision"], selection["generation"]), "UI selection refers to an old task version")
                require(all(step in task["steps"] for step in selection["step_ids"]), "selected step unavailable")
                fragments.append(ContextFragment(
                    id="ui-selection", kind="operator", source="ui_selection_resolved_from_ledger", authority="data",
                    content={"task_id": task["id"], "selected_steps": {step: task["steps"][step] for step in selection["step_ids"]}},
                    priority=90, required=True,
                    metadata={"selection_id": selection["id"], "revision": task["revision"], "generation": task["generation"], "expires_at": selection["expires_at"]},
                ))
        return tuple(fragments)


DEFAULT_PROVIDERS = (GoalCapabilityProvider(), TaskStateProvider(), SessionProvider(), MemoryProvider(), AssetProvider(), SelectionProvider())
