"""Real local data skills and explicit remote execution protocol."""

import os
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import httpx
from .contracts import require, schema_check, ContractError
from .memory import Memory


LOCAL_SPECS = {
    "asset.verify-set": {
        "adapter": "local",
        "input_schema": {
            "type": "object", "required": ["items"], "additionalProperties": False,
            "properties": {"items": {"type": "array", "minItems": 1, "maxItems": 100,
                "items": {"type": "object", "required": ["asset_id", "sha256"], "additionalProperties": False,
                    "properties": {"asset_id": {"type": "string", "minLength": 1},
                                   "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}}}},
        },
        "output_schema": {
            "type": "object", "required": ["verified", "count", "items"], "additionalProperties": False,
            "properties": {"verified": {"type": "boolean"}, "count": {"type": "integer", "minimum": 1},
                "items": {"type": "array", "minItems": 1, "items": {
                    "type": "object", "required": ["asset_id", "sha256", "size"], "additionalProperties": False,
                    "properties": {"asset_id": {"type": "string"}, "sha256": {"type": "string"},
                                   "size": {"type": "integer", "minimum": 0}}}}},
        },
        "checks": [{"path": "verified", "op": "eq", "value": True}],
    },
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
        "output_schema": {"type": "object", "required": ["asset_id", "sha256", "size"],
            "properties": {"asset_id": {"type": "string"}, "sha256": {"type": "string"},
                           "size": {"type": "integer", "minimum": 0}}, "additionalProperties": False},
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
        "output_schema": {"type": "object", "required": ["sha256", "size", "verified"],
            "properties": {"sha256": {"type": "string"}, "size": {"type": "integer", "minimum": 0},
                           "verified": {"type": "boolean"}}, "additionalProperties": False},
        "checks": [{"path": "verified", "op": "eq", "value": True}],
    },
}


def validate_spec(name, spec):
    require(isinstance(name, str) and bool(name), "skill name required")
    require(spec.get("adapter") in {"local", "http"}, "adapter must be local or http")
    if 'fencing_domain' in spec:
        from .fencing import validate_domain
        validate_domain(spec['fencing_domain'])
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

    def call(self, operation, name, spec, execution_id, args, robot_id, *, authority=None):
        if spec["adapter"] == "http":
            headers = {}
            if spec.get('fencing_domain'):
                from .fencing import validate_authority
                validate_authority(authority, spec['fencing_domain'])
                headers['X-Execution-Authority'] = json.dumps(authority, ensure_ascii=True)
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
                            **({'authority': authority} if authority is not None else {}),
                        },
                    )
                elif operation == "cancel":
                    response = client.post(url + "/cancel", headers=headers)
                else:
                    response = client.get(url, headers=headers)
                response.raise_for_status()
                result = response.json()
                if spec.get('fencing_domain'):
                    require(isinstance(result, dict), 'invalid execution authority response')
                    validate_authority(result.get('authority'), spec['fencing_domain'])
                    require(isinstance(result, dict) and result.get('authority') == authority,
                            'execution response authority mismatch')
                return result
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
            elif name == "asset.verify-set":
                items = args["items"]
                require(len({item['asset_id'] for item in items}) == len(items), 'duplicate asset in verification set')
                verified, evidence = [], []
                for item in items:
                    data = self.memory.read(item['asset_id'])
                    asset = self.store.get('assets', item['asset_id'])
                    require(asset['metadata'].get('robot_id') in {None, robot_id}, 'verification asset robot mismatch')
                    digest = hashlib.sha256(data).hexdigest()
                    require(digest == item['sha256'], 'verification asset differs from expected sha256')
                    verified.append({'asset_id': asset['id'], 'sha256': digest, 'size': len(data)})
                    evidence.append({'source': 'asset:' + asset['id'], 'sha256': digest})
                output = {'verified': True, 'count': len(verified), 'items': verified}
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
