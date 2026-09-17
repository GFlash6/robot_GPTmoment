"""Preliminary model analysis and user-question generation for raw goals."""

from dataclasses import dataclass
import json
import time
import uuid

from .context_models import GoalContext
from .contracts import ContractError, require
from .model_call import ModelCaller
from .model_transport import ModelCallError


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

    def analyze(self, original_input, conversation=()):
        analysis_result, analysis_id = self._call(
            "goal_analysis",
            {"original_input": original_input, "conversation": list(conversation)},
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
            "goal_clarification", {"goal_context": goal.as_dict()}
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

    def _call(self, method, arguments):
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
            return self.caller.call(method, arguments), key
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
