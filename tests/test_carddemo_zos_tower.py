"""Public fixture rehearsal and adversarial no-values checks on every transport."""

import copy
import json
import shutil
import stat
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

from lightyear_control_tower.console import ConsoleService, provision
from lightyear_control_tower.decisions import canonical, digest, DecisionUnauthorized
from lightyear_control_tower.server import (
    ConsoleAPI,
    create_server,
    READ_ROUTES,
    WRITE_ROUTES,
)
from lightyear_control_tower.client import ConsoleClient
from lightyear_control_tower.mcp import TowerTools
from lightyear_control_tower.carddemo_console import verify_release
from lightyear_control_tower import carddemo_policy as p
from lightyear_mainframe.zos_bindings import ROOT, dataset_binding, load_bindings
from lightyear_mainframe.records import load_copybook, decode_fixed
from lightyear_mainframe.zos_bridge import approved_paths, implementation_hashes
from lightyear_mainframe.zos_compare import TIMESTAMP


def fixture_rule():
    b = dataset_binding(load_bindings(), "INTCALC", "STEP15", "TRANSACT")
    layout = load_copybook(ROOT / b["copybook"])
    return p.rule(
        dict(
            schema="zos-tower-rule/1",
            workload=p.WORKLOAD,
            dataset="STEP15/TRANSACT",
            field=b["timestamp_fields"][0],
            pattern=TIMESTAMP,
            runs=["1" * 64, "2" * 64],
            still_caught=dict(
                field=next(
                    f.path
                    for f in layout.fields
                    if not f.filler and f.path not in b["timestamp_fields"]
                ),
                detected=True,
            ),
        )
    )


class TowerIntakeTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "work/zos-tower-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()
        authority = Path(self.temp.name) / "authority/authority.json"
        credential = (
            provision(authority, p.SCOPE, p.HOWARD, "Howard Weale").read_text().strip()
        )
        self.s = ConsoleService(self.root, authority)
        self.addCleanup(self.s.close)
        self.s.grant_roles(
            p.HOWARD,
            [
                "operator",
                "qualification-approver",
                "normalization-approver",
                "business-owner",
                "campaign-authorizer",
            ],
            reason="Public test only",
            workloads=[p.WORKLOAD],
        )
        self.agent = self.s.add_identity(p.AGENT, "Intake agent", identity_kind="agent")
        self.s.grant_roles(p.AGENT, ["agent"], reason="Public test only")
        sponsor = self.s.add_identity(
            "release-sponsor", "Release sponsor", identity_kind="customer"
        )
        self.s.grant_roles(
            "release-sponsor", ["customer-sponsor"], reason="Public test only"
        )
        self.token = self.s.login(credential)["token"]
        self.sponsor = self.s.login(sponsor)["token"]
        self.tools = TowerTools(self.s, self.agent)
        self.api = ConsoleAPI(self.s)
        self.summary = dict(
            schema="zos-intake-review/1",
            arrival_sha256="3" * 64,
            intake_sha256="4" * 64,
            files=50,
            runs=3,
            findings=0,
            status="ready-for-review",
        )
        self.intake = p.write_request(
            self.root, "intake-acceptance", {"intake": self.summary}
        )
        self.rule = fixture_rule()
        self.normal = p.write_request(self.root, "normalization", {"rule": self.rule})
        difference = dict(
            schema="zos-difference-review/1",
            source_sha256="5" * 64,
            target_sha256="6" * 64,
            diagnostic_sha256="7" * 64,
            added=0,
            deleted=0,
            changed=1,
        )
        self.diff = p.write_request(
            self.root,
            "difference-disposition",
            {k: difference for k in p.registry().get("difference-disposition").hashes},
        )
        self.bundle = dict(
            schema="zos-evidence-release/1",
            scope=p.SCOPE,
            disclosure_policy=p.POLICY,
            members=[self.summary, difference],
        )
        self.release = p.write_request(
            self.root, "evidence-release", {"archive": self.bundle}
        )

    def decide(
        self,
        request,
        outcome,
        *,
        token=None,
        reason="Public fixture operator review",
        **extra,
    ):
        token = token or self.token
        item = self.s.review(token, request["id"])
        slot = extra.get("decision_slot")
        previous = (
            item["latest_decisions_by_role"].get(slot)
            if slot
            else (item["latest_decision"] or {}).get("content_sha256")
        )
        payload = dict(
            item_id=item["id"],
            bound=item["bound"],
            outcome=outcome,
            reason=reason,
            request_id=str(uuid4()),
            previous_decision_sha256=previous,
            **extra,
        )
        if item["kind"] == "normalization":
            payload.update(
                named_owner=p.HOWARD,
                review_after=(
                    datetime.now(timezone.utc).date() + timedelta(days=10)
                ).isoformat(),
            )
        return self.s.decide(token, payload)

    def propose(self, text="Public fixture proposal"):
        item = self.tools.item(self.normal["id"])
        return self.tools.propose_rule(
            dict(
                item_id=item["id"],
                bound=item["bound"],
                request_id=str(uuid4()),
                text=text,
                rule=self.rule,
            )
        )

    def test_four_kinds_and_read_only_arrivals(self):
        self.assertEqual(
            p.POLICY, p.initialize_workspace(self.root)["disclosure_policy"]
        )
        p.initialize_workspace(self.root)
        self.assertEqual(
            set(p.KINDS), {i["kind"] for i in self.s.queue(self.token)["items"]}
        )
        before = self.s.export_session(self.token)["journal_head_sha256"]
        view = self.api.read("workspace", self.token, {})
        self.assertTrue(view["read_only"])
        self.assertEqual(3, view["arrivals"][0]["runs"])
        self.assertEqual(
            before, self.s.export_session(self.token)["journal_head_sha256"]
        )
        with self.assertRaises(KeyError):
            self.api.write("arrivals", self.token, {})
        decision = self.decide(self.diff, "intended-change")
        self.assertFalse(decision["payload"]["verdict_changed"])

    def test_normalization_agent_then_howard_and_verified_register_only(self):
        with self.assertRaises(ValueError):
            self.decide(self.normal, "approved")
        self.propose()
        with self.assertRaises(DecisionUnauthorized):
            self.decide(self.normal, "approved", token=self.tools.token)
        event = self.decide(self.normal, "approved")
        self.assertEqual("operator-review", event["payload"]["independence"])
        register = self.s.register(self.token)
        head = register["journal_head_sha256"]
        args = (self.s.public_key, head, self.rule["runs"][0])
        now = datetime.now(timezone.utc)
        expected = {self.rule["dataset"]: [self.rule["field"]]}
        self.assertEqual(expected, approved_paths(register, *args, at=now))
        direct = dict(schema="zos-approved-rules/1", rules=register["rules"])
        self.assertEqual(expected, approved_paths(direct, *args, at=now))
        for broken in (
            dict(rules=direct["rules"]),
            {**direct, "rules": [{**direct["rules"][0], "ledger": {}}]},
        ):
            with self.assertRaises(ValueError):
                approved_paths(broken, *args, at=now)
        with self.assertRaises(ValueError):
            approved_paths(
                register, self.s.public_key, "0" * 64, self.rule["runs"][0], at=now
            )
        with self.assertRaises(ValueError):
            approved_paths(register, self.s.public_key, head, "8" * 64, at=now)
        with self.assertRaises(ValueError):
            approved_paths(register, *args, at=now + timedelta(days=11))
        tampered = copy.deepcopy(direct)
        tampered["rules"][0]["rule"]["runs"][0] = "8" * 64
        with self.assertRaises(ValueError):
            approved_paths(tampered, *args, at=now)
        self.decide(self.normal, "rejected")
        latest = self.s.register(self.token)
        self.assertEqual([], latest["rules"])
        with self.assertRaises(ValueError):
            approved_paths(
                direct,
                self.s.public_key,
                latest["journal_head_sha256"],
                self.rule["runs"][0],
                at=now,
            )
        self.assertNotIn("spec/comparison-normalizations.json", implementation_hashes())

    def test_release_requires_both_roles_and_closed_members(self):
        with self.assertRaises(DecisionUnauthorized):
            self.s.release(self.token, self.release["id"])
        self.decide(self.release, "approved", decision_slot="campaign-authorizer")
        with self.assertRaises(DecisionUnauthorized):
            self.s.release(self.token, self.release["id"])
        self.decide(
            self.release,
            "approved",
            token=self.sponsor,
            decision_slot="customer-sponsor",
        )
        archive = self.s.release(self.token, self.release["id"])
        self.assertEqual(
            "verified", verify_release(archive, self.s.public_key)["status"]
        )
        broken = copy.deepcopy(archive)
        broken["bundle"]["members"][0]["record_value"] = "hidden"
        with self.assertRaises(ValueError):
            verify_release(broken, self.s.public_key)
        self.decide(
            self.release,
            "rejected",
            token=self.sponsor,
            decision_slot="customer-sponsor",
        )
        with self.assertRaises(ValueError):
            self.s.release(self.token, self.release["id"])

    def test_business_rules_unavailable_without_reading_confidential_catalogue(self):
        api = ConsoleAPI(self.s)
        with patch("lightyear_business_rules.tower.read_catalogue") as read_catalogue:
            self.assertEqual(
                {"available": False, "catalogues": []},
                api.read("business-rules", self.token, {}),
            )
            with self.assertRaises(DecisionUnauthorized):
                api.read("business-rules", "invalid-session", {})
            read_catalogue.assert_not_called()

    def test_no_record_values_in_any_route_sse_mcp_or_export(self):
        markers = ["Q9Z7A6B5C4", "R8Y6D5E4F3"]
        # Values planted in a real public fixed-width record, both raw and decoded.
        b = dataset_binding(load_bindings(), "INTCALC", "STEP15", "ACCTFILE")
        layout = load_copybook(ROOT / b["copybook"])
        field = next(
            f
            for f in layout.fields
            if f.length >= len(markers[0]) and not f.digits and not f.filler
        )
        raw = bytearray(
            (
                ROOT
                / "tests/mainframe/fixtures/arrival-rehearsal/INTCALC-run1-2026-10-05/before/ACCTFILE.bin"
            ).read_bytes()
        )
        raw[field.offset : field.offset + field.length] = (
            markers[0].ljust(field.length).encode("cp037")
        )
        decoded = decode_fixed(layout, bytes(raw))
        self.assertIn(markers[0], canonical(decoded).decode())
        private = self.root / "work/mainframe/arrivals/canary/original"
        private.mkdir(parents=True)
        (private / "ACCTFILE.bin").write_bytes(raw)
        (private.parent / "decoded.json").write_bytes(canonical(decoded))
        # Also attack free-text, request names, generic workspace/catalogue adapters.
        path = self.s.inbox.directory / (self.intake["id"] + ".json")
        req = json.loads(path.read_bytes())
        req.update(
            summary=markers[0], requested_by=markers[1], created_at_utc=markers[1]
        )
        path.write_bytes(canonical(req))
        (self.s.inbox.directory / (markers[0] + ".json")).write_text(
            json.dumps({"value": markers[1]})
        )
        for rel in (
            "control-tower/workspace.json",
            "catalog/lanes.json",
            "control-tower/campaigns.json",
        ):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"title": markers[0], "value": markers[1]}))
        self.propose(markers[0])
        event = self.decide(self.normal, "approved", reason=markers[1])
        self.decide(
            self.release,
            "approved",
            reason=markers[0],
            decision_slot="campaign-authorizer",
        )
        self.decide(
            self.release,
            "approved",
            reason=markers[1],
            token=self.sponsor,
            decision_slot="customer-sponsor",
        )
        server = create_server(self.s, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = "http://127.0.0.1:" + str(server.server_port)
        opener = build_opener(ProxyHandler({}))
        args = {
            "item": "?id=" + self.intake["id"],
            "export": "?id=" + self.release["id"],
            "validation": "?id=" + self.normal["id"],
            "proof": "?sha256=" + event["content_sha256"],
            "campaign": "?id=" + markers[0],
        }
        seen = set()
        for route in READ_ROUTES:
            request = Request(
                url + "/api/tower/" + route + args.get(route, ""),
                headers={"Authorization": "Bearer " + self.token},
            )
            with opener.open(request) as response:
                raw_response = response.read()
            for marker in markers:
                self.assertNotIn(marker.encode(), raw_response, route)
            seen.add(route)
        self.assertEqual(READ_ROUTES, seen)
        # Actual MCP adapter through HTTP, not a separate in-process projection.
        tools = TowerTools(ConsoleClient(url), self.agent)
        responses = [
            tools.queue(),
            tools.item(self.normal["id"]),
            tools.catalogue(),
            tools.campaign_status(markers[0]),
        ]
        item = tools.item(self.normal["id"])
        payload = dict(
            item_id=item["id"],
            bound=item["bound"],
            request_id=str(uuid4()),
            text=markers[1],
            rule=self.rule,
        )
        responses.append(tools.propose_rule(payload))
        for method in (tools.prepare_classification, tools.annotate_request):
            responses.append(method({**payload, "request_id": str(uuid4())}))
        for response in responses:
            for marker in markers:
                self.assertNotIn(marker.encode(), canonical(response))
        # Every write route also has a non-reflecting refusal path.
        for route in WRITE_ROUTES | {"session"}:
            request = Request(
                url + "/api/tower/" + route,
                data=canonical({"id": markers[0], "text": markers[1]}),
                headers={"Origin": url, "Content-Type": "application/json"},
            )
            try:
                response = opener.open(request)
            except HTTPError as exc:
                response = exc
            with response:
                raw_response = response.read()
            for marker in markers:
                self.assertNotIn(marker.encode(), raw_response)

    def test_evidence_unknown_fields_and_arrival_paths_refused(self):
        for record in (
            dict(self.summary, value="secret"),
            dict(self.rule, raw_hex="secret"),
        ):
            with self.assertRaises(ValueError):
                p.evidence(record)
        reqpath = self.s.inbox.directory / (self.intake["id"] + ".json")
        request = json.loads(reqpath.read_bytes())
        request["evidence"]["intake"] = "work/mainframe/arrivals/secret.json"
        reqpath.write_bytes(canonical(request))
        with self.assertRaises((ValueError, OSError)):
            self.s.item(self.token, self.intake["id"])

    def test_live_journal_tampering_cannot_be_resigned_or_exposed(self):
        with self.s.connect() as db:
            event = json.loads(
                db.execute("SELECT envelope FROM events WHERE sequence=1").fetchone()[0]
            )
            event["payload"]["reason"] = "PRIVATE-MAINTEC-CANARY"
            db.execute(
                "UPDATE events SET envelope=? WHERE sequence=1",
                (canonical(event).decode(),),
            )
            db.commit()
        with self.assertRaises(ValueError):
            self.s.export_session(self.token)

    def test_no_implicit_filler_or_padding_rules(self):
        from lightyear_mainframe.zos_compare import compare_records

        b = dict(keys=[], timestamp_fields=[])
        a = [dict(fields=[dict(path="FILLER", value="a ", filler=True)])]
        c = [dict(fields=[dict(path="FILLER", value="a", filler=True)])]
        self.assertFalse(compare_records(a, c, b)["identical"])


if __name__ == "__main__":
    unittest.main()
