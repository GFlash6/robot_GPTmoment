"""Shared application actions. Callers supply identity through trusted transports."""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import time
import uuid

from .contracts import ContractError, require, schema_check
from .runtime import Runtime
from .store import dumps


class ActionError(ContractError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Principal:
    subject: str
    permissions: frozenset[str]
    robots: frozenset[str]
    source: str

    def check(self, permission, robot_id=None):
        if not self.subject or permission not in self.permissions:
            raise ActionError("FORBIDDEN", "action permission denied")
        if robot_id is not None and "*" not in self.robots and robot_id not in self.robots:
            raise ActionError("FORBIDDEN", "robot outside permitted scope")


def object_schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1, "maxLength": 512}
REVISION = {"type": "integer", "minimum": 0}
EVENT_SEQ = {"type": "integer", "minimum": 0, "maximum": 2**63 - 1}
VERSION = {"task_id": TEXT, "expected_revision": REVISION, "expected_generation": REVISION}
CONTROL_REQUIRED = tuple(VERSION)
COMMAND_ACTIONS = {"task.submit", "task.pause", "task.cancel", "task.resume", "task.revise", "task.preempt"}


@dataclass(frozen=True)
class ActionSpec:
    permission: str
    schema: dict
    description: str


ACTIONS = {
    "task.list": ActionSpec("tasks.read", object_schema({"robot_id": TEXT}), "List permitted tasks"),
    "task.get": ActionSpec("tasks.read", object_schema({"task_id": TEXT}, ("task_id",)), "Read actual task state"),
    "task.events": ActionSpec("tasks.read", object_schema({"task_id": TEXT}, ("task_id",)), "Read task evidence events"),
    "task.events-page": ActionSpec("tasks.read", object_schema({"task_id": TEXT, "after_seq": EVENT_SEQ,
        "through_seq": EVENT_SEQ, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}, ("task_id",)),
        "Read a bounded, resumable page of actual task events; does not advance execution"),
    "asset.get": ActionSpec("assets.read", object_schema({"asset_id": TEXT}, ("asset_id",)), "Read asset metadata, without asserting byte verification"),
    "memory.search": ActionSpec("memory.read", object_schema({"text": TEXT, "robot_id": TEXT, "kind": TEXT,
        "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, ("text", "robot_id")),
        "Search scoped stored annotations and verify their source assets"),
    "command.get": ActionSpec("tasks.read", object_schema({"command_id": TEXT}, ("command_id",)), "Read command receipt, separately from task completion"),
    "task.submit": ActionSpec("tasks.submit", object_schema({
        "plan": {"type": "object"}, "robot_id": TEXT,
        "priority": {"type": "integer", "default": 0}, "goal": {"type": "string"},
        "completion_contract": {"type": "object"},
    }, ("plan", "robot_id")), "Queue a validated plan; does not execute it"),
    **{name: ActionSpec("tasks.control", object_schema(VERSION, CONTROL_REQUIRED),
                       "Queue a version-bound control request; not a stop acknowledgement")
       for name in ("task.pause", "task.cancel", "task.resume", "task.preempt")},
    "task.revise": ActionSpec("tasks.control", object_schema({**VERSION, "plan": {"type": "object"}},
                                                             (*CONTROL_REQUIRED, "plan")),
                              "Queue a new plan for a safely stopped task"),
}

SESSION_VERSION = {"session_id": TEXT, "expected_revision": REVISION}
LONG_TEXT = {"type": "string", "minLength": 1, "maxLength": 16000}
ACTIONS.update({
    "session.create": ActionSpec("planning.use", object_schema({"robot_id": TEXT, "goal": LONG_TEXT,
        "priority": {"type": "integer"}, "max_replans": {"type": "integer", "minimum": 0, "maximum": 10}}, ("robot_id", "goal")), "Create an operator goal session"),
    "session.completion-contract": ActionSpec("planning.use", object_schema({**SESSION_VERSION,
        "contract": {"type": ["object", "null"]}}, (*SESSION_VERSION, "contract")),
        "Set explicit final-verifier output requirements before planning; accepted task contracts stay fixed"),
    "session.get": ActionSpec("planning.use", object_schema({"session_id": TEXT}, ("session_id",)), "Read your session and drafts"),
    "session.message": ActionSpec("planning.use", object_schema({**SESSION_VERSION, "content": LONG_TEXT}, (*SESSION_VERSION, "content")), "Add a clarification; invalidates older analysis"),
    "session.context-policy": ActionSpec("planning.use", object_schema({**SESSION_VERSION,
        "auto_summary": {"type": "boolean"}, "keep_recent": {"type": "integer", "minimum": 2, "maximum": 32},
        "pinned_turn_ids": {"type": "array", "maxItems": 64, "uniqueItems": True, "items": TEXT}},
        (*SESSION_VERSION, "auto_summary")), "Configure opt-in budget reduction and mandatory original turns"),
    "session.summarize": ActionSpec("planning.use", object_schema({**SESSION_VERSION,
        "keep_recent": {"type": "integer", "minimum": 2, "maximum": 32},
        "pinned_turn_ids": {"type": "array", "maxItems": 64, "uniqueItems": True, "items": TEXT}},
        SESSION_VERSION), "Summarize older original turns; preserve pinned turns and recent originals"),
    "goal.analyze": ActionSpec("planning.use", object_schema(SESSION_VERSION, SESSION_VERSION), "Analyze the goal using the configured live model"),
    "plan.propose": ActionSpec("planning.use", object_schema(SESSION_VERSION, SESSION_VERSION), "Generate a live-model plan draft without execution"),
    "plan.submit": ActionSpec("planning.use", object_schema({**SESSION_VERSION, "draft_id": TEXT, "plan_hash": TEXT}, (*SESSION_VERSION, "draft_id", "plan_hash")), "Submit the exact reviewed draft through the command queue"),
    "selection.set": ActionSpec("planning.use", object_schema({**SESSION_VERSION, "task_id": TEXT,
        "task_revision": REVISION, "task_generation": REVISION,
        "step_ids": {"type": "array", "items": TEXT, "maxItems": 20, "uniqueItems": True}},
        (*SESSION_VERSION, "task_id", "task_revision", "task_generation", "step_ids")), "Bind a versioned task selection to this session"),
    "task.explain": ActionSpec("planning.use", object_schema({**SESSION_VERSION, "question": LONG_TEXT}, (*SESSION_VERSION, "question")), "Explain selected actual records using the live model; does not change task state"),
    "session.attach-assets": ActionSpec("planning.use", object_schema({**SESSION_VERSION,
        "asset_ids": {"type": "array", "items": TEXT, "maxItems": 20, "uniqueItems": True}},
        (*SESSION_VERSION, "asset_ids")), "Attach verified existing assets as evidence, without inventing world state"),
    "session.attach-memories": ActionSpec("planning.use", object_schema({**SESSION_VERSION,
        "memories": {"type": "array", "maxItems": 10, "items": object_schema(
            {"memory_id": TEXT, "record_hash": TEXT}, ("memory_id", "record_hash"))}},
        (*SESSION_VERSION, "memories")), "Bind exact retrieved memory versions to a session"),
})
SESSION_ACTIONS = {"session.completion-contract", "session.context-policy", "session.summarize", "session.create", "session.get", "session.message", "goal.analyze", "plan.propose", "plan.submit", "selection.set", "task.explain", "session.attach-assets", "session.attach-memories"}

ACTIONS.update({
    "automation.create": ActionSpec("automations.manage", object_schema({"robot_id": TEXT, "question": LONG_TEXT,
        "max_runs": {"type": "integer", "minimum": 1, "maximum": 100}}, ("robot_id", "question", "max_runs")),
        "Subscribe to future failed execution events for bounded model diagnostics"),
    "automation.set-enabled": ActionSpec("automations.manage", object_schema({"automation_id": TEXT,
        "expected_revision": REVISION, "enabled": {"type": "boolean"}}, ("automation_id", "expected_revision", "enabled")),
        "Pause or enable owned diagnostics; skipped events are not replayed"),
    "automation.list": ActionSpec("automations.manage", object_schema({}), "List owned automation rules"),
    "automation.runs": ActionSpec("automations.manage", object_schema({"automation_id": TEXT}, ("automation_id",)),
        "Read owned event diagnostic runs and actual model evidence"),
    "automation.retry": ActionSpec("automations.manage", object_schema({"run_id": TEXT,
        "expected_status": {"enum": ["failed", "unresolved"]}}, ("run_id", "expected_status")),
        "Explicitly queue another model diagnosis within the original rule budget; preserves the uncertain call"),
})


def output_schema(name):
    if name == 'task.events-page':
        return object_schema({'task_id': TEXT, 'events': {'type': 'array', 'maxItems': 500},
            'next_seq': EVENT_SEQ, 'through_seq': EVENT_SEQ, 'has_more': {'type': 'boolean'}},
            ('task_id', 'events', 'next_seq', 'through_seq', 'has_more'))
    if name in COMMAND_ACTIONS | {"plan.submit", "command.get"}:
        return {"type": "object", "required": ["command_id", "task_id", "status", "confirmed_stopped"],
                "properties": {"command_id": TEXT, "task_id": TEXT,
                    "status": {"enum": ["accepted", "applied", "rejected"]}, "confirmed_stopped": {"const": False}}}
    key = {"task.list": "items", "memory.search": "items", "task.get": "task", "task.events": "events", "asset.get": "asset",
           "plan.propose": "draft", "task.explain": "explanation", "automation.create": "automation",
           "automation.set-enabled": "automation", "automation.list": "items", "automation.runs": "items",
           "automation.retry": "run"}.get(name, "session")
    return {"type": "object", "required": [key], "properties": {key: {"type": "array" if key in {"items", "events"} else "object"}}}


# Explicit coverage: a newly registered action must declare its observable effect.
ACTION_EFFECTS = {
    **dict.fromkeys({'task.list', 'task.get', 'task.events', 'task.events-page', 'asset.get',
                     'memory.search', 'command.get', 'session.get', 'automation.list', 'automation.runs'}, 'read'),
    **dict.fromkeys(COMMAND_ACTIONS | {'plan.submit'}, 'task_command'),
    **dict.fromkeys({'goal.analyze', 'plan.propose', 'task.explain', 'session.summarize'}, 'model_call'),
    **dict.fromkeys({'session.create', 'session.message', 'session.context-policy',
                     'session.completion-contract', 'selection.set', 'session.attach-assets',
                     'session.attach-memories'}, 'session_write'),
    **dict.fromkeys({'automation.create', 'automation.set-enabled'}, 'automation_write'),
    'automation.retry': 'diagnosis_queue',
}
require(set(ACTION_EFFECTS) == set(ACTIONS), 'every action requires an explicit effect declaration')


def action_contract(name):
    """Detached discovery metadata; read actions still write an invocation audit record."""
    spec = ACTIONS[name]
    effect = ACTION_EFFECTS[name]
    contract = {
        'contract_version': 1,
        'description': spec.description,
        'input_schema': spec.schema,
        'output_schema': output_schema(name),
        'permission': spec.permission,
        'effect_kind': effect,
        'requires_idempotency_key': effect != 'read',
        'calls_model': effect == 'model_call',
        'may_schedule_model': effect in {'automation_write', 'diagnosis_queue'},
        'dispatches_skill': False,
        'writes_audit_record': True,
    }
    contract['contract_hash'] = fingerprint({'action': name, **contract})
    return deepcopy(contract)


def action_catalog(principal):
    # Discovery advertises the base permission only. Ownership, extra permissions,
    # robot scope, versions and actual state are checked again when invoked.
    require(bool(principal.subject), 'action discovery requires a subject')
    return {name: action_contract(name) for name, spec in ACTIONS.items()
            if spec.permission in principal.permissions}


def fingerprint(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def check_idempotency_owner(store, subject, key, owner):
    """Check all persisted key formats inside the caller's write transaction.

    Keep historical automation IDs so upgrades replay the original receipt.
    Existing ambiguous historical ownership is rejected, never silently migrated.
    """
    identity = fingerprint([subject, key])
    candidates = [('commands', identity), ('application_requests', identity)]
    candidates.extend(('automation_requests', fingerprint([subject, name, key]))
                      for name in ('automation.create', 'automation.set-enabled', 'automation.retry'))
    for candidate in candidates:
        if candidate != owner and store.get(*candidate) is not None:
            raise ActionError('IDEMPOTENCY_CONFLICT', 'idempotency key already belongs to another action request')


def local_principal():
    import getpass
    return Principal("local:" + getpass.getuser(), frozenset(s.permission for s in ACTIONS.values()),
                     frozenset({"*"}), "cli")


class Actions:
    def __init__(self, store, *, model_config=None):
        self.store = store
        self.runtime = Runtime(store)
        self.model_config = model_config

    def task(self, task_id, principal, permission="tasks.read"):
        task = self.store.get("tasks", task_id)
        if task is None:
            raise ActionError("NOT_FOUND", "unknown task")
        principal.check(permission, task["robot_id"])
        return task

    def call(self, name, args, principal, *, request_id=None, idempotency_key=None):
        call_id = str(uuid.uuid4())
        record = {"id": call_id, "request_id": request_id or call_id, "action": name,
                  "subject": principal.subject, "source": principal.source, "created_at": time.time()}
        try:
            spec = ACTIONS.get(name)
            if spec is None:
                raise ActionError("NOT_FOUND", "unknown action")
            principal.check(spec.permission)
            contract = action_contract(name)
            record.update(contract_version=contract["contract_version"],
                          contract_hash=contract["contract_hash"], effect_kind=contract["effect_kind"])
            schema_check(spec.schema, args)
            if name.startswith("automation."):
                from .automations import call
                result = call(self, name, args, principal, idempotency_key)
            elif name in SESSION_ACTIONS:
                result = self.session_call(name, args, principal, idempotency_key, record)
            elif name in COMMAND_ACTIONS:
                require(isinstance(idempotency_key, str) and 0 < len(idempotency_key) <= 256,
                        "mutation requires an idempotency key")
                result = self.enqueue(name, args, principal, idempotency_key, record)
            else:
                result = self.query(name, args, principal)
            schema_check(output_schema(name), result)
            record.update(status="returned", command_id=result.get("command_id"), task_id=result.get("task_id"))
            return {"action_call_id": call_id, "result": result}
        except Exception as exc:
            record.update(status="rejected", error_code=getattr(exc, "code", "INVALID_ARGUMENT"), error=str(exc))
            raise
        finally:
            self.store.put("action_calls", call_id, record)

    def session_call(self, name, args, principal, key, record):
        from .sessions import Sessions
        sessions = Sessions(self)
        if name == "session.get":
            return sessions.call(name, args, principal, record)
        if name == "session.create":
            principal.check("planning.use", args["robot_id"])
        else:
            sessions.get(args["session_id"], principal)
        require(isinstance(key, str) and 0 < len(key) <= 256, "mutation requires an idempotency key")
        identity = fingerprint([principal.subject, key])
        payload_hash = fingerprint({"action": name, "args": args})
        with self.store.transaction():
            check_idempotency_owner(self.store, principal.subject, key, ("application_requests", identity))
            old = self.store.get("application_requests", identity)
            if old:
                if old["payload_hash"] != payload_hash:
                    raise ActionError("IDEMPOTENCY_CONFLICT", "key already belongs to another request")
                if old["status"] == "completed":
                    return old["result"]
                raise ActionError("REQUEST_UNRESOLVED", "prior request did not complete; inspect its action record before retrying")
            request = {"id": identity, "payload_hash": payload_hash, "status": "running", "action_call_id": record["id"]}
            self.store.put("application_requests", identity, request)
            self.store.put("action_calls", record["id"], {**record, "status": "running"})
        try:
            # Model IO stays outside SQLite transactions. A crashed model call is
            # never silently replayed; its stored request/response remains evidence.
            if name in {"goal.analyze", "plan.propose", "task.explain", "session.summarize"}:
                result = sessions.call(name, args, principal, record)
                with self.store.transaction():
                    self.store.put("application_requests", identity, {**request, "status": "completed", "result": result})
            else:
                with self.store.transaction():
                    result = sessions.call(name, args, principal, record)
                    self.store.put("application_requests", identity, {**request, "status": "completed", "result": result})
            return result
        except Exception as exc:
            self.store.put("application_requests", identity, {**request, "status": "failed", "error": str(exc)})
            raise

    def query(self, name, args, principal):
        if name == 'task.events-page':
            task = self.task(args['task_id'], principal)
            return {'task_id': task['id'], **self.store.event_page(task['id'],
                after_seq=args.get('after_seq', 0), through_seq=args.get('through_seq'), limit=args.get('limit', 100))}
        if name == "memory.search":
            from .context_memory import search_memories
            principal.check("memory.read", args["robot_id"])
            principal.check("assets.read", args["robot_id"])
            return {"items": search_memories(self.store, args["text"], args["robot_id"],
                    kind=args.get("kind"), limit=args.get("limit", 5))}
        if name == "task.list":
            if args.get("robot_id"):
                principal.check("tasks.read", args["robot_id"])
            return {"items": [t for t in self.store.list("tasks")
                              if ("*" in principal.robots or t["robot_id"] in principal.robots)
                              and (not args.get("robot_id") or t["robot_id"] == args["robot_id"])]}
        if name in {"task.get", "task.events"}:
            task = self.task(args["task_id"], principal)
            return ({"task_id": task["id"], "task": task} if name == "task.get" else
                    {"task_id": task["id"], "events": self.store.events(task["id"])})
        if name == "asset.get":
            asset = self.store.get("assets", args["asset_id"])
            if asset is None:
                raise ActionError("NOT_FOUND", "unknown asset")
            robot = asset["metadata"].get("robot_id")
            if robot is None and "*" not in principal.robots:
                raise ActionError("FORBIDDEN", "unscoped assets require full ledger access")
            principal.check("assets.read", robot)
            return {"asset": asset, "bytes_verified": False}
        command = self.store.get("commands", args["command_id"])
        if command is None:
            raise ActionError("NOT_FOUND", "unknown command")
        principal.check("tasks.read", command["robot_id"])
        return command_receipt(command)

    def enqueue(self, name, args, principal, key, record):
        command_id = fingerprint([principal.subject, key])
        payload_hash = fingerprint({"action": name, "args": args})
        with self.store.transaction():
            check_idempotency_owner(self.store, principal.subject, key, ("commands", command_id))
            old = self.store.get("commands", command_id)
            if old:
                principal.check(ACTIONS[name].permission, old["robot_id"])
                if old["payload_hash"] != payload_hash:
                    raise ActionError("IDEMPOTENCY_CONFLICT", "idempotency key already has a different request")
                return command_receipt(old)
            if name == "task.submit":
                robot_id = args["robot_id"]
                principal.check(ACTIONS[name].permission, robot_id)
                require("/" not in robot_id, "robot_id must be one namespace segment")
                self.runtime._check_plan(args["plan"], self.runtime.catalog(), robot_id, args.get("completion_contract"))
                task_id = str(uuid.uuid4())
            else:
                task = self.task(args["task_id"], principal, ACTIONS[name].permission)
                check_version(task, args)
                robot_id, task_id = task["robot_id"], task["id"]
                if name == "task.revise":
                    from .completion import task_contract
                    self.runtime._check_plan(args["plan"], self.runtime.catalog(), robot_id, task_contract(task))
            command = {"id": command_id, "action": name, "args": args, "payload_hash": payload_hash,
                       "task_id": task_id, "robot_id": robot_id, "subject": principal.subject,
                       "action_call_id": record["id"], "request_id": record["request_id"],
                       "status": "accepted", "created_at": time.time(),
                       "catalog_hash": fingerprint(self.runtime.catalog()) if "plan" in args else None}
            self.store.put("commands", command_id, command)
            self.store.event(task_id, "command_accepted", {"command_id": command_id, "action": name,
                                                         "action_call_id": record["id"], "subject": principal.subject})
            # The originating call and command must survive the same commit.
            self.store.put("action_calls", record["id"], {**record, "status": "accepted", "command_id": command_id})
            return command_receipt(command)


def check_version(task, args):
    if (task["revision"], task["generation"]) != (args["expected_revision"], args["expected_generation"]):
        raise ActionError("STALE_TASK", "task version changed; reload before submitting")


def command_receipt(command):
    return {"command_id": command["id"], "task_id": command["task_id"],
            "status": command["status"], "action": command["action"],
            "action_call_id": command["action_call_id"], "created_at": command["created_at"],
            "applied_at": command.get("applied_at"), "error": command.get("error"),
            "confirmed_stopped": False}


def process_commands(store, task_id=None):
    """Worker-only: apply ledger mutations and their receipts in one commit."""
    commands = sorted((c for c in store.list("commands") if c["status"] == "accepted"
                       and (task_id is None or c["task_id"] == task_id)),
                      key=lambda c: (c["created_at"], c["id"]))
    for queued in commands:
        with store.task_lock(queued["task_id"]), store.transaction():
            command = store.get("commands", queued["id"])
            if command["status"] != "accepted":
                continue
            try:
                # A failed transition rolls back even if it wrote before rejecting.
                with store.transaction():
                    apply_command(store, command)
            except ContractError as exc:
                command.update(status="rejected", error={"code": getattr(exc, "code", "INVALID_STATE"), "message": str(exc)})
            else:
                command.update(status="applied", applied_at=time.time())
            store.put("commands", command["id"], command)
            store.event(command["task_id"], "command_" + command["status"], command_receipt(command))


def apply_command(store, command):
    from .context_memory import verify_bindings
    runtime = Runtime(store)
    name, args, task_id = command["action"], command["args"], command["task_id"]
    if command.get("context_snapshot_id"):
        from .context_snapshot import read_snapshot
        snapshot = read_snapshot(store, command["context_snapshot_id"], robot_id=command["robot_id"],
                      session_id=command.get("lineage", {}).get("session_id"),
                      catalog_hash=fingerprint(runtime.catalog()), expected_hash=command.get("context_snapshot_hash"))
        from .context_assets import verify_session_assets
        verify_session_assets(store, snapshot["session"])
        from .completion import same_contract
        if name == "task.submit":
            expected_completion = args.get("completion_contract")
        else:
            target = store.get("tasks", task_id)
            require(target is not None, "unknown task")
            expected_completion = target.get("completion_contract")
        require(same_contract(snapshot["session"].get("completion_contract"), expected_completion),
                "command completion contract differs from snapshot")
    verify_bindings(store, command.get("memory_bindings", []), command["robot_id"])
    if command.get("expires_at") is not None and command["expires_at"] <= time.time():
        raise ActionError("EXPIRED_DRAFT", "plan draft expired before worker acceptance")
    if command["catalog_hash"] is not None and command["catalog_hash"] != fingerprint(runtime.catalog()):
        raise ActionError("STALE_CATALOG", "skill catalog changed after command acceptance")
    if name == "task.submit":
        runtime.submit(args["plan"], command["robot_id"], args.get("priority", 0), args.get("goal"),
                       task_id=task_id, agent_context=command.get("agent_context"), completion_contract=args.get("completion_contract"))
    else:
        task = store.get("tasks", task_id)
        require(task is not None, "unknown task")
        check_version(task, args)
        control = store.get("controls", task_id)
        pending_cancel = any(c["task_id"] == task_id and c["action"] == "task.cancel" and c["status"] == "accepted"
                             for c in store.list("commands"))
        if name in {"task.resume", "task.revise"} and (pending_cancel or (control and control["mode"] == "cancel")):
            raise ActionError("CANCEL_PENDING", "cancellation takes precedence over resume or revision")
        if name in {"task.pause", "task.cancel"}:
            runtime.interrupt(task_id, name.split(".")[1])
        elif name == "task.resume":
            runtime.resume(task_id)
        elif name == "task.revise":
            runtime.revise(task_id, args["plan"])
        elif name == "task.preempt":
            command["affected_task_ids"] = runtime.preempt(task_id)
        else:
            raise ContractError("unsupported queued action")
    task = store.get("tasks", task_id)
    task["last_command_id"] = command["id"]
    if name == "task.submit":
        task["origin"] = {key: command[key] for key in ("action_call_id", "request_id", "subject")}
        task["origin"]["command_id"] = command["id"]
    if command.get("lineage"):
        task.update(command["lineage"])
    if command.get("context_snapshot_id"):
        task["context_snapshot_id"] = command["context_snapshot_id"]
        task["context_snapshot_hash"] = command.get("context_snapshot_hash")
    store.put("tasks", task_id, task)
