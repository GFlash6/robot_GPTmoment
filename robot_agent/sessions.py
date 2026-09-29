"""Persistent operator conversations and version-bound planning drafts."""

import time
import uuid

from .contracts import ContractError, require
from .context_models import ContextRequest, GoalContext
from .goal_analysis import GoalAnalyzer
from .planner import Planner
from .model_transport import environment_config


class Sessions:
    def __init__(self, actions):
        self.actions = actions
        self.store = actions.store

    def get(self, session_id, principal):
        from .actions import ActionError
        session = self.store.get("sessions", session_id)
        if session is None:
            raise ActionError("NOT_FOUND", "unknown session")
        principal.check("planning.use", session["robot_id"])
        if session["subject"] != principal.subject:
            raise ActionError("FORBIDDEN", "session belongs to another operator")
        if session.get("memory_bindings"):
            principal.check("memory.read", session["robot_id"])
            principal.check("assets.read", session["robot_id"])
        return session

    def check_revision(self, session, args):
        from .actions import ActionError
        if session["revision"] != args["expected_revision"]:
            raise ActionError("STALE_SESSION", "session changed; reload before continuing")

    def call(self, name, args, principal, record):
        from .actions import fingerprint, ActionError
        if name == "session.create":
            principal.check("planning.use", args["robot_id"])
            require("/" not in args["robot_id"], "invalid robot namespace")
            session_id = str(uuid.uuid4())
            turn = {"id": str(uuid.uuid4()), "role": "user", "content": args["goal"], "created_at": time.time()}
            session = {"id": session_id, "subject": principal.subject, "robot_id": args["robot_id"],
                       "original_input": args["goal"], "revision": 0, "created_at": time.time(),
                       "turns": [turn], "analysis": None, "selection": None, "task_ids": [], "asset_ids": [],
                       "priority": args.get("priority", 0), "max_replans": args.get("max_replans", 0)}
            self.store.put("sessions", session_id, session)
            return {"session": session}
        session = self.get(args["session_id"], principal)
        if name == "session.get":
            from .session_history import history_view
            summary, summary_error = None, None
            try:
                _, summary = history_view(self.store, session)
            except ContractError as exc:
                # Keep original turns available so an operator can inspect and regenerate.
                summary_error = str(exc)
            return {"session": session, "summary": summary, "summary_error": summary_error,
                "drafts": [d for d in self.store.list("plan_drafts") if d["session_id"] == session["id"]]}
        self.check_revision(session, args)
        if name == "session.completion-contract":
            from .completion import validate_contract
            contract = validate_contract(args["contract"], self.actions.runtime.catalog())
            with self.store.transaction():
                current = self.get(session["id"], principal)
                self.check_revision(current, args)
                current.update(completion_contract=contract, revision=current["revision"] + 1, analysis=None)
                self.store.put("sessions", current["id"], current)
            return {"session": current}
        if name == "session.attach-memories":
            from .context_memory import record_hash, resolve_memory
            principal.check("memory.read", session["robot_id"])
            principal.check("assets.read", session["robot_id"])
            bindings = args["memories"]
            require(len({b["memory_id"] for b in bindings}) == len(bindings), "duplicate memory binding")
            with self.store.transaction():
                current = self.get(session["id"], principal)
                self.check_revision(current, args)
                for binding in bindings:
                    item, _ = resolve_memory(self.store, binding["memory_id"], session["robot_id"])
                    require(record_hash(item) == binding["record_hash"], "retrieved memory changed; search again")
                current.update(memory_bindings=bindings, revision=current["revision"] + 1, analysis=None)
                self.store.put("sessions", current["id"], current)
            return {"session": current}
        if name == "session.attach-assets":
            from .context_assets import bind_assets
            with self.store.transaction():
                current = self.get(session["id"], principal)
                self.check_revision(current, args)
                for asset_id in args["asset_ids"]:
                    self.actions.query("asset.get", {"asset_id": asset_id}, principal)
                bindings = bind_assets(self.store, args["asset_ids"], current["robot_id"])
                current.update(asset_ids=args["asset_ids"], asset_bindings=bindings,
                               revision=current["revision"] + 1, analysis=None)
                self.store.put("sessions", current["id"], current)
            return {"session": current}
        if name == "session.message":
            with self.store.transaction():
                session = self.get(session["id"], principal)
                self.check_revision(session, args)
                session["turns"].append({"id": str(uuid.uuid4()), "role": "user", "content": args["content"], "created_at": time.time()})
                session["revision"] += 1
                session["analysis"] = None
                self.store.put("sessions", session["id"], session)
            return {"session": session}
        if name == "selection.set":
            task = self.actions.task(args["task_id"], principal)
            require(task["robot_id"] == session["robot_id"], "selection robot mismatch")
            require(task["revision"] == args["task_revision"] and task["generation"] == args["task_generation"], "stale task selection")
            require(all(x in task["steps"] for x in args["step_ids"]), "unknown selected step")
            with self.store.transaction():
                current = self.get(session["id"], principal)
                self.check_revision(current, args)
                current["selection"] = {"id": str(uuid.uuid4()), "task_id": task["id"],
                    "revision": task["revision"], "generation": task["generation"],
                    "step_ids": args["step_ids"], "captured_at": time.time(), "expires_at": time.time() + 300}
                current["revision"] += 1
                current["analysis"] = None
                self.store.put("sessions", current["id"], current)
            return {"session": current}
        if name == "session.context-policy":
            policy = {**session.get("context_policy", {}), "auto_summary": args["auto_summary"],
                "keep_recent": args.get("keep_recent", session.get("context_policy", {}).get("keep_recent", 6))}
            if "pinned_turn_ids" in args:
                require(set(args["pinned_turn_ids"]) <= {t["id"] for t in session["turns"]}, "unknown pinned turn")
                policy["pinned_turn_ids"] = args["pinned_turn_ids"]
            with self.store.transaction():
                current = self.get(session["id"], principal)
                self.check_revision(current, args)
                current.update(context_policy=policy, revision=current["revision"] + 1, analysis=None)
                self.store.put("sessions", current["id"], current)
            return {"session": current}
        if name == "session.summarize":
            from .session_history import summarize
            from .context_memory import record_hash
            prior = session.get("history_summary")
            previous = self.store.get("session_summaries", prior["id"]) if prior else None
            pinned = args.get("pinned_turn_ids", session.get("context_policy", {}).get("pinned_turn_ids", previous["pinned_turn_ids"] if previous else []))
            summary = summarize(self.actions, session, record, args.get("keep_recent", session.get("context_policy", {}).get("keep_recent", 6)), pinned)
            with self.store.transaction():
                current = self.get(session["id"], principal)
                self.check_revision(current, args)
                current.update(history_summary={"id": summary["id"], "record_hash": record_hash(summary)},
                    revision=current["revision"] + 1, analysis=None)
                self.store.put("sessions", current["id"], current)
            return {"session": current, "summary": summary}
        if name == "goal.analyze":
            from .context_builder import ContextBuilder
            request = ContextRequest(request_id=record["request_id"], phase="planning",
                goal=GoalContext.from_input(session["original_input"]), robot_id=session["robot_id"], session_id=session["id"])
            from .session_budget import fit_session
            session, context = fit_session(self.actions, session, request, self.actions.runtime.catalog(),
                "goal_analysis", {"original_input": session["original_input"], "conversation": []}, record)
            result = GoalAnalyzer(self.store, self.actions.model_config or environment_config()).analyze(
                session["original_input"], [], context_bundle=context)
            with self.store.transaction():
                current = self.get(session["id"], principal)
                self.check_revision(current, args)
                current["revision"] += 1
                if session.get("history_summary"):
                    current["history_summary"] = session["history_summary"]
                current["analysis"] = result.as_dict()
                current["analysis_revision"] = current["revision"]
                current["turns"].append({"id": str(uuid.uuid4()), "role": "assistant",
                    "content": result.goal_context.interpreted_intent + "\n" + "\n".join(q["question"] for q in result.questions),
                    "analysis_response_id": result.analysis_response_id, "created_at": time.time()})
                self.store.put("sessions", current["id"], current)
            return {"session": current}
        if name == "plan.propose":
            analysis = session.get("analysis")
            require(analysis is not None and session.get("analysis_revision") == session["revision"], "analyze the current session before planning")
            require(analysis["status"] == "ready" or (
                analysis["status"] == "needs_grounding" and analysis["goal_context"]["grounding_requests"]
                and not analysis["questions"]
            ), "goal still needs operator clarification")
            parsed = {k: v for k, v in analysis["goal_context"].items() if k not in {"original_input", "disposition"}}
            goal = GoalContext.from_analysis(session["original_input"], parsed)
            selection = session.get("selection")
            task = self.actions.task(selection["task_id"], principal) if selection else None
            if task:
                from .completion import same_contract, task_contract
                require(same_contract(session.get("completion_contract"), task_contract(task)),
                        "session completion contract differs from accepted task; use matching contract or a new task")
            request = ContextRequest(request_id=record["request_id"], phase="replanning" if task else "planning",
                goal=goal, robot_id=session["robot_id"], session_id=session["id"],
                task_id=task["id"] if task else None, revision=task["revision"] if task else 0,
                generation=task["generation"] if task else 0)
            catalog = self.actions.runtime.catalog()
            from .context_builder import ContextBuilder
            from .session_budget import fit_session
            session, _ = fit_session(self.actions, session, request, catalog, "planning",
                {"goal": goal.interpreted_intent, "skills": ContextBuilder.capabilities(catalog)}, record)
            planner = Planner(self.store, self.actions.model_config or environment_config())
            plan = planner.plan(goal.interpreted_intent, catalog, context_request=request, context_session=session)
            self.actions.runtime._check_plan(plan, catalog, session["robot_id"], session.get("completion_contract"))
            with self.store.transaction():
                current = self.get(session["id"], principal)
                self.check_revision(current, args)
                from .context_assets import verify_session_assets
                verify_session_assets(self.store, current)
                if task:
                    latest = self.actions.task(task["id"], principal)
                    require((latest["revision"], latest["generation"]) == (task["revision"], task["generation"]), "task changed during planning")
                    control = self.store.get("controls", task["id"])
                    require(not control or control["mode"] != "cancel", "task cancellation takes precedence")
                if session.get("history_summary") != current.get("history_summary"):
                    current["history_summary"] = session["history_summary"]
                    current["revision"] += 1
                    # Analysis used these original messages; compression adds no new operator input.
                    current["analysis_revision"] = current["revision"]
                    self.store.put("sessions", current["id"], current)
                    session = current
                draft = {"id": str(uuid.uuid4()), "session_id": session["id"], "session_revision": session["revision"],
                    "turn_id": session["turns"][-1]["id"], "action_call_id": record["id"], "robot_id": session["robot_id"],
                    "plan": plan, "plan_hash": fingerprint(plan), "catalog_hash": fingerprint(catalog),
                    "model_response_id": planner.last_response_id, "created_at": time.time(),
                    "expires_at": min(time.time() + 300, selection["expires_at"]) if selection else time.time() + 300,
                    "task_id": task["id"] if task else None, "task_revision": task["revision"] if task else None,
                    "task_generation": task["generation"] if task else None}
                draft["memory_bindings"] = session.get("memory_bindings", [])
                from .context_snapshot import create_snapshot
                from .context_memory import record_hash
                snapshot = create_snapshot(self.store, session, goal, draft["catalog_hash"])
                snapshot_id = snapshot["id"]
                draft["context_snapshot_id"] = snapshot_id
                draft["context_snapshot_hash"] = record_hash(snapshot)
                self.store.put("plan_drafts", draft["id"], draft)
            return {"draft": draft, "session": session}
        if name == "plan.submit":
            with self.store.transaction():
                session = self.get(session["id"], principal)
                self.check_revision(session, args)
                draft = self.store.get("plan_drafts", args["draft_id"])
                require(draft is not None and draft["session_id"] == session["id"], "unknown session draft")
                require(draft["session_revision"] == session["revision"], "draft session is stale")
                from .context_memory import verify_bindings
                verify_bindings(self.store, draft.get("memory_bindings", []), session["robot_id"])
                require(draft.get("expires_at", 0) > time.time(), "draft expired or predates expiry tracking; generate a fresh plan")
                require(draft["plan_hash"] == args["plan_hash"] == fingerprint(draft["plan"]), "draft content changed")
                require(draft["catalog_hash"] == fingerprint(self.actions.runtime.catalog()), "draft skill catalog is stale")
                from .context_snapshot import read_snapshot
                snapshot = read_snapshot(self.store, draft.get("context_snapshot_id"), robot_id=session["robot_id"],
                                         session_id=session["id"], catalog_hash=draft["catalog_hash"],
                                         expected_hash=draft.get("context_snapshot_hash"))
                require(snapshot["session"]["revision"] == draft["session_revision"], "draft snapshot revision mismatch")
                from .context_assets import verify_session_assets
                verify_session_assets(self.store, snapshot["session"])
                if draft["task_id"]:
                    name = "task.revise"
                    body = {"task_id": draft["task_id"], "expected_revision": draft["task_revision"],
                            "expected_generation": draft["task_generation"], "plan": draft["plan"]}
                else:
                    name = "task.submit"
                    body = {"robot_id": session["robot_id"], "plan": draft["plan"], "goal": session["original_input"],
                            "priority": session.get("priority", 0)}
                    if snapshot["session"].get("completion_contract") is not None:
                        body["completion_contract"] = snapshot["session"]["completion_contract"]
                principal.check("tasks.control" if draft["task_id"] else "tasks.submit", session["robot_id"])
                receipt = self.actions.enqueue(name, body, principal, "draft:" + draft["id"], record)
                command = self.store.get("commands", receipt["command_id"])
                command["lineage"] = {"session_id": session["id"], "turn_id": draft["turn_id"],
                    "draft_id": draft["id"], "model_response_id": draft["model_response_id"]}
                command["expires_at"] = draft["expires_at"]
                command["memory_bindings"] = draft.get("memory_bindings", [])
                command["context_snapshot_id"] = draft.get("context_snapshot_id")
                command["context_snapshot_hash"] = draft.get("context_snapshot_hash")
                if session.get("max_replans", 0):
                    config = self.actions.model_config or environment_config()
                    command["agent_context"] = {"max_replans": session["max_replans"], "replans": 0,
                        "model_response_id": draft["model_response_id"], "model_config": {
                            k: v for k, v in config.items() if k in {"endpoint", "model", "token_env", "timeout", "max_input_tokens", "max_output_tokens"}}}
                self.store.put("commands", command["id"], command)
                if receipt["task_id"] not in session["task_ids"]:
                    session["task_ids"].append(receipt["task_id"])
                self.store.put("sessions", session["id"], session)
            return receipt
        if name == "task.explain":
            from .explanation import explain_selection
            return explain_selection(self.actions, session, record, args["question"])
        raise ActionError("NOT_FOUND", "unknown session action")
