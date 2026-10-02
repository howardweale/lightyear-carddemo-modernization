import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from datetime import timedelta
from lightyear_control_tower.console import ConsoleService, provision
from lightyear_control_tower.decisions import (
    DecisionConflict,
    DecisionUnauthorized,
    canonical,
    utcnow,
)
from lightyear_control_tower import verify_decision, DecisionVerificationError


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.authority = self.root / "private/authority.json"
        self.credential = (
            provision(self.authority, "demo", "howard", "Howard").read_text().strip()
        )
        self.service = ConsoleService(self.root, self.authority)
        self.addCleanup(self.service.close)
        self.service.grant_roles(
            "howard",
            ["operator", "campaign-authorizer"],
            reason="Explicit test fixture grant",
        )
        self.token = self.service.login(self.credential)["token"]
        self.make_request()

    def make_request(
        self, kind="campaign-authorization", name="launch", proposed_by="howard"
    ):
        bound = {}
        evidence = {}
        for key in self.service.registry.get(kind).hashes:
            path = self.root / "evidence" / f"{name}-{key}.json"
            path.parent.mkdir(exist_ok=True)
            path.write_text(
                json.dumps(
                    ["cohort-01", "cohort-02"]
                    if kind == "classification-acceptance" and key == "item_ids"
                    else {"fixture": key}
                )
            )
            bound[key] = hashlib.sha256(path.read_bytes()).hexdigest()
            evidence[key] = path.relative_to(self.root).as_posix()
        request = {
            "schema": "tower-request/1",
            "scope": "demo",
            "id": name,
            "kind": kind,
            "bound": bound,
            "evidence": evidence,
            "summary": "Review the exact fixture",
            "proposed_by": proposed_by,
        }
        folder = self.root / "work/control-tower/requests/demo"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (name + ".json")).write_bytes(canonical(request))
        return request

    def payload(self, token=None, item_id="launch", outcome="authorized", view=True):
        token = token or self.token
        item = (
            self.service.review(token, item_id)
            if view
            else self.service.item(token, item_id)
        )
        return {
            "item_id": item_id,
            "bound": item["bound"],
            "outcome": outcome,
            "reason": "Exact evidence reviewed",
            "previous_decision_sha256": (item["latest_decision"] or {}).get(
                "content_sha256"
            ),
            "request_id": str(uuid.uuid4()),
        }

    def test_provision_no_roles_and_role_changes_journaled(self):
        self.assertEqual(
            [], json.loads(self.authority.read_bytes())["operators"][0]["roles"]
        )
        self.assertTrue(
            any(
                e["kind"] == "roles_assigned"
                for e in self.service.export_session(self.token)["events"]
            )
        )

    def test_classification_requires_every_item_and_is_operator_review(self):
        self.make_request("classification-acceptance", "classify", proposed_by="other")
        self.service.grant_roles(
            "howard", ["operator", "classification-reviewer"], reason="Fixture reviewer"
        )
        p = self.payload(item_id="classify", outcome="accept")
        with self.assertRaisesRegex(ValueError, "Every bound classification"):
            self.service.decide(self.token, p)
        p["item_decisions"] = {"cohort-01": "accept", "cohort-02": "reject"}
        with self.assertRaisesRegex(ValueError, "Overall acceptance"):
            self.service.decide(self.token, p)
        p["outcome"] = "reject"
        event = self.service.decide(self.token, p)
        proof = self.service.proof(self.token, event["content_sha256"])
        checked = verify_decision(
            proof,
            self.service.public_key,
            "classification-acceptance",
            event["payload"]["bound"],
        )
        self.assertEqual("operator-review", checked["independence"])
        self.assertEqual(p["item_decisions"], checked["item_decisions"])

    def test_same_session_current_view_and_exact_bound_required(self):
        with self.assertRaises(DecisionConflict):
            self.service.decide(self.token, self.payload(view=False))
        p = self.payload()
        other = self.service.login(self.credential)["token"]
        with self.assertRaises(DecisionConflict):
            self.service.decide(other, p)
        p["bound"]["plan"] = "f" * 64
        with self.assertRaises(DecisionConflict):
            self.service.decide(self.token, p)

    def test_evidence_change_is_invalid_not_decidable(self):
        p = self.payload()
        (self.root / "evidence/launch-plan.json").write_text("changed")
        self.assertEqual(
            "invalid", self.service.queue(self.token)["items"][0]["status"]
        )
        with self.assertRaises(ValueError):
            self.service.decide(self.token, p)

    def test_countersignature_idempotency_supersession_and_hash_binding(self):
        p = self.payload()
        e = self.service.decide(self.token, p)
        self.assertEqual(e, self.service.decide(self.token, p))
        p["reason"] = "different"
        with self.assertRaises(DecisionConflict):
            self.service.decide(self.token, p)
        proof = self.service.proof(self.token, e["content_sha256"])
        result = verify_decision(
            proof,
            self.service.public_key,
            "campaign-authorization",
            e["payload"]["bound"],
            scope="demo",
            outcomes=("authorized",),
        )
        self.assertEqual("operator-review", result["independence"])
        self.assertTrue(result["decider_is_proposer"])
        self.assertFalse(result["verdict_changed"])
        bad = copy.deepcopy(e["payload"]["bound"])
        bad["plan"] = "f" * 64
        with self.assertRaisesRegex(DecisionVerificationError, "bound-hash-mismatch"):
            verify_decision(
                proof, self.service.public_key, "campaign-authorization", bad
            )
        self.service.decide(self.token, self.payload(outcome="rejected"))
        newproof = self.service.proof(self.token, e["content_sha256"])
        with self.assertRaisesRegex(DecisionVerificationError, "decision-superseded"):
            verify_decision(
                newproof,
                self.service.public_key,
                "campaign-authorization",
                e["payload"]["bound"],
            )
        with self.assertRaisesRegex(DecisionVerificationError, "stale-journal-head"):
            verify_decision(
                proof,
                self.service.public_key,
                "campaign-authorization",
                e["payload"]["bound"],
                expected_head=newproof["journal"]["journal_head_sha256"],
            )

    def test_agent_cannot_get_approving_role_or_decide_even_with_forged_payload(self):
        c = self.service.add_identity("bot", "Bot", identity_kind="agent")
        with self.assertRaises(DecisionUnauthorized):
            self.service.grant_roles("bot", ["campaign-authorizer"], reason="test")
        self.service.grant_roles("bot", ["agent", "rule-proposer"], reason="test")
        t = self.service.login(c)["token"]
        p = self.payload(t)
        p["actor"] = {"id": "howard"}
        with self.assertRaises(DecisionUnauthorized):
            self.service.decide(t, p)
        self.assertEqual(
            "action_refused",
            self.service.export_session(self.token)["events"][-1]["kind"],
        )
        draft = self.service.propose(
            t,
            "annotation",
            {
                "item_id": "launch",
                "bound": p["bound"],
                "text": "A draft",
                "request_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual("prepared by agent", draft["payload"]["label"])

    def test_auditor_reads_but_every_domain_write_denied(self):
        c = self.service.add_identity("audit", "Auditor")
        self.service.grant_roles("audit", ["auditor"], reason="test")
        t = self.service.login(c)["token"]
        self.assertTrue(self.service.queue(t)["items"])
        for action in [
            lambda: self.service.review(t, "launch"),
            lambda: self.service.decide(t, {}),
            lambda: self.service.propose(t, "annotation", {}),
            lambda: self.service.dispatch(t, {}),
        ]:
            with self.assertRaises(DecisionUnauthorized):
                action()

    def test_independence_and_required_validator_fail_closed(self):
        self.make_request("classification-acceptance", "classify")
        self.service.grant_roles(
            "howard", ["operator", "classification-reviewer"], reason="test"
        )
        with self.assertRaises(DecisionUnauthorized):
            self.service.decide(
                self.token, self.payload(item_id="classify", outcome="accept")
            )
        self.make_request("rule-technical-review", "rule", proposed_by="other")
        self.service.grant_roles(
            "howard", ["operator", "technical-reviewer"], reason="test"
        )
        with self.assertRaises(DecisionConflict):
            self.service.decide(
                self.token, self.payload(item_id="rule", outcome="approved")
            )

    def test_cross_scope_and_path_escape_never_reflected(self):
        p = self.root / "work/control-tower/requests/demo/foreign.json"
        p.write_text(
            json.dumps(
                {
                    "schema": "tower-request/1",
                    "scope": "other",
                    "id": "foreign",
                    "summary": "SECRET_CANARY",
                }
            )
        )
        self.assertNotIn("SECRET_CANARY", json.dumps(self.service.queue(self.token)))
        r = self.make_request(name="escape")
        r["evidence"]["plan"] = "../outside"
        (p.parent / "escape.json").write_bytes(canonical(r))
        self.assertEqual(
            "invalid",
            next(
                i
                for i in self.service.queue(self.token)["items"]
                if i["id"] == "escape"
            )["status"],
        )

    def test_no_dispatch_or_verdict_mutation(self):
        with self.assertRaises(DecisionUnauthorized):
            self.service.dispatch(self.token, {})
        with self.assertRaises(DecisionUnauthorized):
            self.service.gate("anything")
        p = self.payload()
        p["verdict"] = "passed"
        event = self.service.decide(self.token, p)
        self.assertNotIn("verdict", event["payload"])

    def test_second_scope_cannot_reuse_workspace_data_root(self):
        other = self.root / "other/authority.json"
        provision(other, "other", "other", "Other")
        with self.assertRaisesRegex(ValueError, "another scope or authority"):
            ConsoleService(self.root, other)

    @unittest.skipUnless(importlib.util.find_spec("mcp"), "Optional agent SDK; exercised by dedicated Console CI")
    def test_mcp_tool_surface_contains_only_reads_and_drafts(self):
        import asyncio
        from lightyear_control_tower.mcp import create_server

        credential = self.service.add_identity(
            "mcp-agent", "MCP agent", identity_kind="agent"
        )
        self.service.grant_roles(
            "mcp-agent", ["agent", "rule-proposer"], reason="Fixture MCP role"
        )
        server = create_server(self.service, credential)
        names = {tool.name for tool in asyncio.run(server.list_tools())}
        self.assertEqual(
            {
                "queue",
                "item",
                "campaign_status",
                "catalogue",
                "propose_rule",
                "prepare_classification",
                "annotate_request",
            },
            names,
        )


if __name__ == "__main__":
    unittest.main()
