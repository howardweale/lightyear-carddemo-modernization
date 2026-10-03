"""Two populated deployments, live HTTP/SSE and all MCP tools, no swallowed errors."""

import json
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler

from tests import test_decision_console_workflows as fixture
from lightyear_control_tower.server import (
    ConsoleAPI,
    READ_ROUTES,
    WRITE_ROUTES,
    create_server,
)
from lightyear_control_tower.client import ConsoleClient
from lightyear_control_tower.decisions import canonical, DecisionUnauthorized
from lightyear_control_tower.mcp import TowerTools


class IsolationTests(unittest.TestCase):
    def workspace(self, canary):
        f = fixture.WorkflowTests(
            "test_two_exact_release_decisions_offline_verify_and_tamper"
        )
        f.scope = canary
        f.setUp()
        self.addCleanup(f.doCleanups)
        config = f.root / "control-tower"
        config.mkdir(exist_ok=True)
        (config / "workspace.json").write_bytes(
            canonical(
                {
                    "scope": canary,
                    "title": canary,
                    "snapshot": "evidence/estate.json",
                    "released_archive": "evidence/released.json",
                }
            )
        )
        (f.root / "evidence/estate.json").write_bytes(
            canonical(
                f.service.sign(
                    {
                        "schema": "workspace-view/1",
                        "scope": canary,
                        "estate": [
                            {
                                "id": canary,
                                "name": canary,
                                "kind": "program",
                                "private_value": "PRIVATE_CAPTURE",
                            }
                        ],
                        "slice": {
                            "id": canary,
                            "lane_pair": "fixture",
                            "private_value": "PRIVATE_CAPTURE",
                        },
                        "progress": {
                            "state": "review",
                            "completed": 1,
                            "total": 1,
                            "private_value": "PRIVATE_CAPTURE",
                        },
                        "verdicts": [
                            {
                                "id": canary,
                                "verdict": "divergent",
                                "receipt_sha256": "a" * 64,
                            }
                        ],
                        "differences": [
                            {
                                "id": canary,
                                "class": "accounting",
                                "value": "PRIVATE_CAPTURE",
                            }
                        ],
                        "rules": [{"id": canary, "title": canary}],
                    }
                )
            )
        )
        scoped_rule = {**f.rule(), "title": canary}
        f.rule = lambda: dict(scoped_rule)
        f.technical()
        reviewer = f.actor("reviewer", ["technical-reviewer"])
        technical = f.decide(reviewer, "technical", "approved")
        f.request(
            "business",
            "rule-approval",
            {
                "rule": f.rule(),
                "technical_review": f.service.proof(
                    f.token, technical["content_sha256"]
                ),
                "workload": {"id": "cards"},
            },
            workload="cards",
        )
        owner = f.actor("owner", ["business-owner"], workloads=["cards"])
        f.decide(
            owner,
            "business",
            "approved",
            named_owner=canary,
            review_after=f.rule()["review_after"],
        )
        _, item = f.qualification()
        qa = f.actor("qa", ["qualification-approver"])
        accepted = f.decide(qa, "accept", "accepted")
        proof = f.service.proof(f.token, accepted["content_sha256"])
        bindings = {
            "platform_major": "1",
            "adapter_sha256": "a" * 64,
            "judge_version": "1",
            "rule_register_major": 1,
        }
        entry = {
            "id": canary,
            "status": "qualified",
            "source_lane": "source",
            "target_lane": "target",
            "record": item["evidence"]["qualification"],
            "record_sha256": item["bound"]["qualification"],
            "acceptance": proof,
            "acceptance_bound": accepted["payload"]["bound"],
            "bindings": bindings,
        }
        catalogue = fixture.publish_record(
            [entry],
            scope=canary,
            signer=f.service,
            decision_head=proof["journal"]["journal_head_sha256"],
            current_bindings={canary: bindings},
        )
        (f.root / "catalog").mkdir()
        (f.root / "catalog/lanes.json").write_bytes(canonical(catalogue))
        campaign = f.root / "evidence/campaign"
        campaign.mkdir()
        for name, data in (
            ("plan", {"slots": [{"phase": "cohort", "index": 1}]}),
            (
                "report",
                {"results": [{"phase": "cohort", "index": 1, "status": "passed"}]},
            ),
        ):
            (campaign / (name + ".json")).write_bytes(
                canonical(f.service.sign({"scope": canary, **data}))
            )
        (config / "campaigns.json").write_bytes(
            canonical(
                {
                    "campaigns": [
                        {
                            "id": canary,
                            "scope": canary,
                            "adapter": "ms94-stage-b",
                            "root": str(f.root),
                            "published_directory": str(campaign),
                            "work_directory": str(campaign),
                            "read_mode": "immutable-export",
                            "trusted_public_key": str(
                                f.authority.with_suffix(".public.pem")
                            ),
                        }
                    ]
                }
            )
        )
        f.request("release", "evidence-release", {"archive": f.bundle()})
        f.customer = f.actor("customer", ["customer-sponsor"], kind="customer")
        f.decide(
            f.customer,
            "release",
            "approved",
            decision_slot="customer-sponsor",
            reason=canary,
        )
        f.release = f.decide(
            f.token,
            "release",
            "approved",
            decision_slot="campaign-authorizer",
            reason=canary,
        )
        f.exported = f.workspace.export(f.token, "release")
        (f.root / "evidence/released.json").write_bytes(canonical(f.exported))
        credential = f.service.add_identity("bot", "Bot", identity_kind="agent")
        f.service.grant_roles("bot", ["agent", "rule-proposer"], reason=canary)
        f.http = create_server(f.service, port=0)
        thread = threading.Thread(target=f.http.serve_forever, daemon=True)
        thread.start()

        def close_http():
            f.http.shutdown()
            thread.join(5)
            f.http.server_close()

        self.addCleanup(close_http)
        f.base = "http://127.0.0.1:" + str(f.http.server_address[1])
        f.mcp = TowerTools(ConsoleClient(f.base), credential)
        return f

    def request(self, f, route, token, *, write=False, **args):
        url = f.base + "/api/tower/" + route
        if args:
            url += "?" + urlencode(args)
        req = Request(
            url,
            data=b"{}" if write else None,
            headers={
                "Authorization": "Bearer " + token,
                "Origin": f.base,
                "Content-Type": "application/json",
            },
        )
        try:
            response = build_opener(ProxyHandler({})).open(req, timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, response.read().decode()

    def test_every_read_write_sse_and_mcp_with_foreign_tokens_both_directions(self):
        a, b = self.workspace("CANARY_A_93ff"), self.workspace("CANARY_B_807e")
        for f, other in ((a, b), (b, a)):
            api = ConsoleAPI(f.service)
            # Prove the source sets are populated, rather than accepting empty/error responses.
            for route in (
                "queue",
                "item",
                "history",
                "rules",
                "catalogue",
                "campaign",
                "workspace",
                "export",
                "proof",
            ):
                args = {
                    "id": (
                        f.scope
                        if route == "campaign"
                        else "release" if route == "export" else "technical"
                    ),
                    "sha256": f.release["content_sha256"],
                }
                self.assertIn(
                    f.scope, json.dumps(api.read(route, f.token, args)), route
                )
            for route in READ_ROUTES:
                args = {
                    "id": (
                        f.scope
                        if route == "campaign"
                        else "release" if route == "export" else "technical"
                    ),
                    "sha256": f.release["content_sha256"],
                }
                status, body = self.request(f, route, f.token, **args)
                self.assertEqual(200, status, (route, body))
                self.assertNotIn(other.scope, body, route)
                if route == "validation":
                    own_hash = f.service.inbox.item("technical")["bound"]["rule"]
                    foreign_hash = other.service.inbox.item("technical")["bound"][
                        "rule"
                    ]
                    self.assertNotEqual(own_hash, foreign_hash)
                    self.assertIn(own_hash, body)
                    self.assertNotIn(foreign_hash, body)
                if route == "events":
                    self.assertIn("event: tower", body)
                    self.assertIn(f.scope, body)
                status, body = self.request(f, route, other.token, **args)
                self.assertEqual(403, status, (route, body))
                self.assertNotIn(f.scope, body)
            for route in WRITE_ROUTES:
                status, body = self.request(f, route, other.token, write=True)
                self.assertEqual(403, status, (route, body))
                self.assertNotIn(f.scope, body)
            item = f.service.inbox.item("technical")

            def payload():
                return {
                    "item_id": "technical",
                    "bound": item["bound"],
                    "text": f.scope,
                    "rule": {**f.rule(), "proposed_by": "bot"},
                    "request_id": str(uuid.uuid4()),
                }

            calls = [
                f.mcp.queue,
                lambda: f.mcp.item("technical"),
                f.mcp.catalogue,
                lambda: f.mcp.campaign_status(f.scope),
                lambda: f.mcp.propose_rule(payload()),
                lambda: f.mcp.prepare_classification(payload()),
                lambda: f.mcp.annotate_request(payload()),
            ]
            for call in calls:
                self.assertNotIn(other.scope, json.dumps(call()))
            own = f.mcp.token
            f.mcp.token = other.mcp.token
            try:
                for call in calls:
                    with self.assertRaises(DecisionUnauthorized):
                        call()
            finally:
                f.mcp.token = own

    def test_malformed_campaign_does_not_break_other_campaign_or_live_sse(self):
        f = self.workspace("SSE_HEALTHY")
        registry_path = f.root / "control-tower/campaigns.json"
        registry = json.loads(registry_path.read_bytes())
        broken = f.root / "evidence/broken"
        broken.mkdir()
        (broken / "plan.json").write_bytes(canonical(f.service.sign({"slots": [None]})))
        registry["campaigns"].append(
            {
                **registry["campaigns"][0],
                "id": "broken",
                "work_directory": str(broken),
                "published_directory": str(broken),
            }
        )
        registry_path.write_bytes(canonical(registry))
        status, body = self.request(f, "events", f.token)
        self.assertEqual(200, status)
        value = json.loads(body.split("data: ", 1)[1])
        campaigns = {c["id"]: c for c in value["campaigns"]}
        self.assertEqual("terminal", campaigns[f.scope]["state"])
        self.assertEqual("unavailable", campaigns["broken"]["state"])

    def test_partner_levels_are_allowlisted_and_shares_are_per_partner(self):
        f = self.workspace("CUSTOMER_ESTATE")
        first = f.actor("partner-one", ["partner-viewer"])
        second = f.actor("partner-two", ["partner-viewer"])
        api = ConsoleAPI(f.service)
        for name, level in (("partner-one", "evidence"), ("partner-two", "status")):
            f.request(
                "share-" + name,
                "partner-share",
                {
                    "share": {
                        "scope": f.scope,
                        "partner_id": name,
                        "archive_sha256": f.exported["archive_sha256"],
                    }
                },
            )
            f.decide(f.customer, "share-" + name, level)
        self.assertEqual("evidence", api.read("workspace", first, {})["shared_level"])
        view = api.read("workspace", second, {})
        self.assertEqual("status", view["shared_level"])
        self.assertNotIn("PRIVATE_CAPTURE", json.dumps(view))
        self.assertNotIn("verdicts", view)
        self.assertNotIn("journeys", view)
        self.assertNotIn("differences", view)
        self.assertNotIn(
            "PRIVATE_CAPTURE", json.dumps(api.read("workspace", first, {}))
        )
        f.decide(f.customer, "share-partner-two", "none")
        self.assertEqual("none", api.read("workspace", second, {})["shared_level"])
        self.assertEqual("evidence", api.read("workspace", first, {})["shared_level"])
        for route in READ_ROUTES - {"workspace"}:
            with self.assertRaises(DecisionUnauthorized):
                api.read(route, first, {"id": "release"})


if __name__ == "__main__":
    unittest.main()
