"""Round-one and round-two regression attacks; disposable authorities only."""

import copy
import contextlib
import io
import hashlib
import json
import os
import socket
import threading
import time
import unittest
import uuid
from datetime import date, timedelta
from unittest.mock import patch

from tests import test_decision_console_workflows as fixtures
from lightyear_control_tower.console import ConsoleService, provision
from lightyear_control_tower.decisions import (
    canonical,
    digest,
    DecisionUnauthorized,
    utcnow,
)
from lightyear_control_tower.requests import confined, read_bytes
from lightyear_control_tower.verification import (
    verify_decision,
    DecisionVerificationError,
)
from lightyear_control_tower.workspaces import verify_export
from lightyear_control_tower.workflows import rule_register
from lightyear_control_tower.catalogue import (
    read_catalogue,
    publish_record,
    consistency,
)
from lightyear_control_tower.controller_decisions import (
    TowerControllerV2,
    pause_evidence,
)
from lightyear_control_tower.server import ConsoleAPI, create_server
from lightyear_control_tower.client import ConsoleClient
from lightyear_control_tower.mcp import TowerTools


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.WorkflowTests(
            "test_two_exact_release_decisions_offline_verify_and_tamper"
        )
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.s = self.f.service

    def annotate(self, text):
        item = self.s.inbox.item("launch")
        return self.s.propose(
            self.f.token,
            "annotation",
            {
                "item_id": "launch",
                "bound": item["bound"],
                "text": text,
                "request_id": str(uuid.uuid4()),
            },
        )

    def release(self):
        self.f.request("release", "evidence-release", {"archive": self.f.bundle()})
        customer = self.f.actor("customer", ["customer-sponsor"], kind="customer")
        self.annotate("UNAPPROVED BEFORE RELEASE customer balance 98765.43")
        self.f.decide(customer, "release", "approved", decision_slot="customer-sponsor")
        self.f.decide(
            self.f.token, "release", "approved", decision_slot="campaign-authorizer"
        )
        return self.f.workspace.export(self.f.token, "release")

    def test_release_is_frozen_and_exposes_only_approved_members_and_release_events(
        self,
    ):
        released = self.release()
        original = canonical(released)
        self.assertNotIn(b"UNAPPROVED BEFORE RELEASE", original)
        self.annotate("UNAPPROVED AFTER RELEASE customer balance 22222.22")
        self.assertEqual(
            original, canonical(self.f.workspace.export(self.f.token, "release"))
        )
        self.assertNotIn(b"UNAPPROVED AFTER RELEASE", original)
        self.assertEqual(
            "verified", verify_export(released, self.s.public_key)["status"]
        )
        self.assertEqual(2, len(released["release_decisions"]))
        self.assertTrue(
            all(
                e["payload"]["kind"] == "evidence-release"
                for e in released["release_decisions"].values()
            )
        )
        bad = copy.deepcopy(released)
        bad["decision_prefix"][0]["content_sha256"] = "f" * 64
        bad = self.s.sign(
            {k: v for k, v in bad.items() if k not in {"signature", "content_sha256"}}
        )
        with self.assertRaises(DecisionVerificationError):
            verify_export(bad, self.s.public_key)

    def test_release_second_role_same_actor_refused_before_journaling(self):
        self.f.request("release", "evidence-release", {"archive": self.f.bundle()})
        customer = self.f.actor(
            "customer", ["customer-sponsor", "campaign-authorizer"], kind="customer"
        )
        self.f.decide(customer, "release", "approved", decision_slot="customer-sponsor")
        payload = self.f.payload(customer, "release", "approved")
        payload["decision_slot"] = "campaign-authorizer"
        before = self.s.export_session(self.f.token)["events"]
        with self.assertRaises(DecisionUnauthorized):
            self.s.decide(customer, payload)
        self.assertEqual(before, self.s.export_session(self.f.token)["events"])

    def test_inbox_author_spoof_cannot_produce_independent_approval(self):
        self.f.technical()
        author = self.f.actor("author", ["technical-reviewer"])
        path = self.f.root / "work/control-tower/requests/demo/technical.json"
        request = json.loads(path.read_bytes())
        request.update(proposed_by="someone-else", authored_by=[])
        path.write_bytes(canonical(request))
        with self.assertRaisesRegex(DecisionUnauthorized, "independent"):
            self.f.decide(author, "technical", "approved")
        request.pop("proposal_sha256")
        path.write_bytes(canonical(request))
        reviewer = self.f.actor("reviewer", ["technical-reviewer"])
        with self.assertRaisesRegex(DecisionUnauthorized, "authenticated-proposal"):
            self.f.decide(reviewer, "technical", "approved")

    def test_rule_file_spoof_does_not_match_the_authenticated_proposal(self):
        item = self.f.technical()
        path = self.f.root / item["evidence"]["rule"]
        rule = json.loads(path.read_bytes())
        rule["proposed_by"] = "somebody-else"
        path.write_bytes(canonical(rule))
        reqpath = self.f.root / "work/control-tower/requests/demo/technical.json"
        req = json.loads(reqpath.read_bytes())
        req["bound"]["rule"] = hashlib.sha256(path.read_bytes()).hexdigest()
        reqpath.write_bytes(canonical(req))
        reviewer = self.f.actor("reviewer", ["technical-reviewer"])
        with self.assertRaisesRegex(DecisionUnauthorized, "proposal-rule-mismatch"):
            self.f.decide(reviewer, "technical", "approved")

    def test_rejection_on_new_request_revokes_same_authorization_subject(self):
        authorized = self.s.decide(self.f.token, self.f.payload())
        self.f.make_request(name="another-launch")
        self.s.decide(
            self.f.token, self.f.payload(item_id="another-launch", outcome="rejected")
        )
        proof = self.s.proof(self.f.token, authorized["content_sha256"])
        with self.assertRaisesRegex(DecisionVerificationError, "decision-superseded"):
            verify_decision(
                proof,
                self.s.public_key,
                "campaign-authorization",
                authorized["payload"]["bound"],
            )

    def test_qualification_uses_separate_key_through_acceptance_reader_and_publisher(
        self,
    ):
        other = fixtures.WorkflowTests(
            "test_two_exact_release_decisions_offline_verify_and_tamper"
        )
        other.setUp()
        self.addCleanup(other.doCleanups)
        self.assertNotEqual(self.s.public_key, other.service.public_key)
        qualification, item = self.f.qualification(signer=other.service)
        qa = self.f.actor("qa", ["qualification-approver"])
        event = self.f.decide(qa, "accept", "accepted")
        proof = self.s.proof(self.f.token, event["content_sha256"])
        bindings = {
            "platform_major": "1",
            "adapter_sha256": "a" * 64,
            "judge_version": "1",
            "rule_register_major": 1,
        }
        entry = {
            "id": "lane",
            "source_lane": "source",
            "target_lane": "target",
            "status": "qualified",
            "record": item["evidence"]["qualification"],
            "record_sha256": item["bound"]["qualification"],
            "acceptance": proof,
            "acceptance_bound": event["payload"]["bound"],
            "bindings": bindings,
        }
        data = {
            "entries": [entry],
            "current_bindings": {"lane": bindings},
            "pending_bindings": {"lane": {"platform_major": "2"}},
        }
        source = self.f.root / "publisher.json"
        source.write_bytes(canonical(data))
        from tools.catalogue_publish import main

        self.s.close()
        main(
            [
                "--root",
                str(self.f.root),
                "--authority",
                str(self.f.authority),
                "--input",
                str(source),
            ]
        )
        self.s = self.f.service = ConsoleService(self.f.root, self.f.authority)
        self.addCleanup(self.s.close)
        self.f.token = self.s.login(self.f.credential)["token"]
        fixtures.WorkflowValidation(self.s)
        qa = self.s.login(self.f.actor_credentials["qa"])["token"]
        view = read_catalogue(
            self.f.root, self.s.public_key, qualification_key=other.service.public_key
        )
        self.assertEqual(["platform_major"], view["entries"][0]["upcoming_expiry"])
        consistency(
            self.f.root,
            self.s.public_key,
            self.f.root / "docs/catalogue/lanes.public.json",
            self.f.root / "website-any-system/data/catalogue.json",
            qualification_key=other.service.public_key,
        )
        with self.assertRaisesRegex(
            DecisionVerificationError, "invalid-qualification-signature"
        ):
            read_catalogue(
                self.f.root, self.s.public_key, qualification_key=self.s.public_key
            )
        self.f.request(
            "reject-same-qualification",
            "qualification-acceptance",
            {
                "qualification": qualification,
                "replay": json.loads(
                    (self.f.root / item["evidence"]["replay"]).read_bytes()
                ),
            },
        )
        self.f.decide(qa, "reject-same-qualification", "rejected")
        stale = self.s.proof(self.f.token, event["content_sha256"])
        with self.assertRaisesRegex(DecisionVerificationError, "decision-superseded"):
            verify_decision(
                stale,
                self.s.public_key,
                "qualification-acceptance",
                event["payload"]["bound"],
            )

    def test_authority_and_trust_cannot_be_engine_evidence(self):
        original = self.f.authority.read_bytes()
        try:
            for field in ("private_key", "public_key"):
                config = json.loads(original)
                config[field] = str(self.f.root / "unsafe-key.pem")
                self.f.authority.write_bytes(canonical(config))
                with self.assertRaisesRegex(ValueError, "outside"):
                    ConsoleService(self.f.root, self.f.authority)
        finally:
            self.f.authority.write_bytes(original)
        from lightyear_control_tower.cli import main

        before = self.s.export_session(self.f.token)["events"]
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as refused,
        ):
            main(
                [
                    "add-identity",
                    "--root",
                    str(self.f.root),
                    "--authority",
                    str(self.f.authority),
                    "--operator-id",
                    "unsafe",
                    "--operator-name",
                    "Unsafe destination",
                    "--credential-output",
                    str(self.f.root / "credential.txt"),
                ]
            )
        self.assertEqual(2, refused.exception.code)
        self.assertEqual(before, self.s.export_session(self.f.token)["events"])
        self.assertFalse((self.f.root / "credential.txt").exists())
        for path in (
            "control-tower/qualification-trust.json",
            "private/authority.json",
            "work/control-tower/authority.json",
        ):
            with self.assertRaises(ValueError):
                confined(self.f.root, path)
        inside = self.f.root / "private/authority.json"
        provision(inside, "demo", "x", "x")
        with self.assertRaisesRegex(ValueError, "outside"):
            ConsoleService(self.f.root, inside)
        self.f.qualification()
        config = self.f.authority.parent / "qualification-trust.json"
        config.write_bytes(
            canonical({"scope": "demo", "public_key": str(self.f.root / "key.pem")})
        )
        with self.assertRaisesRegex(ValueError, "outside"):
            self.s.qualification_key()

    def test_rule_membership_versions_review_queue_and_catalogue_dependency_warning(
        self,
    ):
        self.assertEqual(1, rule_register(self.s, self.f.token)["major_version"])
        self.f.technical()
        tech = self.f.actor("reviewer", ["technical-reviewer"])
        reviewed = self.f.decide(tech, "technical", "approved")
        self.f.request(
            "business",
            "rule-approval",
            {
                "rule": self.f.rule(),
                "technical_review": self.s.proof(
                    self.f.token, reviewed["content_sha256"]
                ),
                "workload": {"id": "cards"},
            },
            workload="cards",
        )
        owner = self.f.actor("owner", ["business-owner"], workloads=["cards"])
        self.f.decide(
            owner,
            "business",
            "approved",
            named_owner="Finance",
            review_after=self.f.rule()["review_after"],
        )
        register = rule_register(self.s, self.f.token)
        self.assertEqual(2, register["major_version"])
        _, item = self.f.qualification()
        qa = self.f.actor("qa", ["qualification-approver"])
        accepted = self.f.decide(qa, "accept", "accepted")
        proof = self.s.proof(self.f.token, accepted["content_sha256"])
        bindings = {
            "platform_major": "1",
            "adapter_sha256": "a" * 64,
            "judge_version": "1",
            "rule_register_major": 2,
        }
        rule_hash = digest(self.f.rule())
        entry = {
            "id": "lane",
            "status": "qualified",
            "source_lane": "source",
            "target_lane": "target",
            "record": item["evidence"]["qualification"],
            "record_sha256": item["bound"]["qualification"],
            "acceptance": proof,
            "acceptance_bound": accepted["payload"]["bound"],
            "bindings": bindings,
            "rule_dependencies": [rule_hash],
        }
        catalog = publish_record(
            [entry],
            scope=self.f.scope,
            signer=self.s,
            decision_head=proof["journal"]["journal_head_sha256"],
            current_bindings={"lane": bindings},
            pending_bindings={"lane": {"judge_version": "2"}},
            rule_register=register,
        )
        (self.f.root / "catalog").mkdir()
        (self.f.root / "catalog/lanes.json").write_bytes(canonical(catalog))
        future = date.today() + timedelta(days=100)
        row = read_catalogue(
            self.f.root,
            self.s.public_key,
            qualification_key=self.s.qualification_key(),
            now=future,
        )["entries"][0]
        self.assertEqual([rule_hash], row["review_due"])
        self.assertEqual(["judge_version"], row["upcoming_expiry"])
        self.assertEqual("qualified", row["status"])

        class FutureDate(date):
            @classmethod
            def today(cls):
                return future

        with patch("lightyear_control_tower.workflows.date", FutureDate):
            queue = ConsoleAPI(self.s).read("queue", self.f.token, {})
            due = [r for r in queue["items"] if r["status"] == "review due"]
            self.assertEqual(1, len(due))
            self.assertFalse(due[0]["decidable"])
        self.f.request(
            "renew",
            "rule-retirement",
            {"rule": self.f.rule(), "workload": {"id": "cards"}},
            workload="cards",
        )
        self.f.decide(
            owner,
            "renew",
            "renewed",
            named_owner="Finance",
            review_after=(date.today() + timedelta(days=180)).isoformat(),
        )
        renewed = rule_register(self.s, self.f.token, now=future)
        self.assertEqual(2, renewed["major_version"])
        self.assertFalse(renewed["rules"][0]["review_due"])
        self.f.request(
            "retire",
            "rule-retirement",
            {"rule": self.f.rule(), "workload": {"id": "cards"}},
            workload="cards",
        )
        self.f.decide(
            owner,
            "retire",
            "retired",
            named_owner="Finance",
            review_after=self.f.rule()["review_after"],
        )
        retired = rule_register(self.s, self.f.token)
        self.assertEqual(3, retired["major_version"])
        self.assertEqual([], retired["rules"])
        current_proof = self.s.proof(self.f.token, accepted["content_sha256"])
        expired = publish_record(
            [{**entry, "acceptance": current_proof}],
            scope=self.f.scope,
            signer=self.s,
            decision_head=current_proof["journal"]["journal_head_sha256"],
            current_bindings={"lane": {**bindings, "rule_register_major": 3}},
            rule_register=retired,
        )
        self.assertEqual("expired", expired["entries"][0]["status"])
        self.assertEqual(
            [rule_hash], expired["entries"][0]["unavailable_rule_dependencies"]
        )

    @unittest.skipIf(
        os.name == "nt",
        "POSIX FIFO attack; Windows reparse and replacement tested separately",
    )
    def test_fifo_refuses_promptly_and_never_blocks_writer(self):
        path = self.f.root / "fifo"
        os.mkfifo(path)
        started = time.monotonic()
        with self.assertRaises(ValueError):
            read_bytes(path)
        self.assertLess(time.monotonic() - started, 1)
        self.annotate("writer remains available")

    def test_all_evidence_hash_reads_happen_outside_writer_lock(self):
        import lightyear_control_tower.requests as requests

        original = requests.read_bytes

        def checked(path):
            self.assertFalse(self.s.lock._is_owned(), str(path))
            return original(path)

        with patch.object(requests, "read_bytes", checked):
            self.s.queue(self.f.token)
            self.s.review(self.f.token, "launch")
            self.s.decide(self.f.token, self.f.payload())

    def test_review_after_upper_bound_and_logout_without_write_roles(self):
        payload = self.f.payload()
        payload["review_after"] = "9999-12-31"
        with self.assertRaisesRegex(ValueError, "maximum"):
            self.s.decide(self.f.token, payload)
        api = ConsoleAPI(self.s)
        for name, roles in (
            ("audit", ["auditor"]),
            ("partner", ["partner-viewer"]),
            ("none", []),
        ):
            token = self.f.actor(name, roles)
            self.assertEqual("ended", api.write("logout", token, {})["status"])
            with self.assertRaises(DecisionUnauthorized):
                self.s.authenticate(token)

    def test_mcp_refreshes_expired_sessions_and_labels_agent_role(self):
        credential = self.s.add_identity("bot", "bot", identity_kind="agent")
        self.s.grant_roles("bot", ["agent"], reason="test")
        tools = TowerTools(self.s, credential)
        old = tools.token
        tools.expires_at = utcnow() - timedelta(seconds=1)
        self.s.sessions[old]["expires_at"] = tools.expires_at.isoformat()
        self.assertEqual("demo", tools.queue()["scope"])
        self.assertNotEqual(old, tools.token)
        human_agent = self.f.actor("human-agent", ["agent"])
        item = self.s.inbox.item("launch")
        p = self.s.propose(
            human_agent,
            "annotation",
            {
                "item_id": "launch",
                "bound": item["bound"],
                "text": "draft",
                "request_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual("prepared by agent", p["payload"]["label"])

    def test_each_pause_requires_its_own_resume_and_campaign_mismatch_refuses(self):
        auth = self.s.decide(self.f.token, self.f.payload())
        with self.assertRaisesRegex(
            DecisionVerificationError, "campaign-authorization-mismatch"
        ):
            TowerControllerV2(
                self.s.public_key, "demo", "f" * 64, auth["payload"]["bound"]
            )
        controller = TowerControllerV2(
            self.s.public_key,
            "demo",
            auth["payload"]["bound"]["campaign"],
            auth["payload"]["bound"],
        )

        def admitted():
            proof = self.s.proof(self.f.token, auth["content_sha256"])
            return controller.before_slot(
                proof, fresh_head=proof["journal"]["journal_head_sha256"]
            )

        pauses = []
        for name in ("pause-a", "pause-b"):
            req = self.f.make_request("measurement-validity", name)
            path = self.f.root / req["evidence"]["cause"]
            path.write_bytes(canonical({"cause": name}))
            req["bound"]["cause"] = hashlib.sha256(path.read_bytes()).hexdigest()
            (self.f.root / f"work/control-tower/requests/demo/{name}.json").write_bytes(
                canonical(req)
            )
            pauses.append(self.f.decide(self.f.token, name, "pause"))
        self.f.make_request("measurement-validity", "unrelated")
        self.f.decide(self.f.token, "unrelated", "continue")
        for index, pause in enumerate(pauses):
            with self.assertRaisesRegex(DecisionVerificationError, "campaign-paused"):
                admitted()
            name = "resume-" + str(index)
            req = self.f.make_request("resume", name)
            raw = pause_evidence(pause)
            (self.f.root / req["evidence"]["pause"]).write_bytes(raw)
            req["bound"]["pause"] = hashlib.sha256(raw).hexdigest()
            (self.f.root / f"work/control-tower/requests/demo/{name}.json").write_bytes(
                canonical(req)
            )
            self.f.decide(self.f.token, name, "resume")
        self.assertEqual("admitted", admitted()["status"])

    def test_http_short_body_and_nested_json_fail_closed_with_catch_all_500(self):
        with patch("lightyear_control_tower.server.SOCKET_TIMEOUT", 0.2):
            http = create_server(self.s, port=0)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        address = ("127.0.0.1", http.server_port)

        def send(body, size):
            with socket.create_connection(address, timeout=2) as sock:
                headers = (
                    f"POST /api/tower/session HTTP/1.1\r\nHost: 127.0.0.1:{http.server_port}\r\n"
                    f"Origin: http://127.0.0.1:{http.server_port}\r\nContent-Type: application/json\r\nContent-Length: {size}\r\n\r\n"
                )
                sock.sendall(headers.encode() + body)
                return sock.recv(4096)

        self.assertIn(b"408", send(b"{", 100))
        nested = b"[" * 3000 + b"]" * 3000
        # JSON recursion thresholds differ between CPython versions/platforms.
        # A parsed non-object is a 422; a parser RecursionError must return 500,
        # never drop the connection. Exercise that branch deterministically too.
        self.assertRegex(send(nested, len(nested)), rb"^HTTP/1\.0 (422|500) ")
        with patch(
            "lightyear_control_tower.server.json.loads", side_effect=RecursionError
        ):
            self.assertIn(b"500", send(b"{}", 2))


if __name__ == "__main__":
    unittest.main()
