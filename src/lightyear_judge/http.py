"""Authenticated loopback-only JSON RPC. No file-serving or process-management routes."""

import hmac
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from lightyear_toolkit.workspace import ARTIFACT_LIMIT

MAX_BODY = ARTIFACT_LIMIT * 4 // 3 + 4096


def create_server(judge, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No raw URLs, diagnostics, tokens or submitted values in logs.

        def reply(self, status, value):
            body = json.dumps(value, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.connection.settimeout(10)
            if not hmac.compare_digest(
                self.headers.get("Authorization", ""), "Bearer " + judge.token
            ):
                with judge.lock:
                    judge.append("unauthorized")
                return self.reply(401, {"ok": False, "error": "unauthorized"})
            try:
                if (
                    self.headers.get("Transfer-Encoding")
                    or self.headers.get("Content-Type") != "application/json"
                    or len(self.headers.get_all("Content-Length", [])) != 1
                ):
                    raise ValueError()
                size = int(self.headers.get("Content-Length", "-1"))
                if not 0 <= size <= MAX_BODY:
                    raise ValueError()

                def unique(items):
                    out = {}
                    for key, value in items:
                        if key in out:
                            raise ValueError()
                        out[key] = value
                    return out

                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError()
                args = json.loads(
                    raw,
                    object_pairs_hook=unique,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
                )
                result = judge.invoke(self.path.removeprefix("/"), args)
                return self.reply(200, result)
            except Exception:
                with judge.lock:
                    judge.append("invalid-http-request")
                return self.reply(400, {"ok": False, "error": "request-refused"})

        def do_GET(self):
            with judge.lock:
                judge.append("invalid-http-request")
            self.reply(405, {"ok": False, "error": "method-refused"})

    # Serial requests avoid concurrent evaluation and state side channels.
    return HTTPServer(("127.0.0.1", port), Handler)
