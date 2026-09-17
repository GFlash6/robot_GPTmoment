"""Loopback HTTP service for actual built-in data skills.

Robot integrations implement the same execution envelope at their own endpoint.
This service never fabricates robot observations or exposes arbitrary commands.
"""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .contracts import ContractError, require, schema_check
from .runtime import Runtime
from .skills import Skills


def skill_server(store, host="127.0.0.1", port=0):
    require(host in {"127.0.0.1", "localhost"}, "local data service must bind loopback")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            # Requests may contain local paths; avoid incidental access-log disclosure.
            return

        def handle_request(self):
            match = re.fullmatch(
                r"/executions/([A-Za-z0-9_-]{1,128})(/cancel)?", self.path
            )
            if match is None:
                self.reply(404, {"error": "unknown route"})
                return
            execution_id = match.group(1)
            try:
                with store.lock:
                    request = store.get("service_requests", execution_id)
                    if self.command == "PUT" and not match.group(2):
                        size = int(self.headers.get("Content-Length", "0"))
                        require(0 < size <= 1048576, "body must be 1..1048576 bytes")
                        body = json.loads(self.rfile.read(size))
                        require(
                            isinstance(body, dict)
                            and body.get("execution_id") == execution_id,
                            "execution identity mismatch",
                        )
                        require(
                            isinstance(body.get("robot_id"), str) and body["robot_id"],
                            "robot_id required",
                        )
                        if request is not None:
                            require(
                                request["body"] == body,
                                "execution ID already used for different request",
                            )
                            operation = "query"
                        else:
                            spec = Runtime(store).catalog().get(body.get("skill"))
                            require(
                                spec is not None and spec["adapter"] == "local",
                                "service accepts only registered local data skills",
                            )
                            schema_check(spec["input_schema"], body.get("args"))
                            request = {"body": body, "spec": spec}
                            store.put("service_requests", execution_id, request)
                            operation = "start"
                    elif self.command in {"GET", "POST"}:
                        if request is None:
                            self.reply(404, {"error": "execution not found"})
                            return
                        require(
                            (self.command == "POST") == bool(match.group(2)),
                            "invalid execution operation",
                        )
                        operation = "cancel" if self.command == "POST" else "query"
                    else:
                        raise ContractError("unsupported method")
                    body = request["body"]
                    result = Skills(store).call(
                        operation,
                        body["skill"],
                        request["spec"],
                        execution_id,
                        body["args"],
                        body["robot_id"],
                    )
                    self.reply(200, result)
            except (ValueError, ContractError) as exc:
                self.reply(409, {"error": type(exc).__name__, "message": str(exc)})
            except Exception as exc:
                self.reply(500, {"error": type(exc).__name__})

        def reply(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_PUT = handle_request
        do_GET = handle_request
        do_POST = handle_request

    return ThreadingHTTPServer((host, port), Handler)
