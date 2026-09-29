"""Preliminary model analysis and user-question generation for raw goals."""

from dataclasses import dataclass
import json
import time
import uuid

from .context_models import ContextBundle, ContextRequest, GoalContext
from .context_codec import encode_bundle, decode_bundle
from .context_evidence import context_manifest
from .context_memory import record_hash
from .contracts import ContractError, require
from .model_call import ModelCaller
from .model_transport import ModelCallError
from .store import dumps


@dataclass(frozen=True)
class GoalAnalysisResult:
    goal_context: GoalContext
    questions: tuple[dict, ...]
    analysis_response_id: str
    clarification_response_id: str | None = None

    def as_dict(self):
        return {
            "goal_context": self.goal_context.as_dict(),
            "status": self.goal_context.disposition,
            "questions": list(self.questions),
            "analysis_response_id": self.analysis_response_id,
            "clarification_response_id": self.clarification_response_id,
        }


class GoalAnalyzer:
    """Uses separate model methods for interpretation and clarification wording."""

    def __init__(self, store, config, *, caller=None):
        self.store = store
        self.caller = caller or ModelCaller(config)

    def analyze(self, original_input, conversation=(), *, context=(), context_bundle=None):
        require(context_bundle is None or not context, "provide fragments or a context bundle, not both")
        if context_bundle is None:
            context_bundle = ContextBundle(
                ContextRequest(str(uuid.uuid4()), "planning", GoalContext.from_input(original_input)),
                tuple(context),
            )
        require(context_bundle.request.goal.original_input == original_input, "analysis context goal mismatch")
        encoded_bundle = encode_bundle(context_bundle)
        bundle = decode_bundle(encoded_bundle)
        analysis_result, analysis_id = self._call(
            "goal_analysis",
            {"original_input": original_input, "conversation": list(conversation)},
            bundle=bundle,
        )
        try:
            analysis = json.loads(analysis_result.content)
            goal = GoalContext.from_analysis(original_input, analysis)
        except Exception as exc:
            self._reject(analysis_id, exc)
            raise ContractError(
                f"goal analysis failed; evidence record {analysis_id}: {type(exc).__name__}"
            ) from exc

        self._accept(analysis_id, analysis_result, goal.as_dict())
        unresolved = bool(goal.clarification_requests) or bool(
            goal.missing_information and not goal.grounding_requests
        )
        if not unresolved:
            return GoalAnalysisResult(goal, (), analysis_id)

        question_result, question_id = self._call(
            "goal_clarification", {"goal_context": goal.as_dict()}, bundle=bundle
        )
        try:
            questions = self._validate_questions(json.loads(question_result.content))
        except Exception as exc:
            self._reject(question_id, exc)
            raise ContractError(
                f"goal clarification failed; evidence record {question_id}: {type(exc).__name__}"
            ) from exc
        self._accept(question_id, question_result, {"questions": list(questions)})
        return GoalAnalysisResult(goal, questions, analysis_id, question_id)

    def _call(self, method, arguments, *, bundle):
        key = str(uuid.uuid4())
        record = {
            "id": key,
            "model": self.caller.config.model,
            "created_at": time.time(),
            "method": method,
            "status": "requesting",
        }
        self.store.put("model_responses", key, record)
        try:
            # Use persisted JSON ordering on the first request as well as replay.
            # Clarification includes nested objects from the actual model response.
            arguments = json.loads(dumps(arguments))
            encoded_bundle = encode_bundle(bundle)
            prepared = self.caller.prepare(method, arguments, context=bundle.fragments)
            manifest = context_manifest(bundle, prepared, self.caller._renderer.version)
            record["request"] = {"messages": list(prepared.request.messages),
                                 "response_format": prepared.request.response_format,
                                 "model": self.caller.config.model}
            record.update(context_bundle_id=key, context_bundle_hash=record_hash(encoded_bundle),
                          context_manifest_id=key, context_allocation=prepared.allocation.as_dict(),
                          preparation={"method": method, "arguments": arguments},
                          session_id=bundle.request.session_id)
            with self.store.transaction():
                self.store.put("context_bundles", key, encoded_bundle)
                self.store.put("context_manifests", key, {"id": key, **manifest.as_dict()})
                self.store.put("model_responses", key, record)
            result = self.caller.send_prepared(prepared)
            # Preserve actual responses even when semantic parsing later rejects them.
            record.update(http_status=result.transport.status_code, raw=result.transport.raw,
                          elapsed_ms=result.transport.elapsed_ms, actual_model=result.actual_model,
                          response_id=result.response_id)
            self.store.put("model_responses", key, record)
            return result, key
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
                f"{method} model call failed; evidence record {key}: {type(exc).__name__}"
            ) from exc

    def _accept(self, key, result, parsed):
        record = self.store.get("model_responses", key)
        record.update(
            status="validated",
            http_status=result.transport.status_code,
            raw=result.transport.raw,
            elapsed_ms=result.transport.elapsed_ms,
            response_id=result.response_id,
            actual_model=result.actual_model,
            parsed=parsed,
        )
        self.store.put("model_responses", key, record)

    def _reject(self, key, exc):
        record = self.store.get("model_responses", key)
        record.update(status="rejected", error=type(exc).__name__ + ": " + str(exc))
        self.store.put("model_responses", key, record)

    @staticmethod
    def _validate_questions(value):
        require(isinstance(value, dict) and set(value) == {"questions"}, "invalid clarification response")
        questions = value["questions"]
        require(isinstance(questions, list) and 1 <= len(questions) <= 3, "clarification needs one to three questions")
        required = {"field", "question", "reason"}
        for item in questions:
            require(isinstance(item, dict) and set(item) == required, "invalid clarification question")
            require(
                all(isinstance(item[k], str) and bool(item[k].strip()) for k in required),
                "clarification question fields must be nonempty",
            )
        return tuple(questions)
