"""Authenticated loopback action transport, separate from the read-only observer."""

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import secrets

from .actions import Actions, ActionError, Principal, action_catalog
from .contracts import ContractError, require
from .store import Store


def make_server(root, credentials, port=8768, static=None):
    """credentials maps actual bearer tokens to server-configured principals."""
    require(bool(credentials) and all(isinstance(k, str) and k for k in credentials), "action credentials required")
    from robot_agent_observer.server import make_server as observer_server
    server = observer_server(root, port=port, static=static)
    parent = server.RequestHandlerClass

    class Handler(parent):
        def log_message(self, *_):
            pass

        def reply(self, status, body):
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def authenticate(self):
            hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in hosts or self.headers.get("Origin") not in (
                None, *("http://" + h for h in hosts)
            ):
                raise ActionError("FORBIDDEN", "request origin denied")
            auth = self.headers.get("Authorization", "")
            for token, principal in credentials.items():
                if secrets.compare_digest(auth.encode(), ("Bearer " + token).encode()):
                    return replace(principal, source="http")
            raise ActionError("UNAUTHENTICATED", "valid action credential required")

        def do_GET(self):
            if self.path != "/actions":
                return super().do_GET()
            try:
                principal = self.authenticate()
                if self.path != "/actions":
                    return self.reply(404, {"error": {"code": "NOT_FOUND", "message": "unknown route"}})
                self.reply(200, {"catalog_version": 1, "actions": action_catalog(principal)})
            except ActionError as exc:
                self.reply(401 if exc.code == "UNAUTHENTICATED" else 403,
                           {"error": {"code": exc.code, "message": str(exc)}})

        def do_POST(self):
            try:
                principal = self.authenticate()
                if not self.path.startswith("/actions/"):
                    raise ActionError("NOT_FOUND", "unknown route")
                require(self.headers.get_content_type() == "application/json", "JSON body required")
                require(not self.headers.get("Transfer-Encoding"), "chunked request bodies unsupported")
                length = int(self.headers.get("Content-Length", "0"))
                require(0 < length <= 1024 * 1024, "request body exceeds limit or is empty")
                self.connection.settimeout(15)
                args = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
                store = Store(root)
                try:
                    result = Actions(store).call(self.path.removeprefix("/actions/"), args, principal,
                        request_id=self.headers.get("X-Request-ID"), idempotency_key=self.headers.get("Idempotency-Key"))
                finally:
                    store.close()
                self.reply(202 if result["result"].get("status") == "accepted" else 200, result)
            except ActionError as exc:
                status = {"UNAUTHENTICATED": 401, "FORBIDDEN": 403, "NOT_FOUND": 404,
                          "STALE_TASK": 409, "IDEMPOTENCY_CONFLICT": 409}.get(exc.code, 400)
                self.reply(status, {"error": {"code": exc.code, "message": str(exc)}})
            except (ContractError, ValueError, TimeoutError) as exc:
                self.reply(400, {"error": {"code": "INVALID_ARGUMENT", "message": str(exc)}})
            except Exception:
                self.reply(500, {"error": {"code": "INTERNAL_ERROR", "message": "action failed; inspect the local ledger"}})

    server.RequestHandlerClass = Handler
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".runtime")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--static", help="built UI directory")
    parser.add_argument("--auth-config", required=True, help="JSON principals with token_env, subject, permissions and robots")
    args = parser.parse_args(argv)
    config = json.loads(Path(args.auth_config).read_text())
    credentials = {}
    for item in config["principals"]:
        token = os.environ.get(item["token_env"])
        require(bool(token), "action credential environment variable missing")
        require(token not in credentials, "duplicate action credential")
        credentials[token] = Principal(item["subject"], frozenset(item["permissions"]), frozenset(item["robots"]), "http")
    server = make_server(args.root, credentials, args.port, args.static)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
