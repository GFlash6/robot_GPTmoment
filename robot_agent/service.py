"""Loopback HTTP service for actual built-in data skills.

Robot integrations implement the same execution envelope at their own endpoint.
This service never fabricates robot observations or exposes arbitrary commands.
"""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .contracts import ContractError, require, schema_check, check_terminal
from .context_memory import record_hash
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
                r"/executions/([A-Za-z0-9_-]{1,128})(/cancel|/reconcile)?", self.path
            )
            if match is None:
                self.reply(404, {"error": "unknown route"})
                return
            execution_id = match.group(1)
            try:
                # Keep authority acceptance and synchronous local side effects
                # serialized across threads and service processes sharing this ledger.
                with store.lock, store.task_lock('service-execution-authority'):
                    request = store.get("service_requests", execution_id)
                    new_execution = False
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
                            new_execution = True
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
                    domain = request['spec'].get('fencing_domain')
                    current_spec = Runtime(store).catalog().get(body['skill'])
                    require(current_spec is not None and current_spec.get('fencing_domain') == domain,
                            'execution fencing configuration changed')
                    authority = body.get('authority')
                    if domain:
                        from .fencing import validate_authority, accept, domain_key
                        validate_authority(authority, domain)
                        supplied = json.loads(self.headers.get('X-Execution-Authority', 'null'))
                        validate_authority(supplied, domain)
                        if match.group(2) == '/reconcile':
                            current = store.get('service_authorities', domain_key(body['robot_id'], domain))
                            require(current is not None and current['token'] == supplied['token']
                                    and current['token'] > authority['token'],
                                    'reconciliation requires current newer authority')
                            saved = store.get('service_reconciliations', execution_id)
                            if saved is None:
                                require(request['spec'].get('cancelable', False), 'execution is not cancelable')
                                # Only a real local cancellation/result may certify stopping.
                                # No caller-provided terminal result is accepted.
                                result = Skills(store).call('cancel', body['skill'], request['spec'],
                                    execution_id, body['args'], body['robot_id'])
                                check_terminal(result, execution_id)
                                result = {**result, 'authority': authority,
                                    'reconciliation': {'controller_execution_id': current['execution_id'],
                                                       'authority': supplied}}
                                saved = {'request_hash': record_hash(body), 'result': result}
                                store.put('service_reconciliations', execution_id, saved)
                            require(saved['request_hash'] == record_hash(body), 'reconciled execution request changed')
                            self.reply(200, saved['result'])
                            return
                        require(supplied == authority, 'execution authority header mismatch')
                        # A reconciled historical result is read-only, even for a
                        # pending old cancel. Never poll Skills here: polling copies bytes.
                        saved = store.get('service_reconciliations', execution_id)
                        if saved is not None and self.command in {'GET', 'POST'}:
                            require(saved['request_hash'] == record_hash(body), 'reconciled execution request changed')
                            check_terminal(saved['result'], execution_id)
                            self.reply(200, saved['result'])
                            return
                    else:
                        require(match.group(2) != '/reconcile', 'reconciliation requires a fenced execution')
                        require(authority is None and self.headers.get('X-Execution-Authority') is None,
                                'endpoint skill does not support execution authority')
                    with store.transaction():
                        if domain:
                            accept(store, body['robot_id'], execution_id, authority, new_execution=new_execution)
                        if new_execution:
                            store.put('service_requests', execution_id, request)
                    result = Skills(store).call(
                        operation,
                        body["skill"],
                        request["spec"],
                        execution_id,
                        body["args"],
                        body["robot_id"],
                    )
                    if domain:
                        result = {**result, 'authority': authority}
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
