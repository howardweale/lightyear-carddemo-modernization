import unittest
import importlib.util
from tools.verify_graph_activation_check import BASE, GRAPH, validate

class ActivationCheckTests(unittest.TestCase):
    def test_baseline_and_approved_require_real_responses(self):
        budget = {"ok": True, "submissions_left": 5}
        validate(BASE, {"ok": True}, budget, budget, "baseline")
        validate(BASE | GRAPH, {"ok": True, "context_projection_sha256": "a" * 64},
                 budget, budget, "approved", "a" * 64,
                 {"projection_sha256": "a" * 64, "items": [{"id": "public"}]})
        for names, task, after, search in (
                (BASE, {"ok": True}, budget, {}),
                (BASE | GRAPH, {"ok": False}, budget, {}),
                (BASE | GRAPH, {"ok": True, "context_projection_sha256": "b" * 64}, budget, {}),
                (BASE | GRAPH, {"ok": True}, {"ok": True, "submissions_left": 4}, {})):
            with self.assertRaises(ValueError):
                validate(names, task, budget, after, "approved", "a" * 64, search)


from tests.verify_graph_support import GraphFixture, read, leak_check, digest, canonical


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'Optional MCP SDK; required by Verify CI')
class ActivationProtocolTests(GraphFixture):
    def test_checker_uses_real_stdio_toolkit_and_loopback_fixture(self):
        import asyncio
        import json
        import os
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from types import SimpleNamespace
        from unittest.mock import patch
        from tools.verify_graph_activation_check import probe
        m = self.build()
        leak_check(self.out, digest(self.lane), set(), self.signer,
                   evaluation_inventory_sha256=digest({}))
        proof, trust = self.approve(m)
        manifest = self.root / "public.json"
        manifest.write_bytes(canonical({"files": {}, "graph_trust": trust}))
        decision = self.root / "proof.json"
        decision.write_bytes(canonical(proof))
        task = dict(ok=True, context_projection_sha256=m["projection_sha256"],
                    context_lane_sha256=m["lane_sha256"], disclosure_mode="field")
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                calls.append(self.path)
                if self.headers.get("Authorization") != "Bearer public-protocol-fixture":
                    self.send_error(403); return
                result = task if self.path == "/get_task" else {"ok":True,"submissions_left":5}
                body = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            args = SimpleNamespace(workspace=self.root, public_manifest=manifest,
                graph_projection=self.out, graph_decision=decision, expect="approved",
                judge_url=f"http://127.0.0.1:{server.server_port}")
            with patch.dict(os.environ, LIGHTYEAR_VERIFY_TOKEN="public-protocol-fixture"):
                result = asyncio.run(asyncio.wait_for(probe(args), timeout=25))
                self.assertEqual(16, result["tool_count"])
                args.graph_projection = args.graph_decision = None
                args.expect = "baseline"
                self.assertEqual(10, asyncio.run(asyncio.wait_for(probe(args), timeout=25))["tool_count"])
            self.assertEqual({"/get_task", "/get_budget"}, set(calls))
        finally:
            server.shutdown(); server.server_close(); thread.join(5)
