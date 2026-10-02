import json
import unittest
import uuid
from tests import test_decision_console_workflows as fixture
from lightyear_control_tower.server import ConsoleAPI, READ_ROUTES
from lightyear_control_tower.decisions import canonical, DecisionUnauthorized
from lightyear_control_tower.mcp import TowerTools


class IsolationTests(unittest.TestCase):
    def workspace(self, canary):
        f = fixture.WorkflowTests(
            "test_two_exact_release_decisions_offline_verify_and_tamper"
        )
        f.setUp()
        self.addCleanup(f.doCleanups)
        config = f.root / "control-tower"
        config.mkdir(exist_ok=True)
        (config / "workspace.json").write_bytes(
            canonical(
                {
                    "scope": "demo",
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
                        "scope": "demo",
                        "estate": [
                            {
                                "id": canary,
                                "name": canary,
                                "kind": "program",
                                "private_value": "PRIVATE_CAPTURE",
                            }
                        ],
                        "slice": {"id": "slice"},
                        "verdicts": [
                            {
                                "id": "journey",
                                "verdict": "divergent",
                                "receipt_sha256": "a" * 64,
                            }
                        ],
                        "differences": [
                            {
                                "id": "d1",
                                "class": "accounting",
                                "value": "PRIVATE_CAPTURE",
                            }
                        ],
                        "rules": [{"id": "r1", "title": "Padding"}],
                    }
                )
            )
        )
        f.request("release", "evidence-release", {"archive": f.bundle()})
        customer = f.actor("customer", ["customer-sponsor"], kind="customer")
        f.decide(customer, "release", "approved", decision_slot="customer-sponsor")
        release = f.decide(
            f.token, "release", "approved", decision_slot="campaign-authorizer"
        )
        exported = f.workspace.export(f.token, "release")
        (f.root / "evidence/released.json").write_bytes(canonical(exported))
        credential = f.service.add_identity("bot", "Bot", identity_kind="agent")
        f.service.grant_roles("bot", ["agent", "rule-proposer"], reason="fixture")
        f.mcp = TowerTools(f.service, credential)
        f.customer = customer
        f.exported = exported
        f.release = release
        # Canary in decision history too, without changing any verdict.
        i = f.service.inbox.item("launch")
        f.service.propose(
            f.token,
            "annotation",
            {
                "item_id": "launch",
                "bound": i["bound"],
                "text": canary,
                "request_id": str(uuid.uuid4()),
            },
        )
        return f

    def test_every_read_sse_mcp_and_export_stays_in_workspace_both_directions(self):
        a = self.workspace("CANARY_A_93ff")
        b = self.workspace("CANARY_B_807e")
        for f, foreign in [(a, "CANARY_B_807e"), (b, "CANARY_A_93ff")]:
            api = ConsoleAPI(f.service)
            for route in READ_ROUTES:
                args = {
                    "id": "release" if route == "export" else "launch",
                    "sha256": f.release["content_sha256"],
                }
                try:
                    value = api.read(route, f.token, args)
                except (KeyError, ValueError) as e:
                    value = str(e)
                self.assertNotIn(foreign, json.dumps(value), route)
            for call in [
                f.mcp.queue,
                lambda: f.mcp.item("launch"),
                f.mcp.catalogue,
                lambda: f.mcp.campaign_status("missing"),
            ]:
                try:
                    value = call()
                except (KeyError, ValueError) as e:
                    value = str(e)
                self.assertNotIn(foreign, json.dumps(value))
            for call in [f.mcp.prepare_classification, f.mcp.annotate_request]:
                i = f.service.inbox.item("launch")
                value = call(
                    {
                        "item_id": "launch",
                        "bound": i["bound"],
                        "text": "Draft",
                        "request_id": str(uuid.uuid4()),
                    }
                )
                self.assertNotIn(foreign, json.dumps(value))
            with self.assertRaises(DecisionUnauthorized):
                api.read("queue", b.token if f is a else a.token, {})

    def test_partner_exact_shared_levels_and_private_values_never_visible(self):
        f = self.workspace("CUSTOMER_ESTATE")
        partner = f.actor("partner", ["partner-viewer"])
        api = ConsoleAPI(f.service)
        self.assertEqual("none", api.read("workspace", partner, {})["shared_level"])
        for level in ("status", "summary", "evidence", "none"):
            f.request(
                "share",
                "partner-share",
                {
                    "share": {
                        "scope": "demo",
                        "partner_id": "partner",
                        "archive_sha256": f.exported["archive_sha256"],
                    }
                },
            )
            f.decide(f.customer, "share", level)
            view = api.read("workspace", partner, {})
            self.assertEqual(level, view["shared_level"])
            self.assertNotIn("PRIVATE_CAPTURE", json.dumps(view))
            self.assertNotIn("estate", view)
            self.assertEqual(level in {"summary", "evidence"}, "differences" in view)
            self.assertEqual(level == "evidence", "evidence" in view)
            for route in READ_ROUTES - {"workspace"}:
                with self.assertRaises(DecisionUnauthorized):
                    api.read(route, partner, {"id": "release"})


if __name__ == "__main__":
    unittest.main()
