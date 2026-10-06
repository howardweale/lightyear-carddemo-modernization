"""Loopback-only console transport. Closed route table; no engine-control routes."""

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .decisions import DecisionConflict, DecisionUnauthorized, canonical
from .requests import identifier
from .campaign_observer import CampaignRegistry
from .features import feature

SOCKET_TIMEOUT = 5

READ_ROUTES = frozenset(
    {
        "queue",
        "item",
        "history",
        "proof",
        "rules",
        "catalogue",
        "campaigns",
        "campaign",
        "workspace",
        "export",
        "validation",
        "events",
        "arrivals",
        "knowledge",
    }
)
WRITE_ROUTES = frozenset({"review", "decide", "propose", "logout"})


class ConsoleAPI:
    def __init__(self, service):
        self.service = service
        self.carddemo = None
        if service.scope == "carddemo-zos":
            from .carddemo_console import CarddemoAPI

            self.carddemo = CarddemoAPI(service)
            return
        self.campaigns = CampaignRegistry(service.root, service.scope)
        workflows = feature("workflows")
        workspace = feature("workspace")
        self.workflows = workflows.WorkflowValidation(service) if workflows else None
        self.workspace = workspace.Workspace(service) if workspace else None

    def read(self, route, token, args):
        if self.carddemo:
            if route == "knowledge":
                self.service._read_access(token)
                return {"available": False}
            return self.carddemo.read(route, token, args)
        s = self.service
        if route == "workspace":
            if self.workspace:
                return self.workspace.view(token)
            s._read_access(token)
            return {"scope": s.scope, "configured": False}
        s._read_access(token)
        if route == "knowledge":
            from .knowledge_status import read_status
            return read_status(s.root,s.scope)
        if route == "arrivals":
            return {"scope": s.scope, "available": False, "arrivals": []}
        if route == "queue":
            result = s.queue(token)
            if self.workflows:
                with s.connect() as db:
                    events = s.events(db)
                    for item in result["items"]:
                        if item.get("status") == "invalid" or item.get("kind") not in {
                            "rule-technical-review",
                            "rule-approval",
                            "rule-retirement",
                            "qualification-acceptance",
                        }:
                            continue
                        try:
                            item["validation"] = self.workflows.inspect(item, events)
                        except (ValueError, KeyError, OSError):
                            item["validation"] = {
                                "passed": False,
                                "reason_code": "required-evidence-validation-unavailable-or-failed",
                            }
                from .workflows import rule_register

                for row in rule_register(s, token)["rules"]:
                    if row["review_due"]:
                        result["items"].append(
                            {
                                "id": "review-due-" + row["approval_sha256"],
                                "scope": s.scope,
                                "kind": "rule-retirement",
                                "status": "review due",
                                "summary": "Rule review due: " + row["rule"]["title"],
                                "decidable": False,
                                "required_roles": ["business-owner"],
                                "bound": {},
                                "next_action": "Submit a renewal or retirement request bound to the authenticated rule proposal",
                            }
                        )
            return result
        if route == "item":
            return s.item(token, identifier(args["id"]))
        if route == "history":
            return s.export_session(token)
        if route == "proof":
            return s.proof(token, args["sha256"])
        if route == "rules":
            module = feature("workflows")
            return (
                module.rule_register(s, token)
                if module
                else {"available": False, "rules": []}
            )
        if route == "catalogue":
            module = feature("catalogue")
            return (
                module.read_catalogue(
                    s.root,
                    s.public_key,
                    qualification_key=(
                        s.qualification_key()
                        if (s.root / "catalog/lanes.json").exists()
                        else None
                    ),
                    scope=s.scope,
                )
                if module
                else {
                    "available": False,
                    "entries": [],
                    "limitation": "Catalogue adapter not installed",
                }
            )
        if route == "campaigns":
            return {
                "campaigns": [
                    {"id": r["id"], "adapter": r["adapter"]}
                    for r in self.campaigns.entries()
                ]
            }
        if route == "campaign":
            return self.campaigns.view(
                identifier(args["id"]), now=datetime.now(timezone.utc)
            )
        if route == "export":
            if not self.workspace:
                raise KeyError("Workspace export not installed")
            return self.workspace.export(token, identifier(args["id"]))
        if route == "validation":
            if not self.workflows:
                raise DecisionConflict("Workflow validator not installed")
            item = s.inbox.item(identifier(args["id"]))
            with s.connect() as db:
                return self.workflows.inspect(item, s.events(db))
        if route == "events":
            # No watcher, lock or write in any source directory. A bounded SSE
            # snapshot shares the evidence-plane event shape; browser polls 3/30s.
            return {
                "scope": s.scope,
                "queue": s.queue(token),
                "campaigns": [
                    self.campaigns.view(r["id"], now=datetime.now(timezone.utc))
                    for r in self.campaigns.entries()
                ],
            }
        raise KeyError("Unknown read route")

    def write(self, route, token, payload):
        if route not in WRITE_ROUTES:
            raise KeyError("Unknown write route")
        s = self.service
        if route == "logout":
            return s.logout(token)
        s._write_access(token, route, deciding=route == "decide")
        if route == "review":
            return s.review(token, identifier(payload["id"]))
        if route == "decide":
            return s.decide(token, payload)
        if route == "propose":
            return s.propose(token, payload["proposal_type"], payload)


def create_server(service, *, port=8766, assets=None):
    api = ConsoleAPI(service)
    assets = (
        Path(assets)
        if assets
        else Path(__file__).resolve().parents[2] / "knowledge/viewer"
    )
    static = {
        "/": "decision-console.html",
        "/decision-console.js": "decision-console.js",
        "/decision-console.css": "decision-console.css",
        "/styles.css": "styles.css",
    }

    class Handler(BaseHTTPRequestHandler):
        timeout = SOCKET_TIMEOUT

        def log_message(self, *args):
            pass  # Never print credentials or user evidence.

        def send(
            self, status, value, *, content_type="application/json; charset=utf-8"
        ):
            data = value if isinstance(value, bytes) else canonical(value)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(data)

        def process(self, write=False):
            try:
                host = self.headers.get("Host", "")
                allowed = {
                    "127.0.0.1:" + str(self.server.server_port),
                    "localhost:" + str(self.server.server_port),
                }
                if host not in allowed:
                    raise DecisionUnauthorized("Host refused")
                if write and self.headers.get("Origin") != "http://" + host:
                    raise DecisionUnauthorized("Same-origin request required")
                url = urlsplit(self.path)
                if not write and url.path in static:
                    path = assets / static[url.path]
                    mime = (
                        "text/html"
                        if path.suffix == ".html"
                        else "text/javascript" if path.suffix == ".js" else "text/css"
                    )
                    return self.send(
                        200, path.read_bytes(), content_type=mime + "; charset=utf-8"
                    )
                if not url.path.startswith("/api/tower/"):
                    return self.send(404, {"error": "route-not-found"})
                route = url.path.removeprefix("/api/tower/")
                token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                if write:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 65536:
                        raise ValueError("Request size refused")
                    if (
                        self.headers.get("Content-Type", "").split(";")[0]
                        != "application/json"
                    ):
                        raise ValueError("JSON required")
                    raw = self.rfile.read(size)
                    if len(raw) != size:
                        raise ValueError("Incomplete request body")
                    payload = json.loads(raw)
                    if not isinstance(payload, dict):
                        raise ValueError("Object required")
                    result = (
                        service.login(payload.get("credential"))
                        if route == "session"
                        else api.write(route, token, payload)
                    )
                else:
                    if route not in READ_ROUTES:
                        return self.send(404, {"error": "route-not-found"})
                    args = {
                        k: v[0] for k, v in parse_qs(url.query).items() if len(v) == 1
                    }
                    result = api.read(route, token, args)
                if route == "events":
                    return self.send(
                        200,
                        b"event: tower\ndata: " + canonical(result) + b"\n\n",
                        content_type="text/event-stream",
                    )
                return self.send(200, result)
            except DecisionUnauthorized:
                return self.send(403, {"error": "role-or-session-refused"})
            except DecisionConflict:
                return self.send(
                    409, {"error": "evidence-or-decision-changed-review-again"}
                )
            except KeyError:
                return self.send(404, {"error": "scoped-item-not-found"})
            except TimeoutError:
                self.close_connection = True
                return self.send(408, {"error": "request-timeout"})
            except (ValueError, TypeError, OSError):
                return self.send(422, {"error": "invalid-or-unavailable-evidence"})
            except Exception:
                self.close_connection = True
                return self.send(500, {"error": "internal-error"})

        def do_GET(self):
            self.process()

        def do_POST(self):
            self.process(True)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
