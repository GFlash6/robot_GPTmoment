"""Explicit call methods: each method owns task-specific prompt construction."""

from dataclasses import dataclass
import json

from .contracts import require


@dataclass(frozen=True)
class MethodPrompt:
    system_messages: tuple[dict, ...]
    user_message: dict
    response_format: dict | None = None
    temperature: float | None = None

    @property
    def base_messages(self):
        return self.system_messages + (self.user_message,)


class QuestionAnswerMethod:
    name = "qa"

    def prepare(self, arguments):
        require(isinstance(arguments, dict), "qa arguments must be an object")
        question = arguments.get("question")
        require(isinstance(question, str) and bool(question.strip()), "question required")
        instruction = arguments.get(
            "instruction", "Answer the question accurately and concisely."
        )
        require(isinstance(instruction, str) and bool(instruction), "instruction required")
        response_format = arguments.get("response_format")
        require(
            response_format is None or isinstance(response_format, dict),
            "response_format must be an object",
        )
        return MethodPrompt(
            system_messages=({"role": "system", "content": instruction},),
            user_message={"role": "user", "content": question},
            response_format=response_format,
            temperature=arguments.get("temperature"),
        )


class PlanningMethod:
    name = "planning"
    _instruction = (
        'Return only a JSON object shaped as {"steps":[...],"verification":"step_id"}. Each step has a unique id, skill from the supplied catalog, args, deps, optional retries (0..10) and fallback [{skill,args}]. '
        "verification must be a JSON string containing the id of a final independent goal-checking step that transitively depends on every other step; never return an object in verification. "
        'Use {"$ref":"dependency_id.output_field"} to reference actual direct dependency output fields. '
        "Never invent sensor observations, successful skill results, skill names or paths. Split long goals into an executable dependency DAG. "
        'If the catalog cannot express or verify the goal, return {"error":"reason"}; do not claim success.'
    )

    def prepare(self, arguments):
        require(isinstance(arguments, dict), "planning arguments must be an object")
        goal = arguments.get("goal")
        skills = arguments.get("skills")
        require(isinstance(goal, str) and bool(goal.strip()), "goal required")
        require(isinstance(skills, dict), "skill catalog required")
        return MethodPrompt(
            system_messages=({"role": "system", "content": self._instruction},),
            user_message={
                "role": "user",
                "content": json.dumps(
                    {"goal": goal, "skills": skills}, ensure_ascii=False
                ),
            },
            response_format={"type": "json_object"},
        )


class GoalAnalysisMethod:
    name = "goal_analysis"
    _instruction = (
        "Analyze the user's robot goal before planning. Return only one JSON object. "
        "Preserve uncertainty: never invent object identities, poses, observations, user preferences, or robot capabilities. "
        "Separate explicit meaning from ambiguities, missing information, assumptions, information the robot can ground through sensing, and information that requires user clarification. "
        "Use exactly these fields: interpreted_intent (string), entities (array of objects), relations (array of objects), constraints (array of strings), completion_criteria (array of strings), ambiguities (array of strings), missing_information (array of strings), assumptions (array of strings), grounding_requests (array of strings), clarification_requests (array of strings)."
    )

    def prepare(self, arguments):
        require(isinstance(arguments, dict), "goal analysis arguments must be an object")
        original_input = arguments.get("original_input")
        require(
            isinstance(original_input, str) and bool(original_input.strip()),
            "original goal input required",
        )
        conversation = arguments.get("conversation", [])
        require(isinstance(conversation, list), "conversation context must be a list")
        return MethodPrompt(
            system_messages=({"role": "system", "content": self._instruction},),
            user_message={
                "role": "user",
                "content": json.dumps(
                    {"original_input": original_input, "conversation": conversation},
                    ensure_ascii=False,
                ),
            },
            response_format={"type": "json_object"},
            temperature=0,
        )


class ClarificationMethod:
    name = "goal_clarification"
    _instruction = (
        "Generate concise clarification questions for an unresolved robot goal. Return only one JSON object shaped as "
        '{"questions":[{"field":"...","question":"...","reason":"..."}]}. '
        "Ask only questions that require the user; do not ask for information the robot can obtain through sensing or tools. "
        "Prefer one question and never return more than three. Do not answer the questions or modify the goal."
    )

    def prepare(self, arguments):
        require(isinstance(arguments, dict), "clarification arguments must be an object")
        goal_context = arguments.get("goal_context")
        require(isinstance(goal_context, dict), "goal context required")
        return MethodPrompt(
            system_messages=({"role": "system", "content": self._instruction},),
            user_message={
                "role": "user",
                "content": json.dumps(goal_context, ensure_ascii=False),
            },
            response_format={"type": "json_object"},
            temperature=0,
        )


DEFAULT_METHODS = {
    QuestionAnswerMethod.name: QuestionAnswerMethod(),
    PlanningMethod.name: PlanningMethod(),
    GoalAnalysisMethod.name: GoalAnalysisMethod(),
    ClarificationMethod.name: ClarificationMethod(),
}
