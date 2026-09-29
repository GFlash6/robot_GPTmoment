"""Live-model interpretation with references constrained to actual selected records."""

import json
import time
import uuid

from .context_builder import ContextBuilder
from .context_codec import encode_bundle, decode_bundle
from .context_memory import record_hash
from .context_models import ContextRequest, GoalContext
from .context_evidence import context_manifest
from .contracts import require, schema_check
from .model_call import ModelCaller
from .model_transport import environment_config, ModelCallError


def explain_selection(actions, session, action_record, question):
    selection = session.get("selection")
    require(selection is not None and bool(selection["step_ids"]), "select actual task steps before requesting an explanation")
    task = actions.store.get("tasks", selection["task_id"])
    require(task is not None, "selected task unavailable")
    request = ContextRequest(request_id=action_record["request_id"], phase="replanning",
        goal=GoalContext.from_input(session["original_input"]), session_id=session["id"],
        robot_id=session["robot_id"], task_id=task["id"], revision=task["revision"], generation=task["generation"])
    encoded_bundle = encode_bundle(ContextBuilder(actions.store).build(request, task["catalog"]))
    bundle = decode_bundle(encoded_bundle)
    refs = [f"{task['id']}:{step}" for step in selection["step_ids"]]
    caller = ModelCaller(actions.model_config or environment_config())
    arguments = {"question": question,
        "instruction": (
            "Explain only the selected actual task ledger records. Model interpretation is not execution evidence. "
            "Distinguish observed failures from hypotheses; never invent observations, recovery, or success. "
            "Return JSON with summary (string), record_refs (nonempty array of supplied reference strings), "
            "and unknowns (array of strings). Answer in the user's language. Allowed record_refs: " + json.dumps(refs)),
        "response_format": {"type": "json_object"}}
    prepared = caller.prepare("qa", arguments, context=bundle.fragments)
    key = str(uuid.uuid4())
    manifest = context_manifest(bundle, prepared, caller._renderer.version)
    record = {"id": key, "method": "task_explanation", "model": caller.config.model, "created_at": time.time(),
        "status": "requesting", "session_id": session["id"], "action_call_id": action_record["id"],
        "request": {"messages": list(prepared.request.messages), "model": caller.config.model,
                    "response_format": prepared.request.response_format},
        "record_refs": refs, "task_revision": task["revision"], "task_generation": task["generation"],
        "context_bundle_id": key, "context_bundle_hash": record_hash(encoded_bundle),
        "context_manifest_id": key, "context_allocation": prepared.allocation.as_dict(),
        "preparation": {"method": "qa", "arguments": arguments}}
    # Commit the exact evidence used to prepare this request before network IO.
    with actions.store.transaction():
        actions.store.put("context_bundles", key, encoded_bundle)
        actions.store.put("context_manifests", key, {"id": key, **manifest.as_dict()})
        actions.store.put("model_responses", key, record)
    try:
        result = caller.send_prepared(prepared)
        record.update(raw=result.transport.raw, http_status=result.transport.status_code,
            actual_model=result.actual_model, response_id=result.response_id, elapsed_ms=result.transport.elapsed_ms)
        parsed = json.loads(result.content)
        schema_check({"type": "object", "required": ["summary", "record_refs", "unknowns"], "additionalProperties": False,
            "properties": {"summary": {"type": "string", "minLength": 1},
                "record_refs": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"enum": refs}},
                "unknowns": {"type": "array", "items": {"type": "string"}}}}, parsed)
        record.update(status="validated", parsed=parsed)
        return {"explanation": parsed, "model_response_id": key, "task_id": task["id"],
                "task_revision": task["revision"], "task_generation": task["generation"],
                "selected_records": {step: task["steps"][step] for step in selection["step_ids"]},
                "is_execution_evidence": False}
    except Exception as exc:
        if isinstance(exc, ModelCallError) and exc.response:
            record.update(raw=exc.response.raw, http_status=exc.response.status_code)
        record.update(status="rejected", error=str(exc))
        raise
    finally:
        actions.store.put("model_responses", key, record)
