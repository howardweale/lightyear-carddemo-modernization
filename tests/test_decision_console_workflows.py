import copy
import hashlib
import json
import unittest
import uuid
import contextlib
import io
from pathlib import Path
from tests import test_decision_console as fixture
from carddemo_oracle.compare import NORMALIZATION_RULES
from lightyear_control_tower.decisions import (
    canonical,
    digest,
    DecisionConflict,
    DecisionUnauthorized,
)
from lightyear_control_tower.workflows import (
    WorkflowValidation,
    rule_register,
    still_caught,
)
from lightyear_control_tower.features import feature

catalogue = feature("catalogue")
workspaces = feature("workspace")
if catalogue:
    publish_record = catalogue.publish_record
    read_catalogue = catalogue.read_catalogue
    consistency = catalogue.consistency
if workspaces:
    Workspace = workspaces.Workspace
    verify_export = workspaces.verify_export
from lightyear_control_tower.verification import DecisionVerificationError


class WorkflowTests(unittest.TestCase):
    make_request = fixture.ConsoleTests.make_request
    payload = fixture.ConsoleTests.payload

    def setUp(self):
        fixture.ConsoleTests.setUp(self)
        self.workflow = WorkflowValidation(self.service)
        self.workspace = Workspace(self.service) if workspaces else None

    def actor(self, name, roles, kind="human", workloads=()):
        credential = self.service.add_identity(name, name, identity_kind=kind)
        self.service.grant_roles(
            name, roles, reason="Explicit fixture grant", workloads=workloads
        )
        return self.service.login(credential)["token"]

    def request(self, name, kind, values, proposer="author", workload=None):
        bound = {}
        evidence = {}
        for key, value in values.items():
            relative = f"evidence/{name}-{key}.json"
            p = self.root / relative
            p.parent.mkdir(exist_ok=True)
            p.write_bytes(canonical(value))
            bound[key] = hashlib.sha256(p.read_bytes()).hexdigest()
            evidence[key] = relative
        request = {
            "schema": "tower-request/1",
            "scope": "demo",
            "id": name,
            "kind": kind,
            "summary": "Fixture evidence review",
            "bound": bound,
            "evidence": evidence,
            "proposed_by": proposer,
            "workload": workload,
        }
        (self.root / f"work/control-tower/requests/demo/{name}.json").write_bytes(
            canonical(request)
        )
        return self.service.inbox.item(name)

    def decide(self, token, item, outcome, **extra):
        p = self.payload(token, item_id=item, outcome=outcome)
        p.update(extra)
        return self.service.decide(token, p)

    def rule(self):
        return {
            "schema": "tower-rule-proposal/1",
            "id": "padding",
            "title": "Fixed width padding",
            "owner": "Finance",
            "proposed_by": "author",
            "workload": "cards",
            "lane_pair": "cobol-python",
            "field": "name",
            "operation": "fixed-width-right-padding",
            "parameters": {},
            "review_after": "2099-01-01",
        }

    def technical(self, *, hide_fault=False):
        rule = self.rule()
        still = {
            "schema": "tower-still-caught/1",
            "rule_sha256": digest(rule),
            "positive": ["value  ", "value"],
            "planted_fault": ["wrong ", "wrong" if hide_fault else "correct"],
        }
        ledger = {
            "schema_version": "1.0",
            "comparator": "carddemo-intcalc-differential",
            "rules": [
                {
                    **r,
                    "reason": "Fixture",
                    "owner": "Fixture",
                    "review_after": "2099-01-01",
                }
                for r in NORMALIZATION_RULES
            ],
        }
        return self.request(
            "technical",
            "rule-technical-review",
            {"rule": rule, "still_caught": still, "ledger_validation": ledger},
        )

    def test_still_caught_blocks_hidden_fault_and_proposer_cannot_review(self):
        token = self.actor("reviewer", ["technical-reviewer"])
        self.technical(hide_fault=True)
        with self.assertRaises(DecisionConflict):
            self.decide(token, "technical", "approved")
        self.technical()
        e = self.decide(token, "technical", "approved")
        self.assertEqual("independent", e["payload"]["independence"])
        proposer = self.actor("author", ["technical-reviewer"])
        with self.assertRaises(DecisionUnauthorized):
            self.decide(proposer, "technical", "approved")

    def test_register_only_approved_rules_workload_roles_and_retirement(self):
        tech = self.actor("reviewer", ["technical-reviewer"])
        self.technical()
        e = self.decide(tech, "technical", "approved")
        proof = self.service.proof(self.token, e["content_sha256"])
        self.request(
            "business",
            "rule-approval",
            {
                "rule": self.rule(),
                "technical_review": proof,
                "workload": {"id": "cards"},
            },
            workload="cards",
        )
        owner = self.actor("owner", ["business-owner"], workloads=["elsewhere"])
        self.assertEqual([], rule_register(self.service, self.token)["rules"])
        with self.assertRaises(DecisionUnauthorized):
            self.decide(
                owner,
                "business",
                "approved",
                named_owner="Finance",
                review_after="2099-01-01",
            )
        self.service.grant_roles(
            "owner",
            ["business-owner"],
            reason="Fixture cards owner",
            workloads=["cards"],
        )
        decision = self.decide(
            owner,
            "business",
            "approved",
            named_owner="Finance",
            review_after="2099-01-01",
        )
        register = rule_register(self.service, self.token)
        self.assertEqual(1, len(register["rules"]))
        self.assertEqual(
            decision["content_sha256"], register["rules"][0]["approval_sha256"]
        )
        self.request(
            "retire",
            "rule-retirement",
            {"rule": self.rule(), "workload": {"id": "cards"}},
            workload="cards",
        )
        self.decide(
            owner, "retire", "retired", named_owner="Finance", review_after="2099-01-01"
        )
        self.assertEqual([], rule_register(self.service, self.token)["rules"])

    def qualification(self):
        receipt = self.service.sign(
            {
                "schema": "lane-control/1",
                "scope": "demo",
                "id": "reference",
                "outcome": "passed",
            }
        )
        qualification = self.service.sign(
            {
                "schema": "lane-qualification/1",
                "scope": "demo",
                "controls": [
                    {
                        "id": "reference",
                        "expected_outcome": "passed",
                        "receipt_sha256": receipt["content_sha256"],
                    }
                ],
                "fixture_only": True,
                "limits": [
                    "Portable fixture protocol; LAS native adapter not installed"
                ],
            }
        )
        replay = {
            "schema": "lane-replay/1",
            "qualification_sha256": qualification["content_sha256"],
            "receipts": [receipt],
        }
        config = self.root / "control-tower"
        config.mkdir(exist_ok=True)
        (config / "qualification.public.pem").write_bytes(self.service.public_key)
        (config / "qualification-trust.json").write_bytes(
            canonical(
                {
                    "scope": "demo",
                    "public_key": "control-tower/qualification.public.pem",
                }
            )
        )
        item = self.request(
            "accept",
            "qualification-acceptance",
            {"qualification": qualification, "replay": replay},
        )
        return qualification, item

    @unittest.skipUnless(catalogue, "Catalogue is delivered in PR 4")
    def test_unaccepted_missing_replay_excluded_catalogue_expiry_and_public_drift(self):
        qualification, item = self.qualification()
        token = self.actor("qa", ["qualification-approver"])
        entry = {
            "id": "lane",
            "source_lane": "source",
            "target_lane": "target",
            "status": "qualified",
            "record": item["evidence"]["qualification"],
            "record_sha256": item["bound"]["qualification"],
            "bindings": {
                "platform_major": "1",
                "adapter_sha256": "a" * 64,
                "judge_version": "1",
                "rule_register_major": 1,
            },
        }
        with self.assertRaises(KeyError):
            publish_record(
                [entry],
                scope="demo",
                decision_head="a" * 64,
                signer=self.service,
                current_bindings={"lane": entry["bindings"]},
            )
        e = self.decide(token, "accept", "accepted")
        proof = self.service.proof(self.token, e["content_sha256"])
        entry.update(acceptance=proof, acceptance_bound=e["payload"]["bound"])
        catalog = publish_record(
            [entry],
            scope="demo",
            decision_head=proof["journal"]["journal_head_sha256"],
            signer=self.service,
            current_bindings={
                "lane": {**entry["bindings"], "adapter_sha256": "b" * 64}
            },
        )
        self.assertEqual("expired", catalog["entries"][0]["status"])
        folder = self.root / "catalog"
        folder.mkdir()
        (folder / "lanes.json").write_bytes(canonical(catalog))
        view = read_catalogue(self.root, self.service.public_key, scope="demo")
        self.assertEqual("expired", view["entries"][0]["status"])
        projection = {
            "catalogue_sha256": catalog["content_sha256"],
            "entries": [{"id": "lane", "status": "expired"}],
        }
        p = self.root / "public.json"
        w = self.root / "website.json"
        p.write_bytes(canonical(projection))
        w.write_bytes(canonical(projection))
        self.assertEqual(
            "verified", consistency(self.root, self.service.public_key, p, w)["status"]
        )
        from lightyear_control_tower.cli import main

        args = [
            "catalogue-check",
            "--root",
            str(self.root),
            "--trusted-public-key",
            str(self.authority.with_suffix(".public.pem")),
            "--public",
            str(p),
            "--website",
            str(w),
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, main(args))
        projection["entries"][0]["status"] = "qualified"
        w.write_bytes(canonical(projection))
        with self.assertRaisesRegex(
            DecisionVerificationError, "projection-status-mismatch"
        ):
            consistency(self.root, self.service.public_key, p, w)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, main(args))

    def bundle(self):
        members = []
        for kind in ("receipt", "rule-register", "catalogue-entry", "journal"):
            record = (
                self.service.export_session(self.token)
                if kind == "journal"
                else self.service.sign({"schema": kind + "/1", "scope": "demo"})
            )
            members.append(
                {
                    "scope": "demo",
                    "kind": kind,
                    "record": record,
                    "sha256": hashlib.sha256(canonical(record)).hexdigest(),
                }
            )
        return self.service.sign(
            {
                "schema": "tower-evidence-bundle/1",
                "scope": "demo",
                "disclosure": "public-evidence",
                "members": members,
            }
        )

    @unittest.skipUnless(workspaces, "Workspace export is delivered in PR 5")
    def test_two_exact_release_decisions_offline_verify_and_tamper(self):
        self.request("release", "evidence-release", {"archive": self.bundle()})
        customer = self.actor("customer", ["customer-sponsor"], kind="customer")
        self.decide(customer, "release", "approved", decision_slot="customer-sponsor")
        with self.assertRaises(DecisionUnauthorized):
            self.workspace.export(self.token, "release")
        self.decide(
            self.token, "release", "approved", decision_slot="campaign-authorizer"
        )
        exported = self.workspace.export(self.token, "release")
        self.assertEqual(
            "verified", verify_export(exported, self.service.public_key)["status"]
        )
        tampered = copy.deepcopy(exported)
        tampered["bundle"]["scope"] = "other"
        with self.assertRaises(DecisionVerificationError):
            verify_export(tampered, self.service.public_key)
        # Changing the underlying archive invalidates both decisions.
        (self.root / "evidence/release-archive.json").write_bytes(
            canonical(self.bundle())
        )
        with self.assertRaises(ValueError):
            self.workspace.export(self.token, "release")


if __name__ == "__main__":
    unittest.main()
