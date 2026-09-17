"""Build goal, capability, and graph-shaped task context from authoritative state."""

from .context_models import (
    ContextBundle,
    ContextFragment,
    ContextRequest,
    TaskEdge,
    TaskNode,
    TaskStateContext,
)
from .contracts import require


CAPABILITY_FIELDS = {
    "input_schema",
    "output_schema",
    "checks",
    "resources",
    "cancelable",
    "replay_safe",
    "verifier",
}


class ContextBuilder:
    def __init__(self, store):
        self.store = store

    def build(self, request: ContextRequest, catalog):
        require(isinstance(catalog, dict), "skill catalog required")
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
                content=self.capabilities(catalog),
                source="frozen_skill_catalog" if request.task_id else "skill_registry",
                authority="framework",
                priority=90,
                required=True,
            ),
        ]
        if request.task_id:
            task = self.store.get("tasks", request.task_id)
            require(task is not None, "unknown context task")
            require(
                task["revision"] == request.revision
                and task["generation"] == request.generation,
                "stale task context request",
            )
            fragments.append(
                ContextFragment(
                    id="task-state",
                    kind="task_state",
                    content=self.task_state(task).as_dict(),
                    source="runtime_ledger",
                    authority="data",
                    priority=95,
                    required=request.phase in {"replanning", "subplanning"},
                )
            )
        return ContextBundle(request=request, fragments=tuple(fragments))

    @staticmethod
    def capabilities(catalog):
        return {
            name: {key: value for key, value in spec.items() if key in CAPABILITY_FIELDS}
            for name, spec in sorted(catalog.items())
        }

    @staticmethod
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
