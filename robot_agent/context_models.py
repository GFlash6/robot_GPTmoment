"""Typed, serializable context contracts for model-facing task reasoning."""

from dataclasses import dataclass, field
from typing import Any

from .contracts import require


CONTEXT_KINDS = {
    "policy",
    "goal",
    "capability",
    "task_state",
    "session",
    "memory",
    "world_state",
    "operator",
}
AUTHORITIES = {"framework", "operator", "data"}
PHASES = {"planning", "replanning", "subplanning"}
TASK_RELATIONS = {
    "decomposes_to",
    "depends_on",
    "produces",
    "consumes",
    "verifies",
    "fallback_to",
    "blocked_by",
}


@dataclass(frozen=True)
class GoalContext:
    """An auditable interpretation of a raw goal, including unresolved meaning."""

    original_input: str
    interpreted_intent: str
    entities: tuple[dict, ...] = ()
    relations: tuple[dict, ...] = ()
    constraints: tuple[str, ...] = ()
    completion_criteria: tuple[str, ...] = ()
    ambiguities: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    grounding_requests: tuple[str, ...] = ()
    clarification_requests: tuple[str, ...] = ()

    def __post_init__(self):
        require(
            isinstance(self.original_input, str) and bool(self.original_input.strip()),
            "original goal input required",
        )
        require(
            isinstance(self.interpreted_intent, str)
            and bool(self.interpreted_intent.strip()),
            "interpreted goal intent required",
        )
        require(
            all(isinstance(x, dict) for x in self.entities + self.relations),
            "goal entities and relations must be objects",
        )
        for values in (
            self.constraints,
            self.completion_criteria,
            self.ambiguities,
            self.missing_information,
            self.assumptions,
            self.grounding_requests,
            self.clarification_requests,
        ):
            require(
                all(isinstance(x, str) and bool(x.strip()) for x in values),
                "goal context text entries must be nonempty",
            )

    @classmethod
    def from_input(cls, text: str):
        require(isinstance(text, str) and bool(text.strip()), "goal required")
        # Raw input is preserved. Semantic enrichment can replace interpreted_intent
        # only through a separately validated analyzer result.
        return cls(original_input=text, interpreted_intent=text)

    @classmethod
    def from_analysis(cls, original_input: str, analysis: dict):
        """Accept validated semantic enrichment without allowing raw input replacement."""
        require(isinstance(analysis, dict), "goal analysis must be an object")
        fields = {
            "entities",
            "relations",
            "constraints",
            "completion_criteria",
            "ambiguities",
            "missing_information",
            "assumptions",
            "grounding_requests",
            "clarification_requests",
        }
        require(set(analysis) <= fields | {"interpreted_intent"}, "unknown goal analysis field")
        values = {}
        for name in fields:
            value = analysis.get(name, ())
            require(isinstance(value, (list, tuple)), f"goal analysis {name} must be a list")
            values[name] = tuple(value)
        return cls(
            original_input=original_input,
            interpreted_intent=analysis.get("interpreted_intent", original_input),
            **values,
        )

    @property
    def disposition(self):
        if self.clarification_requests:
            return "needs_clarification"
        if self.grounding_requests or self.missing_information:
            return "needs_grounding"
        return "ready"

    def as_dict(self):
        return {
            "original_input": self.original_input,
            "interpreted_intent": self.interpreted_intent,
            "entities": list(self.entities),
            "relations": list(self.relations),
            "constraints": list(self.constraints),
            "completion_criteria": list(self.completion_criteria),
            "ambiguities": list(self.ambiguities),
            "missing_information": list(self.missing_information),
            "assumptions": list(self.assumptions),
            "grounding_requests": list(self.grounding_requests),
            "clarification_requests": list(self.clarification_requests),
            "disposition": self.disposition,
        }


@dataclass(frozen=True)
class TaskNode:
    id: str
    title: str
    node_type: str
    status: str
    parent_id: str | None = None
    priority: int = 0
    owner: str | None = None
    output: Any = None
    failure: str | None = None
    evidence_ids: tuple[str, ...] = ()

    def as_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "node_type": self.node_type,
            "status": self.status,
            "parent_id": self.parent_id,
            "priority": self.priority,
            "owner": self.owner,
            "output": self.output,
            "failure": self.failure,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class TaskEdge:
    source: str
    target: str
    relation: str

    def __post_init__(self):
        require(bool(self.source) and bool(self.target), "task relation endpoints required")
        require(self.relation in TASK_RELATIONS, "unsupported task relation")

    def as_dict(self):
        return {"source": self.source, "target": self.target, "relation": self.relation}


@dataclass(frozen=True)
class TaskStateContext:
    task_id: str
    status: str
    revision: int
    generation: int
    nodes: tuple[TaskNode, ...]
    edges: tuple[TaskEdge, ...]

    def as_dict(self):
        return {
            "task_id": self.task_id,
            "status": self.status,
            "revision": self.revision,
            "generation": self.generation,
            "nodes": [x.as_dict() for x in self.nodes],
            "edges": [x.as_dict() for x in self.edges],
        }


@dataclass(frozen=True)
class ContextRequest:
    request_id: str
    phase: str
    goal: GoalContext
    robot_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    revision: int = 0
    generation: int = 0

    def __post_init__(self):
        require(
            isinstance(self.request_id, str) and bool(self.request_id),
            "context request id required",
        )
        require(self.phase in PHASES, "unsupported context phase")
        require(isinstance(self.goal, GoalContext), "goal context required")
        require(type(self.revision) is int and self.revision >= 0, "invalid revision")
        require(type(self.generation) is int and self.generation >= 0, "invalid generation")


@dataclass(frozen=True)
class ContextFragment:
    id: str
    content: str | dict | list
    priority: int = 0
    required: bool = False
    kind: str = "operator"
    source: str = "legacy"
    authority: str = "data"
    evidence_ids: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        require(isinstance(self.id, str) and bool(self.id), "context id required")
        require(isinstance(self.content, (str, dict, list)), "invalid context content")
        require(type(self.priority) is int, "context priority must be integer")
        require(type(self.required) is bool, "context required must be boolean")
        require(self.kind in CONTEXT_KINDS, "unsupported context kind")
        require(self.authority in AUTHORITIES, "unsupported context authority")
        require(isinstance(self.source, str) and bool(self.source), "context source required")
        require(isinstance(self.metadata, dict), "context metadata must be an object")


@dataclass(frozen=True)
class ContextBundle:
    request: ContextRequest
    fragments: tuple[ContextFragment, ...]
    diagnostics: tuple[dict, ...] = ()

    def __post_init__(self):
        require(
            len({item.id for item in self.fragments}) == len(self.fragments),
            "context bundle fragment ids must be unique",
        )


@dataclass(frozen=True)
class ContextManifest:
    request_id: str
    phase: str
    included: tuple[str, ...]
    dropped: tuple[dict, ...]
    estimated_input_tokens: int
    input_token_limit: int
    reserved_output_tokens: int
    estimator: str
    renderer_version: str

    def as_dict(self):
        return {
            "request_id": self.request_id,
            "phase": self.phase,
            "included": list(self.included),
            "dropped": list(self.dropped),
            "estimated_input_tokens": self.estimated_input_tokens,
            "input_token_limit": self.input_token_limit,
            "reserved_output_tokens": self.reserved_output_tokens,
            "estimator": self.estimator,
            "renderer_version": self.renderer_version,
        }
