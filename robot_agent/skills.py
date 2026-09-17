"""Real local data skills and explicit remote execution protocol."""

import os
from pathlib import Path
from urllib.parse import urlparse
import httpx
from .contracts import require, schema_check, ContractError
from .memory import Memory


LOCAL_SPECS = {
    "file.copy": {
        "adapter": "local",
        "input_schema": {
            "type": "object",
            "required": ["source", "target"],
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
                "chunk_bytes": {"type": "integer", "minimum": 1, "maximum": 8388608},
            },
            "additionalProperties": False,
        },
        "output_schema": {"type": "object", "required": ["sha256", "verified", "path"]},
        "checks": [{"path": "verified", "op": "eq", "value": True}],
    },
    "file.ingest": {
        "adapter": "local",
        "input_schema": {
            "type": "object",
            "required": ["path", "metadata"],
            "properties": {"path": {"type": "string"}, "metadata": {"type": "object"}},
            "additionalProperties": False,
        },
        "output_schema": {"type": "object", "required": ["asset_id", "sha256"]},
        "checks": [{"path": "asset_id", "op": "nonempty"}],
    },
    "asset.verify": {
        "adapter": "local",
        "input_schema": {
            "type": "object",
            "required": ["asset_id"],
            "properties": {"asset_id": {"type": "string"}},
            "additionalProperties": False,
        },
        "output_schema": {"type": "object", "required": ["sha256", "size", "verified"]},
        "checks": [{"path": "verified", "op": "eq", "value": True}],
    },
}


def validate_spec(name, spec):
    require(isinstance(name, str) and bool(name), "skill name required")
    require(spec.get("adapter") in {"local", "http"}, "adapter must be local or http")
    for key in ("input_schema", "output_schema"):
        require(isinstance(spec.get(key), dict), f"{key} required")
        import jsonschema

        try:
            jsonschema.Draft202012Validator.check_schema(spec[key])
        except jsonschema.SchemaError as exc:
            raise ContractError(exc.message) from exc
    require(
        isinstance(spec.get("resources", {}), dict)
        and all(
            isinstance(k, str) and k and type(v) is int and v > 0
            for k, v in spec.get("resources", {}).items()
        ),
        "invalid skill resources",
    )
    require(
        type(spec.get("cancelable", False)) is bool
        and type(spec.get("replay_safe", False)) is bool,
        "capability flags must be booleans",
    )
    require(
        type(spec.get("timeout", 10)) in (float, int)
        and 0 < spec.get("timeout", 10) <= 120,
        "HTTP timeout must be 0..120 seconds",
    )
    require(
        type(spec.get("execution_timeout", 300)) in (float, int)
        and 0 < spec.get("execution_timeout", 300) <= 86400,
        "execution timeout must be 0..86400 seconds",
    )
    for check in spec.get("checks", []):
        require(
            isinstance(check, dict)
            and isinstance(check.get("path"), str)
            and check.get("op") in {"eq", "nonempty", "gte", "lte"},
            "invalid postcondition",
        )
        require(
            check["op"] == "nonempty" or "value" in check, "postcondition value missing"
        )
    if spec["adapter"] == "local":
        require(name in LOCAL_SPECS, "unknown local skill")
    else:
        endpoint = urlparse(spec.get("endpoint", ""))
        require(
            endpoint.scheme in {"http", "https"}
            and endpoint.hostname
            and not endpoint.username
            and not endpoint.password
            and not endpoint.query
            and not endpoint.fragment,
            "explicit HTTP endpoint without credentials required",
        )


class Skills:
    def __init__(self, store):
        self.store = store
        self.memory = Memory(store)

    def call(self, operation, name, spec, execution_id, args, robot_id):
        if spec["adapter"] == "http":
            headers = {}
            if spec.get("token_env"):
                token = os.environ.get(spec["token_env"])
                require(
                    bool(token),
                    "configured skill token environment variable is missing",
                )
                headers["Authorization"] = "Bearer " + token
            url = spec["endpoint"].rstrip("/") + "/executions/" + execution_id
            with httpx.Client(
                timeout=spec.get("timeout", 10), follow_redirects=False, trust_env=False
            ) as client:
                if operation == "start":
                    response = client.put(
                        url,
                        headers=headers,
                        json={
                            "execution_id": execution_id,
                            "skill": name,
                            "robot_id": robot_id,
                            "args": args,
                        },
                    )
                elif operation == "cancel":
                    response = client.post(url + "/cancel", headers=headers)
                else:
                    response = client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
        if name == "file.copy":
            from .file_copy import copy_step

            schema_check(spec["input_schema"], args)
            return copy_step(self.store, operation, execution_id, args, spec)
        saved = self.store.get("local_results", execution_id)
        if saved is not None:
            return saved
        require(
            operation == "start",
            "local execution has no durable result; reconcile before retry",
        )
        try:
            schema_check(spec["input_schema"], args)
            if name == "file.ingest":
                path = Path(args["path"]).resolve()
                roots = [Path(p).resolve() for p in spec.get("allowed_roots", [])]
                require(
                    any(path == root or root in path.parents for root in roots),
                    "file outside configured allowed roots",
                )
                asset = self.memory.ingest(path, args["metadata"])
                output = {
                    "asset_id": asset["id"],
                    "sha256": asset["sha256"],
                    "size": asset["size"],
                }
                evidence = [
                    {"source": "asset:" + asset["id"], "sha256": asset["sha256"]}
                ]
            else:
                data = self.memory.read(args["asset_id"])
                asset = self.store.get("assets", args["asset_id"])
                output = {
                    "sha256": asset["sha256"],
                    "size": len(data),
                    "verified": True,
                }
                evidence = [
                    {"source": "asset:" + asset["id"], "sha256": asset["sha256"]}
                ]
            result = {
                "execution_id": execution_id,
                "status": "succeeded",
                "quiescent": True,
                "output": output,
                "evidence": evidence,
            }
        except (OSError, ContractError) as exc:
            result = {
                "execution_id": execution_id,
                "status": "failed",
                "quiescent": True,
                "output": {},
                "evidence": [
                    {"source": "local:" + name, "error_type": type(exc).__name__}
                ],
                "error": type(exc).__name__ + ": " + str(exc),
            }
        self.store.put("local_results", execution_id, result)
        return result
