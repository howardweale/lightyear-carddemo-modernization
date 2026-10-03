"""Zero-model security regressions. Linux tests use real files, locks and signatures."""

import base64
import concurrent.futures
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from lightyear_judge.policy import disclosure, project, fingerprint
from lightyear_control_tower.decisions import canonical, digest, verify_envelope
from lightyear_control_tower.status_export import atomic_new
from lightyear_mainframe.zos_evidence import read_json


class PolicyTests(unittest.TestCase):
    def test_non_fixture_cannot_enable_fields(self):
        self.assertEqual("confidential", disclosure({}))
        self.assertEqual("confidential", disclosure({"fixture": False}))
        self.assertEqual("field", disclosure({"fixture": True}))
        for config in (
            {"fixture": "false"},
            {"disclosure_mode": "field"},
            {"disclosure_mode": "unknown"},
        ):
            with self.assertRaises(ValueError):
                disclosure(config)

    def test_deliberate_field_band_kind_encoding_collapses(self):
        for field in ("SECRET-ACCOUNT", "SECRET-BALANCE"):
            for kind in ("value-differs", "missing-record", "abend"):
                for count in ("1", "2-10", ">10"):
                    raw = [
                        {
                            "dataset": "STEP15/ACCTFILE",
                            "field": field,
                            "kind": kind,
                            "count_band": count,
                        }
                    ]
                    self.assertEqual(
                        [{"dataset": "STEP15/ACCTFILE", "kind": "differs"}],
                        project(raw * 3, "confidential"),
                    )
        with self.assertRaises(ValueError):
            project([{"dataset": "SECRET"}], "confidential")

    def test_fingerprint_assets_bwrap_and_whole_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [
                root / "src/lightyear_judge/test.py",
                root / "spec/mainframe/test.cpy",
                root / "bwrap",
                root / "runtime/bin/java",
                root / "runtime/lib/modules",
            ]
            for p in paths:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"original")
            with patch(
                "lightyear_judge.policy.shutil.which",
                side_effect=lambda name: str(
                    root / ("bwrap" if name == "bwrap" else "runtime/bin/java")
                ),
            ):
                original = fingerprint(root / "src")
                for p in paths:
                    p.write_bytes(b"changed")
                    self.assertNotEqual(original, fingerprint(root / "src"), p)
                    p.write_bytes(b"original")


@unittest.skipUnless(os.name == "posix", "Real Linux process locks required")
class ServiceTests(unittest.TestCase):
    def setUp(self):
        from lightyear_judge import service

        self.service = service
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.eval = self.base / "evaluation"
        self.eval.mkdir()
        (self.eval / "input").write_bytes(b"protected-value-82746")
        self.tower = self.base / "tower"
        self.tower.mkdir()
        for name, value in (
            ("require_isolation", None),
            ("require_trusted_installation", None),
            ("implementation", {"test": "a" * 64}),
        ):
            p = patch.object(service, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = patch(
            "lightyear_judge.ledger.ledger_directory", return_value=self.base / "ledger"
        )
        p.start()
        self.addCleanup(p.stop)

    def judge(self, name="task", **extra):
        root = self.base / name
        config = dict(
            task_id=name,
            evaluation=str(self.eval),
            agent_uid=65534,
            exports=str(self.tower / (name + "-exports")),
            tower_workspace=str(self.tower),
            public_task={},
            **extra,
        )
        self.service.initialize(root, config)
        j = self.service.Judge(root, task=name)
        self.addCleanup(j.close)
        return j

    def reserve(self, j, status="equipment-failure"):
        attempt = "attempt-" + uuid.uuid4().hex
        reservation = j.ledger.reserve(j.config["content_sha256"], attempt)
        from lightyear_toolkit.workspace import sha

        artifact = j.root / "artifacts" / (attempt + ".jar")
        artifact.parent.mkdir(exist_ok=True)
        artifact.write_bytes(b"PKsynthetic")
        accepted = j.append(
            "accepted",
            attempt_id=attempt,
            attempt_number=len(j.accepted()) + 1,
            request_id=str(uuid.uuid4()),
            artifact_sha256=sha(artifact.read_bytes()),
            inventory_reservation=reservation,
        )
        j.finish(accepted, "indeterminate", [], [], status)
        return attempt

    def test_new_task_and_concurrent_reservations_share_budget(self):
        one = self.judge()
        two = self.judge("other", submissions=100, attempt_slots=100)

        def reserve(n):
            try:
                (one if n % 2 else two).ledger.reserve("f" * 64, str(n))
                return True
            except ValueError:
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            self.assertEqual(5, sum(pool.map(reserve, range(30))))
        self.assertEqual(0, one.budget()["submissions_left"])
        self.assertEqual(0, two.budget()["submissions_left"])
        self.assertEqual(0, self.judge("third").budget()["submissions_left"])

    def test_two_processes_cannot_overbook_inventory(self):
        import subprocess
        import sys

        j = self.judge()
        code = """from pathlib import Path
import sys
from lightyear_judge.ledger import Ledger
ledger = Ledger(sys.argv[2], 100, directory=Path(sys.argv[1]))
for i in range(5):
    try:
        ledger.reserve('a' * 64, sys.argv[3] + str(i))
        print('accepted', flush=True)
    except ValueError:
        print('refused', flush=True)
"""
        args = [
            sys.executable,
            "-c",
            code,
            str(self.base / "ledger"),
            j.config["evaluation_inventory_sha256"],
        ]
        processes = [
            subprocess.Popen(
                args + [str(n)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            for n in range(2)
        ]
        accepted = 0
        for process in processes:
            out, err = process.communicate(timeout=15)
            self.assertEqual(0, process.returncode, err)
            accepted += out.count(b"accepted")
        self.assertEqual(5, accepted)
        self.assertEqual((5, 5), j.ledger.budget())

    def test_async_pending_idempotency_confidential_receipts(self):
        j = self.judge()
        gate = threading.Event()
        self.addCleanup(gate.set)

        def worker(*args, **kwargs):
            gate.wait(5)
            attempt = args[0][-1]
            atomic_new(
                j.root / "worker-results" / (attempt + ".json"),
                j.signer.sign(
                    dict(
                        task=j.config["content_sha256"],
                        attempt_id=attempt,
                        verdict="divergent",
                        runs=[],
                        diagnostics=[
                            dict(
                                dataset="STEP15/ACCTFILE",
                                field="SECRET",
                                kind="value-differs",
                                count_band=">10",
                            )
                        ],
                    )
                ),
            )

        with patch.object(self.service.subprocess, "run", side_effect=worker):
            args = dict(
                request_id=str(uuid.uuid4()),
                artifact=base64.b64encode(b"PKjar").decode(),
            )
            result = j.invoke("submit_candidate", args)
            self.assertTrue(result["ok"], result)
            attempt = result["attempt_id"]
            self.assertEqual(
                "pending", j.invoke("get_verdict", {"attempt_id": attempt})["verdict"]
            )
            self.assertEqual(4, j.invoke("get_budget", {})["submissions_left"])
            self.assertEqual(attempt, j.invoke("submit_candidate", args)["attempt_id"])
            self.assertFalse(
                j.invoke(
                    "submit_candidate",
                    {**args, "artifact": base64.b64encode(b"PKother").decode()},
                )["ok"]
            )
            gate.set()
            j.pool.shutdown(wait=True)
        public = j.invoke("get_receipt", {"attempt_id": attempt})["receipt"]
        self.assertTrue(verify_envelope(public, j.signer.public))
        self.assertNotIn("SECRET", json.dumps(public))
        self.assertNotIn("evidence_sha256", public)
        self.assertEqual(
            [{"dataset": "STEP15/ACCTFILE", "kind": "differs"}], public["diagnostics"]
        )
        self.assertFalse(
            j.invoke(
                "propose_normalization",
                dict(attempt_id=attempt, dataset="STEP15/ACCTFILE", field="SECRET"),
            )["ok"]
        )

    def test_invalid_and_unauthenticated_flood_is_bounded(self):
        from lightyear_judge.http import create_server
        import http.client

        j = self.judge()
        before = len(j.events)
        for _ in range(3000):
            j.invoke("bogus", {})
            j.ingress("unauthorized")
        self.assertEqual(before, len(j.events))
        self.assertEqual({"invalid", "unauthorized"}, set(j.ingress_counts))
        server = create_server(j)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            client = http.client.HTTPConnection("127.0.0.1", server.server_port)
            client.request(
                "POST",
                "/get_budget",
                body="{}",
                headers={"Authorization": "Bearer " + j.token},
            )
            self.assertEqual(429, client.getresponse().status)
            client.close()
            client = http.client.HTTPConnection("127.0.0.1", server.server_port)
            client.request(
                "POST", "/get_budget", body="{}", headers={"Authorization": "\xff"}
            )
            self.assertEqual(401, client.getresponse().status)
            client.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        j.flush_ingress(force=True)
        self.assertEqual(before + 1, len(j.events))

    def console(self, scope):
        from lightyear_control_tower.console import ConsoleService, provision

        authority = self.base / "console/authority.json"
        credential = provision(authority, scope, "howard", "Howard").read_text().strip()
        console = ConsoleService(self.tower, authority)
        self.addCleanup(console.close)
        console.grant_roles(
            "howard", ["operator", "campaign-authorizer"], reason="Test fixture"
        )
        return console, console.login(credential)["token"]

    def decide(self, console, token, attempt, outcome):
        item = console.review(token, "review-" + attempt)
        e = console.decide(
            token,
            dict(
                item_id=item["id"],
                bound=item["bound"],
                outcome=outcome,
                reason="Investigated synthetic interruption",
                previous_decision_sha256=None,
                request_id=str(uuid.uuid4()),
            ),
        )
        proof = console.proof(token, e["content_sha256"])
        return proof, proof["journal"]["journal_head_sha256"]

    def test_tower_continue_void_are_receipt_bound_and_consume_attempts(self):
        from lightyear_judge.review import queue_decision

        console, token = self.console("task")
        j = self.judge(tower_public_key=console.public_key.decode())
        for outcome in ("continue", "void"):
            attempt = self.reserve(j)
            self.assertTrue(j.unresolved())
            proof, head = self.decide(console, token, attempt, outcome)
            with self.assertRaises(ValueError):
                queue_decision(j.root, attempt, proof, "0" * 64)
            queue_decision(j.root, attempt, proof, head)
            j.consume_decisions()
            self.assertFalse(j.unresolved())
            self.assertEqual("equipment-failure", j.receipt(attempt)["status"])
        self.assertEqual(3, j.budget()["submissions_left"])
        other = self.reserve(j)
        with self.assertRaises(ValueError):
            queue_decision(j.root, other, proof, head)
        replay = self.service.replay(
            j.root, j.signer.public, j.events[-1]["content_sha256"]
        )
        self.assertEqual(3, replay["attempts"])

    def test_only_signed_tower_grant_can_raise_cumulative_budget(self):
        from lightyear_judge.review import inventory_budget

        console, token = self.console("task")
        j = self.judge(tower_public_key=console.public_key.decode())
        self.reserve(j)
        requested = inventory_budget(j.root, 7)
        item = console.review(token, requested["request_id"])
        event = console.decide(
            token,
            dict(
                item_id=item["id"],
                bound=item["bound"],
                outcome="approved",
                reason="Explicit synthetic grant",
                previous_decision_sha256=None,
                request_id=str(uuid.uuid4()),
            ),
        )
        proof = console.proof(token, event["content_sha256"])
        head = proof["journal"]["journal_head_sha256"]
        with self.assertRaises(ValueError):
            inventory_budget(j.root, 8, proof=proof, expected_head=head)
        with self.assertRaises(ValueError):
            inventory_budget(j.root, 7, proof=proof)
        inventory_budget(j.root, 7, proof=proof, expected_head=head)
        self.assertEqual((7, 1), j.ledger.budget())
        self.assertEqual(
            4, j.budget()["submissions_left"], "Task's original limit remains"
        )
        with self.assertRaises(ValueError):
            inventory_budget(j.root, 7, proof=proof, expected_head=head)
        fresh = self.judge("fresh", attempt_slots=100, submissions=100)
        self.assertEqual(6, fresh.budget()["submissions_left"])

    def test_restart_consumes_interruption_and_preserves_pending_review(self):
        j = self.judge()
        attempt = "attempt-" + uuid.uuid4().hex
        reservation = j.ledger.reserve(j.config["content_sha256"], attempt)
        j.append(
            "accepted",
            attempt_id=attempt,
            attempt_number=1,
            request_id=str(uuid.uuid4()),
            artifact_sha256="a" * 64,
            inventory_reservation=reservation,
        )
        j.close()
        restarted = self.service.Judge(j.root, task="task")
        self.addCleanup(restarted.close)
        self.assertEqual("interrupted", restarted.receipt(attempt)["status"])
        self.assertEqual(4, restarted.budget()["submissions_left"])
        self.assertTrue(restarted.unresolved())
        self.assertTrue(
            (
                self.tower
                / "work/control-tower/requests/task"
                / ("review-" + attempt + ".json")
            ).exists()
        )

    def test_completed_receipt_cannot_be_operator_voided(self):
        from lightyear_judge.review import queue_decision

        console, token = self.console("task")
        j = self.judge(tower_public_key=console.public_key.decode())
        attempt = self.reserve(j)
        proof, head = self.decide(console, token, attempt, "void")
        receipt = j.receipt(attempt)
        body = {
            k: v for k, v in receipt.items() if k not in {"signature", "content_sha256"}
        }
        body["status"] = "completed"
        (j.root / "receipts" / (attempt + ".json")).write_bytes(
            canonical(j.signer.sign(body))
        )
        with self.assertRaises(ValueError):
            queue_decision(j.root, attempt, proof, head)

    def test_unknown_receipt_is_rejected_before_filesystem_read(self):
        j = self.judge()
        with patch.object(self.service, "read_json") as read:
            with self.assertRaisesRegex(ValueError, "attempt-unavailable"):
                j.public_receipt("../../secret")
            read.assert_not_called()

    def test_runtime_change_refused_before_reservation(self):
        j = self.judge()
        with patch.object(
            self.service, "implementation", return_value={"changed": True}
        ):
            self.assertFalse(
                j.invoke(
                    "submit_candidate",
                    dict(request_id=str(uuid.uuid4()), artifact="UEtqYXI="),
                )["ok"]
            )
        self.assertEqual(5, j.budget()["submissions_left"])


if __name__ == "__main__":
    unittest.main()
