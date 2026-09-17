"""Plans and results are untrusted data, including model-produced JSON."""

import math
from graphlib import TopologicalSorter, CycleError
import jsonschema
import py_trees


class ContractError(ValueError):
    """A response or configuration did not satisfy its declared contract."""


def require(condition, message):
    if not condition:
        raise ContractError(message)


def schema_check(schema, value):
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(value, schema)
    except (jsonschema.ValidationError, jsonschema.SchemaError) as exc:
        raise ContractError(exc.message) from exc


def field(value, path):
    for part in path.split("."):
        require(isinstance(value, dict) and part in value, f"missing field: {path}")
        value = value[part]
    return value


class _Condition(py_trees.behaviour.Behaviour):
    def __init__(self, name, predicate):
        super().__init__(name)
        self.predicate = predicate

    def update(self):
        return (
            py_trees.common.Status.SUCCESS
            if self.predicate()
            else py_trees.common.Status.FAILURE
        )


def check_terminal(result, execution_id):
    require(
        isinstance(result, dict) and result.get("execution_id") == execution_id,
        "terminal identity mismatch",
    )
    require(
        result.get("status") in {"succeeded", "failed", "canceled"},
        "not a terminal result",
    )
    require(result.get("quiescent") is True, "terminal result lacks stop confirmation")
    evidence = result.get("evidence")
    require(
        isinstance(evidence, list)
        and bool(evidence)
        and all(
            isinstance(e, dict)
            and isinstance(e.get("source"), str)
            and bool(e["source"].strip())
            for e in evidence
        ),
        "terminal result lacks valid source evidence",
    )
    return result


def check_result(spec, result, execution_id):
    require(isinstance(result, dict), "result must be an object")
    conditions = [
        _Condition(
            "execution identity", lambda: result.get("execution_id") == execution_id
        ),
        _Condition("actual success", lambda: result.get("status") == "succeeded"),
        _Condition("stopped", lambda: result.get("quiescent") is True),
        _Condition(
            "output present",
            lambda: isinstance(result.get("output"), dict) and bool(result["output"]),
        ),
        _Condition(
            "source evidence",
            lambda: (
                isinstance(result.get("evidence"), list)
                and bool(result["evidence"])
                and all(
                    isinstance(e, dict)
                    and isinstance(e.get("source"), str)
                    and bool(e["source"].strip())
                    for e in result["evidence"]
                )
            ),
        ),
    ]
    tree = py_trees.composites.Sequence(
        "result contract", memory=False, children=conditions
    )
    tree.tick_once()
    require(
        tree.status == py_trees.common.Status.SUCCESS,
        f"result rejected: {tree.tip().name}",
    )
    schema_check(spec.get("output_schema", {"type": "object"}), result["output"])
    for check in spec.get("checks", []):
        value = field(result["output"], check["path"])
        op = check["op"]
        if op == "eq":
            valid = type(value) is type(check["value"]) and value == check["value"]
        elif op == "nonempty":
            valid = bool(value)
        elif op == "gte":
            valid = (
                type(value) in (int, float)
                and math.isfinite(value)
                and value >= check["value"]
            )
        elif op == "lte":
            valid = (
                type(value) in (int, float)
                and math.isfinite(value)
                and value <= check["value"]
            )
        else:
            raise ContractError(f"unsupported check: {op}")
        require(valid, f"postcondition failed: {check['path']} {op}")
    return result


def validate_plan(plan, catalog):
    require(isinstance(plan, dict), "plan must be an object")
    steps = plan.get("steps")
    require(
        isinstance(steps, list) and 0 < len(steps) <= 256, "plan needs 1..256 steps"
    )
    ids = [s.get("id") for s in steps if isinstance(s, dict)]
    require(
        len(ids) == len(steps)
        and all(isinstance(x, str) and x for x in ids)
        and len(set(ids)) == len(ids),
        "unique nonempty step IDs required",
    )
    graph = {}
    for s in steps:
        require(s.get("skill") in catalog, f"unknown skill: {s.get('skill')}")
        deps = s.get("deps", [])
        require(
            isinstance(deps, list)
            and all(d in ids for d in deps)
            and len(set(deps)) == len(deps),
            "invalid dependencies",
        )
        graph[s["id"]] = set(deps)
        require(isinstance(s.get("args", {}), dict), "args must be an object")
        require(
            type(s.get("retries", 0)) is int and 0 <= s.get("retries", 0) <= 10,
            "retry budget must be 0..10",
        )
        require(
            isinstance(s.get("fallback", []), list)
            and len(s.get("fallback", [])) <= 10,
            "fallback budget must be <=10",
        )
        for alt in s.get("fallback", []):
            require(
                isinstance(alt, dict)
                and alt.get("skill") in catalog
                and isinstance(alt.get("args", {}), dict),
                "invalid fallback",
            )

        def refs(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    require(
                        set(value) == {"$ref"} and isinstance(value["$ref"], str),
                        "invalid output reference",
                    )
                    origin, _, path = value["$ref"].partition(".")
                    require(
                        origin in deps and bool(path),
                        "output reference must name a direct dependency",
                    )
                else:
                    for v in value.values():
                        refs(v)
            elif isinstance(value, list):
                for v in value:
                    refs(v)

        refs(s.get("args", {}))
        for alt in s.get("fallback", []):
            refs(alt.get("args", {}))
    try:
        list(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        raise ContractError("cyclic task graph") from exc
    final = plan.get("verification")
    require(final in ids, "final verification step required")
    ancestors = set()

    def visit(k):
        for d in graph[k]:
            if d not in ancestors:
                ancestors.add(d)
                visit(d)

    visit(final)
    require(
        ancestors == set(ids) - {final},
        "every required step must lead to final verification",
    )
    return plan
