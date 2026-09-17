"""Operator CLI; no built-in model answers or robot success responses."""

import argparse
import json
import sys
import time
from pathlib import Path
from .store import Store
from .runtime import Runtime
from .memory import Memory
from .contracts import ContractError


def read_json(path):
    return json.loads(Path(path).read_text())


def parser():
    p = argparse.ArgumentParser(description="Robot task and evidence framework")
    p.add_argument("--root", default=".runtime", help="persistent state directory")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--allow-read", action="append", required=True)
    reg = sub.add_parser("register")
    reg.add_argument("name")
    reg.add_argument("spec")
    cap = sub.add_parser("capacity")
    cap.add_argument("name")
    cap.add_argument("units", type=int)
    submit = sub.add_parser("submit")
    submit.add_argument("plan")
    submit.add_argument("--robot", required=True)
    submit.add_argument("--priority", type=int, default=0)
    for cmd in ("status", "events", "pause", "cancel", "resume", "preempt"):
        sub.add_parser(cmd).add_argument("task")
    sub.add_parser("tasks")
    sub.add_parser("skills")
    sub.add_parser("leases")
    serve = sub.add_parser("serve-skills")
    serve.add_argument("--port", type=int, default=8088)
    runner = sub.add_parser("run")
    runner.add_argument("--until")
    agent = sub.add_parser("agent")
    agent.add_argument("goal")
    agent.add_argument("--robot", required=True)
    agent.add_argument("--model-config", required=True)
    agent.add_argument("--priority", type=int, default=0)
    agent.add_argument("--max-replans", type=int, default=0)
    analyze = sub.add_parser("analyze-goal")
    analyze.add_argument("goal")
    analyze.add_argument("--model-config", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("goal")
    plan.add_argument("--model-config", required=True)
    plan.add_argument("--context")
    replan = sub.add_parser("replan")
    replan.add_argument("task")
    replan.add_argument("--plan")
    replan.add_argument("--model-config")
    replan.add_argument("--goal")
    assets = sub.add_parser("assets")
    assets.add_argument("--kind")
    assets.add_argument("--robot")
    assets.add_argument("--frame")
    assets.add_argument("--start-ns", type=int)
    assets.add_argument("--end-ns", type=int)
    assets.add_argument("--version")
    ingest = sub.add_parser("ingest")
    ingest.add_argument("path")
    ingest.add_argument("metadata")
    verify = sub.add_parser("verify-asset")
    verify.add_argument("asset")
    remember = sub.add_parser("remember")
    remember.add_argument("kind")
    remember.add_argument("text")
    remember.add_argument("--attributes", required=True)
    remember.add_argument("--evidence", nargs="+", required=True)
    search = sub.add_parser("search")
    search.add_argument("text")
    search.add_argument("--kind")
    search.add_argument("--robot")
    record = sub.add_parser("record-file")
    record.add_argument("path")
    record.add_argument("output")
    record.add_argument("--topic", required=True)
    record.add_argument("--encoding", required=True)
    record.add_argument("--metadata", required=True)
    record.add_argument("--publish-time", type=int, required=True)
    sub.add_parser("inspect-recording").add_argument("path")
    sub.add_parser("ros-topics")
    ros = sub.add_parser("record-ros")
    ros.add_argument("output")
    ros.add_argument("--topics", nargs="+", required=True)
    ros.add_argument("--duration", type=float, required=True)
    ros.add_argument("--robot", required=True)
    ros.add_argument("--storage", choices=["sqlite3", "mcap"], default="sqlite3")
    ros.add_argument("--use-sim-time", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    store = Store(args.root)
    rt = Runtime(store)
    memory = Memory(store)
    try:
        cmd = args.command
        if cmd == "init":
            rt.install_local_skills([str(Path(p).resolve()) for p in args.allow_read])
            result = {"root": str(store.root), "skills": list(rt.catalog())}
        elif cmd == "register":
            rt.register(args.name, read_json(args.spec))
            result = {"registered": args.name}
        elif cmd == "capacity":
            store.set_capacity(args.name, args.units)
            result = {"resource": args.name, "capacity": args.units}
        elif cmd == "submit":
            result = rt.submit(read_json(args.plan), args.robot, args.priority)
        elif cmd == "status":
            result = store.get("tasks", args.task)
            if result is None:
                raise ContractError("unknown task")
        elif cmd == "events":
            result = store.events(args.task)
        elif cmd == "tasks":
            result = store.list("tasks")
        elif cmd == "skills":
            result = rt.catalog()
        elif cmd == "leases":
            result = store.leases()
        elif cmd in {"pause", "cancel"}:
            rt.interrupt(args.task, cmd)
            result = {"task": args.task, "requested": cmd, "confirmed_stopped": False}
        elif cmd == "resume":
            result = rt.resume(args.task)
        elif cmd == "preempt":
            result = {
                "pause_requested": rt.preempt(args.task),
                "confirmed_stopped": False,
            }
        elif cmd == "serve-skills":
            from .service import skill_server

            server = skill_server(store, port=args.port)
            try:
                server.serve_forever()
            finally:
                server.server_close()
            result = {"stopped": True}
        elif cmd == "run":
            from .durable import run

            result = run(store.root, args.until)
        elif cmd == "agent":
            result = rt.submit_goal(
                args.goal,
                args.robot,
                read_json(args.model_config),
                args.priority,
                args.max_replans,
            )
        elif cmd == "analyze-goal":
            result = rt.analyze_goal(
                args.goal,
                read_json(args.model_config),
            ).as_dict()
        elif cmd == "plan":
            from .planner import Planner

            result = Planner(store, read_json(args.model_config)).plan(
                args.goal,
                rt.catalog(),
                read_json(args.context) if args.context else None,
            )
        elif cmd == "replan":
            if args.plan:
                body = read_json(args.plan)
            else:
                from .planner import Planner

                if not args.model_config or not args.goal:
                    raise ContractError(
                        "replan needs --plan or actual --model-config and --goal"
                    )
                task = store.get("tasks", args.task)
                body = Planner(store, read_json(args.model_config)).plan(
                    args.goal, rt.catalog(), task
                )
            result = rt.revise(args.task, body)
        elif cmd == "assets":
            result = memory.query_assets(
                args.kind,
                args.robot,
                args.frame,
                args.start_ns,
                args.end_ns,
                args.version,
            )
        elif cmd == "ingest":
            result = memory.ingest(args.path, read_json(args.metadata))
        elif cmd == "verify-asset":
            result = {
                "asset_id": args.asset,
                "size": len(memory.read(args.asset)),
                "verified": True,
            }
        elif cmd == "remember":
            result = memory.remember(
                args.kind, args.text, read_json(args.attributes), args.evidence
            )
        elif cmd == "search":
            result = memory.search(args.text, args.kind, args.robot)
        elif cmd == "record-file":
            from .recording import Recorder

            data = Path(args.path).read_bytes()
            with Recorder(args.output) as recorder:
                recorder.append(
                    args.topic,
                    args.encoding,
                    data,
                    args.publish_time,
                    time.time_ns(),
                    read_json(args.metadata),
                )
            result = {"path": str(Path(args.output).resolve()), "bytes": len(data)}
        elif cmd == "ros-topics":
            from .ros_recording import discover

            result = discover()
        elif cmd == "record-ros":
            from .ros_recording import record

            result = record(
                args.topics,
                args.output,
                args.duration,
                args.robot,
                args.storage,
                args.use_sim_time,
            )
        elif cmd == "inspect-recording":
            from .recording import messages

            result = [
                {k: v for k, v in x.items() if k not in {"data", "schema"}}
                | {"bytes": len(x["data"])}
                for x in messages(args.path)
            ]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return (
            0 if not isinstance(result, dict) or result.get("status") != "failed" else 1
        )
    except KeyboardInterrupt:
        print(
            "Worker interrupted; external stop is not confirmed. Restart and reconcile active executions.",
            file=sys.stderr,
        )
        return 130
    except Exception as exc:
        print(
            json.dumps(
                {"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
