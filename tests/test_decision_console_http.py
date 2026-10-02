import json
import threading
import unittest
import urllib.request
import urllib.error
from tests import test_decision_console as fixture
from lightyear_control_tower.server import create_server, READ_ROUTES, WRITE_ROUTES
from lightyear_control_tower.mcp import TowerTools
from lightyear_control_tower.controller_decisions import TowerControllerV2
from lightyear_control_tower.verification import DecisionVerificationError


class HttpTests(unittest.TestCase):
    make_request = fixture.ConsoleTests.make_request
    payload = fixture.ConsoleTests.payload

    def setUp(self):
        fixture.ConsoleTests.setUp(self)
        self.http = create_server(self.service, port=0)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.base = "http://127.0.0.1:" + str(self.http.server_port)

    def call(self, route, token=None, data=None, origin=True):
        headers = {"Authorization": "Bearer " + (token or self.token)}
        if origin:
            headers["Origin"] = self.base
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base + "/api/tower/" + route,
            headers=headers,
            data=json.dumps(data).encode() if data is not None else None,
        )
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_every_auditor_write_route_returns_403_and_agent_cannot_decide(self):
        c = self.service.add_identity("audit", "Audit")
        self.service.grant_roles("audit", ["auditor"], reason="fixture")
        token = self.service.login(c)["token"]
        for route in WRITE_ROUTES:
            self.assertEqual(403, self.call(route, token, {})[0], route)
        c = self.service.add_identity("bot", "Bot", identity_kind="agent")
        self.service.grant_roles("bot", ["agent"], reason="fixture")
        token = self.service.login(c)["token"]
        self.assertEqual(403, self.call("decide", token, {})[0])
        self.assertEqual(200, self.call("queue", token)[0])
        self.assertTrue(
            any(
                e["kind"] == "action_refused"
                for e in self.service.export_session(self.token)["events"]
            )
        )

    def test_no_dispatch_routes_and_origin_required(self):
        for route in [
            "start",
            "stop",
            "resume",
            "cancel",
            "schedule",
            "dispatch",
            "model",
            "gate",
        ]:
            self.assertEqual(404, self.call(route, data={})[0])
        self.assertEqual(
            403, self.call("review", data={"id": "launch"}, origin=False)[0]
        )
        self.assertEqual(200, self.call("events")[0])

    def test_mcp_uses_the_live_service_without_a_second_journal_writer(self):
        from lightyear_control_tower.client import ConsoleClient

        c = self.service.add_identity("mcpbot", "MCP bot", identity_kind="agent")
        self.service.grant_roles("mcpbot", ["agent"], reason="Fixture MCP grant")
        tools = TowerTools(ConsoleClient(self.base), c)
        self.assertEqual("demo", tools.queue()["scope"])
        item = tools.item("launch")
        import uuid

        result = tools.annotate_request(
            {
                "item_id": "launch",
                "bound": item["bound"],
                "text": "MCP draft",
                "request_id": str(uuid.uuid4()),
            }
        )
        self.assertEqual("prepared by agent", result["payload"]["label"])
        with self.assertRaises(ValueError):
            ConsoleClient("https://example.com")

    def test_new_controller_checks_each_slot_missing_mismatched_and_void(self):
        event = self.service.decide(self.token, self.payload())
        proof = self.service.proof(self.token, event["content_sha256"])
        controller = TowerControllerV2(
            self.service.public_key, "demo", "c" * 64, event["payload"]["bound"]
        )
        with self.assertRaisesRegex(
            DecisionVerificationError, "authorization-required"
        ):
            controller.before_slot(None, fresh_head="a" * 64)
        bad = TowerControllerV2(
            self.service.public_key,
            "demo",
            "c" * 64,
            {**event["payload"]["bound"], "plan": "a" * 64},
        )
        with self.assertRaisesRegex(DecisionVerificationError, "bound-hash-mismatch"):
            bad.before_slot(proof, fresh_head=proof["journal"]["journal_head_sha256"])
        calls = []

        def handoff():
            p = self.service.proof(self.token, event["content_sha256"])
            return p, p["journal"]["journal_head_sha256"]

        def execute(slot):
            calls.append(slot)
            if slot == 1:
                # A signed terminal decision from the same trusted authority.
                with self.service.transaction() as db:
                    self.service.append(
                        db,
                        "tower_decision",
                        {
                            "schema": "tower-decision/1",
                            "kind": "measurement-validity",
                            "kind_version": 1,
                            "scope": "demo",
                            "bound": {"campaign": "c" * 64},
                            "outcome": "void",
                        },
                        self.service.system_actor(),
                    )
            return slot

        with self.assertRaisesRegex(DecisionVerificationError, "campaign-void"):
            controller.run([1, 2], handoff=handoff, execute_slot=execute)
        self.assertEqual([1], calls)

    def test_new_controller_resume_binds_actual_pause_evidence_bytes(self):
        import hashlib
        from lightyear_control_tower.controller_decisions import pause_evidence
        from lightyear_control_tower.decisions import canonical

        authorization = self.service.decide(self.token, self.payload())
        request = self.make_request("measurement-validity", "pause")
        pause = self.service.decide(
            self.token, self.payload(item_id="pause", outcome="pause")
        )
        controller = TowerControllerV2(
            self.service.public_key,
            "demo",
            request["bound"]["campaign"],
            authorization["payload"]["bound"],
        )

        def check():
            proof = self.service.proof(self.token, authorization["content_sha256"])
            return controller.before_slot(
                proof, fresh_head=proof["journal"]["journal_head_sha256"]
            )

        with self.assertRaisesRegex(DecisionVerificationError, "campaign-paused"):
            check()
        resume = self.make_request("resume", "resume")
        evidence = self.root / resume["evidence"]["pause"]
        evidence.write_bytes(pause_evidence(pause))
        resume["bound"]["pause"] = hashlib.sha256(evidence.read_bytes()).hexdigest()
        (self.root / "work/control-tower/requests/demo/resume.json").write_bytes(
            canonical(resume)
        )
        self.service.decide(
            self.token, self.payload(item_id="resume", outcome="resume")
        )
        self.assertEqual("admitted", check()["status"])


if __name__ == "__main__":
    unittest.main()
