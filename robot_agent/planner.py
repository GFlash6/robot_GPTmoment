"""Planning policy over the reusable model-call boundary."""

import json
import time
import uuid

from .contracts import require, validate_plan, ContractError
from .context_builder import ContextBuilder
from .context_codec import encode_bundle, decode_bundle
from .context_memory import record_hash
from .context_models import ContextFragment, ContextManifest
from .model_call import ModelCaller
from .model_transport import ModelCallError


class Planner:
    def __init__(self, store, config, *, context_builder=None):
        self.store = store
        self.config = config
        self.context_builder = context_builder or ContextBuilder(store)

    def plan(self, goal, catalog, context=None, *, context_request=None, context_session=None):
        require(isinstance(goal, str) and bool(goal.strip()), "goal required")
        # Validate configuration before creating an evidence record, preserving the
        # distinction between a missing configuration and a rejected actual call.
        caller = ModelCaller(self.config)
        capabilities = {
            k: {
                f: v
                for f, v in spec.items()
                if f
                in {
                    "input_schema",
                    "output_schema",
                    "checks",
                    "resources",
                    "cancelable",
                    "replay_safe",
                    "verifier",
                }
            }
            for k, spec in catalog.items()
        }
        diagnostics = ()
        encoded_bundle = None
        if context_request is not None:
            bundle = self.context_builder.build(context_request, catalog, **({"session_override": context_session} if context_session is not None else {}))
            encoded_bundle = encode_bundle(bundle)
            bundle = decode_bundle(encoded_bundle)
            fragments = bundle.fragments
            diagnostics = bundle.diagnostics
        elif context is not None:
            fragments = (
                ContextFragment(
                    id="planner_runtime_context",
                    content=json.dumps(context, ensure_ascii=False),
                    priority=100,
                    required=True,
                    kind="task_state",
                    source="legacy_planner_context",
                    authority="data",
                ),
            )
        else:
            fragments = ()
        key = str(uuid.uuid4())
        record = {
            "id": key,
            "model": caller.config.model,
            "created_at": time.time(),
            "goal": goal,
            "method": "planning",
            "status": "requesting",
        }
        self.store.put("model_responses", key, record)
        try:
            if encoded_bundle is not None:
                self.store.put("context_bundles", key, encoded_bundle)
                record.update(context_bundle_id=key, context_bundle_hash=record_hash(encoded_bundle))
            prepared = caller.prepare(
                "planning",
                {"goal": goal, "skills": capabilities},
                context=fragments,
            )
            manifest_id = str(uuid.uuid4())
            request_id = context_request.request_id if context_request else key
            phase = context_request.phase if context_request else "planning"
            manifest = ContextManifest(
                request_id=request_id,
                phase=phase,
                included=tuple(x.id for x in prepared.allocation.included),
                dropped=prepared.allocation.dropped,
                estimated_input_tokens=prepared.allocation.estimated_input_tokens,
                input_token_limit=prepared.allocation.input_token_limit,
                reserved_output_tokens=prepared.allocation.reserved_output_tokens,
                estimator=prepared.allocation.estimator,
                renderer_version=caller._renderer.version,
                provider_diagnostics=tuple({**d,
                    "included": [fid for fid in d["fragment_ids"] if fid in {f.id for f in prepared.allocation.included}],
                    "dropped": [item for item in prepared.allocation.dropped if item["id"] in d["fragment_ids"]],
                } for d in diagnostics),
                sources=tuple({"id": f.id, "source": f.source, "authority": f.authority,
                               "evidence_ids": list(f.evidence_ids), "metadata": f.metadata}
                              for f in prepared.allocation.included),
            )
            self.store.put(
                "context_manifests",
                manifest_id,
                {"id": manifest_id, **manifest.as_dict()},
            )
            record.update(
                context_manifest_id=manifest_id,
                context_allocation=prepared.allocation.as_dict(),
                request={"messages": list(prepared.request.messages),
                         "response_format": prepared.request.response_format,
                         "model": caller.config.model},
            )
            self.store.put("model_responses", key, record)
            result = caller.send_prepared(prepared)
            record.update(
                http_status=result.transport.status_code,
                raw=result.transport.raw,
                elapsed_ms=result.transport.elapsed_ms,
                context_allocation=result.allocation.as_dict(),
            )
            self.store.put("model_responses", key, record)
            plan = json.loads(result.content)
            validate_plan(plan, catalog)
            final = next(
                step for step in plan["steps"] if step["id"] == plan["verification"]
            )
            require(
                catalog[final["skill"]].get("verifier", False),
                "model plan must finish with a registered verifier skill",
            )
            record.update(
                status="validated",
                response_id=result.response_id,
                actual_model=result.actual_model,
                plan=plan,
            )
            self.store.put("model_responses", key, record)
            self.last_response_id = key
            return plan
        except Exception as exc:
            if isinstance(exc, ModelCallError) and exc.response is not None:
                record.update(
                    http_status=exc.response.status_code,
                    raw=exc.response.raw,
                    elapsed_ms=exc.response.elapsed_ms,
                )
            record.update(status="rejected", error=type(exc).__name__ + ": " + str(exc))
            self.store.put("model_responses", key, record)
            raise ContractError(
                f"model planning failed; evidence record {key}: {type(exc).__name__}"
            ) from exc
