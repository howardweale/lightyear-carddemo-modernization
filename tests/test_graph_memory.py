"""Offline security cases: synthetic signed events, never model/Docker calls."""

import copy
import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from lightyear_control_tower.decisions import canonical, digest
from lightyear_control_tower.console import ConsoleService, provision
from lightyear_mainframe.zos_evidence import initialize_key, Signer
from lightyear_factory.annotations import (
    AnnotationLedger,
    annotation,
    leak_certificate,
    retrieve,
    outcome_summary,
)
from lightyear_factory.annotation_tools import (
    review_request,
    propose,
    repair_proposal,
    import_reviews,
    governor_requests,
)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "data"
        self.root.mkdir()
        self.now = datetime.now(timezone.utc)
        self.expiry = (self.now + timedelta(days=10)).date().isoformat()
        for key in ("ledger", "judge"):
            initialize_key(self.root / (key + ".pem"))
        self.signer = Signer(self.root / "ledger.pem")
        self.judge = Signer(self.root / "judge.pem")
        authority = self.root.parent / "authority/authority.json"
        credential = (
            provision(authority, "graph-memory", "howard", "Howard").read_text().strip()
        )
        self.console = ConsoleService(self.root, authority)
        self.addCleanup(self.console.close)
        self.console.grant_roles(
            "howard",
            ["operator", "knowledge-approver", "campaign-authorizer"],
            reason="Synthetic test",
        )
        self.token = self.console.login(credential)["token"]
        self.ledger = AnnotationLedger(
            self.root / "ledger.jsonl",
            self.signer.public,
            tower_key=self.console.public_key,
            judge_key=self.judge.public,
            scope="graph-memory",
            inventory_sha256="a" * 64,
        )

    def body(self, **kw):
        return (
            dict(
                customer_id="public",
                anchors=["paragraph"],
                scope="node",
                type="convention",
                text="Use the approved rounding convention.",
                source="human-review",
                provenance="observed",
                evidence=[],
                visibility="implementer",
                portable=False,
                review_after=self.expiry,
                created_by="operator",
                **kw,
            )
            if not kw
            else {**self.body(), **kw}
        )

    def create(self, **kw):
        a = annotation(self.body(**kw))
        self.ledger.append("create", dict(annotation=a), self.signer)
        return a

    def proof(self, kind, assets, outcome, reason="Synthetic operator review"):
        request = review_request(self.root, "graph-memory", kind, assets)
        item = self.console.review(self.token, request["id"])
        event = self.console.decide(
            self.token,
            dict(
                item_id=item["id"],
                bound=item["bound"],
                outcome=outcome,
                reason=reason,
                named_owner="Howard",
                review_after=self.expiry,
                previous_decision_sha256=(item.get("latest_decision") or {}).get(
                    "content_sha256"
                ),
                request_id=str(uuid.uuid4()),
            ),
        )
        proof = self.console.proof(self.token, event["content_sha256"])
        return proof

    def approve(self, a, *, portable=False, values=()):
        cert = leak_certificate(
            a, values, self.judge, inventory_sha256="a" * 64, publish_portable=portable
        )
        proof = self.proof(
            "graph-annotation",
            dict(annotation=a, leak_check=cert),
            "approved",
            reason="publish-portable:" + digest(a) if portable else "Synthetic review",
        )
        p = dict(
            id=a["id"],
            leak_check=cert,
            proof=proof,
            trusted_head=proof["journal"]["journal_head_sha256"],
        )
        return self.ledger.append(
            "approve", p, self.signer, expected_head=p["trusted_head"]
        )

    def outcome(self, a, i, status="passed", **kw):
        context = dict(annotation_ids=[a["id"]], projection_sha256="b" * 64)
        body = dict(
            schema="annotation-outcome/1",
            customer_id=a["customer_id"],
            evaluation_class="public-calibration",
            independently_replayed=True,
            context=context,
            context_sha256=digest(context),
            run_id=str(i),
            status=status,
            anchors=a["anchors"],
            resolved_categories=[],
        )
        r = self.judge.sign({**body, **kw})
        return self.ledger.append("outcome", dict(id=a["id"], receipt=r), self.signer)

    def test_replay_tampering_order_and_partial_write(self):
        self.create()
        events = self.ledger.events()
        self.assertEqual(
            self.ledger.replay(), self.ledger.replay(copy.deepcopy(events))
        )
        events[0]["payload"]["annotation"]["text"] = "changed"
        with self.assertRaises(ValueError):
            self.ledger.replay(events)
        with self.assertRaises(ValueError):
            self.ledger.replay(self.ledger.events() * 2)
        self.ledger.path.write_bytes(self.ledger.path.read_bytes().rstrip())
        with self.assertRaises(ValueError):
            self.ledger.replay()

    def test_trust_cannot_be_granted_at_creation(self):
        for provenance in ("asserted", "verified"):
            with self.assertRaises(ValueError):
                self.create(provenance=provenance)
        with self.assertRaises(ValueError):
            self.create(created_by="agent:planner")
        self.create(created_by="agent:planner", provenance="inferred")

    def test_leak_blocks_approval(self):
        a = self.create(text="secret-value-123456")
        with self.assertRaises(ValueError):
            self.approve(a, values=["secret-value-123456"])
        self.assertEqual(self.ledger.replay()[a["id"]]["status"], "proposed")

    def test_human_promotion_and_failure_threshold(self):
        a = self.create()
        self.approve(a)
        for i in range(5):
            self.outcome(a, i)
        state = self.ledger.replay()[a["id"]]
        self.assertTrue(outcome_summary(state)["eligible_for_verified"])
        self.assertEqual(state["provenance"], "asserted")
        proof = self.proof(
            "graph-annotation-verified",
            dict(annotation=a, outcome_summary=outcome_summary(state)),
            "verified",
        )
        self.ledger.append(
            "approve",
            dict(
                id=a["id"],
                verified=True,
                proof=proof,
                trusted_head=proof["journal"]["journal_head_sha256"],
            ),
            self.signer,
            expected_head=proof["journal"]["journal_head_sha256"],
        )
        self.assertEqual(self.ledger.replay()[a["id"]]["provenance"], "verified")
        self.outcome(a, 5, "failed")
        self.assertFalse(outcome_summary(self.ledger.replay()[a["id"]])["flagged"])
        self.outcome(a, 6, "failed")
        self.assertEqual(
            retrieve(self.ledger.replay(), ["paragraph"], [], "public")["items"], []
        )

    def test_one_failure_prevents_promotion_duplicates_and_holdouts_refused(self):
        a = self.create()
        self.approve(a)
        for i in range(5):
            self.outcome(a, i)
        with self.assertRaises(ValueError):
            self.outcome(a, 0)
        with self.assertRaises(ValueError):
            self.outcome(a, 6, evaluation_class="sealed-holdout")
        with self.assertRaises(ValueError):
            self.outcome(a, 6, independently_replayed=False)
        with self.assertRaises(ValueError):
            self.outcome(a, 6, context_sha256="c" * 64)
        self.outcome(a, 5, "failed")
        self.assertFalse(
            outcome_summary(self.ledger.replay()[a["id"]])["eligible_for_verified"]
        )

    def test_retrieval_scope_customer_portable_expiry_cap(self):
        a = self.create(anchors=["program"], scope="subtree")
        self.approve(a)
        edges = [dict(source="program", target="paragraph", relation="CONTAINS")]
        self.assertEqual(
            len(
                retrieve(self.ledger.replay(), ["paragraph"], edges, "public")["items"]
            ),
            1,
        )
        self.assertFalse(
            retrieve(self.ledger.replay(), ["paragraph"], edges, "other")["items"]
        )
        b = self.create(text="A reviewed portable convention.")
        self.approve(b, portable=True)
        self.assertEqual(
            len(retrieve(self.ledger.replay(), ["paragraph"], edges, "other")["items"]),
            1,
        )
        self.assertFalse(
            retrieve(
                self.ledger.replay(),
                ["paragraph"],
                edges,
                "public",
                now=self.now + timedelta(days=11),
            )["items"]
        )
        result = retrieve(self.ledger.replay(), ["paragraph"], edges, "public", cap=64)
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(canonical(result)), 64)

    def test_inferred_private_and_node_order(self):
        a = self.create(provenance="inferred", created_by="agent:builder")
        self.assertFalse(
            retrieve(self.ledger.replay(), ["paragraph"], [], "public")["items"]
        )
        self.assertTrue(
            retrieve(
                self.ledger.replay(), ["paragraph"], [], "public", include_inferred=True
            )["items"]
        )
        self.create(
            provenance="inferred",
            visibility="inspector_private",
            text="private convention",
        )
        self.assertEqual(
            len(
                retrieve(
                    self.ledger.replay(),
                    ["paragraph"],
                    [],
                    "public",
                    include_inferred=True,
                )["items"]
            ),
            1,
        )

    def test_agent_tool_refuses_nonfactory(self):
        for kind in ("verify", "campaign"):
            with self.assertRaises(ValueError):
                propose(self.ledger, self.signer, self.body(), execution_kind=kind)
        with self.assertRaises(ValueError):
            propose(
                self.ledger, self.signer, self.body(), evaluation_class="sealed-holdout"
            )

    def test_review_import_binds_commit_lines_and_stays_inferred(self):
        graph = dict(
            nodes=[
                dict(
                    id="paragraph",
                    source=[dict(path="src/Interest.java", line_start=2, line_end=4)],
                )
            ]
        )
        c = dict(
            commit_id="commit",
            side="RIGHT",
            path="src/Interest.java",
            line=3,
            body="Review rounding.",
        )
        rows = import_reviews(
            self.ledger,
            self.signer,
            graph,
            [c, {**c, "commit_id": "other"}],
            self.body(),
            source_commit="commit",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            next(iter(self.ledger.replay().values()))["annotation"]["provenance"],
            "inferred",
        )

    def test_governor_emits_real_tower_request_without_promotion(self):
        a = self.create()
        self.approve(a)
        for i in range(5):
            self.outcome(a, i)
        rows = governor_requests(self.ledger, self.root, "graph-memory", {})
        self.assertEqual(rows[0]["kind"], "graph-annotation-verified")
        self.assertEqual(self.console.inbox.item(rows[0]["id"])["status"], "pending")
        self.assertEqual(self.ledger.replay()[a["id"]]["provenance"], "asserted")

    def test_retirement_closes_flagged_review(self):
        a = self.create()
        self.approve(a)
        for i in range(5):
            self.outcome(a, i, "failed" if i < 2 else "passed")
        summary = outcome_summary(self.ledger.replay()[a["id"]])
        cert = leak_certificate(a, [], self.judge, inventory_sha256="a" * 64)
        rows = governor_requests(
            self.ledger, self.root, "graph-memory", {a["id"]: cert}
        )
        self.assertEqual(len(rows), 1)
        proof = self.proof(
            "graph-annotation",
            dict(annotation=a, leak_check=cert, outcome_summary=summary),
            "retired",
        )
        head = proof["journal"]["journal_head_sha256"]
        self.ledger.append(
            "retire",
            dict(
                id=a["id"],
                leak_check=cert,
                outcome_summary=summary,
                proof=proof,
                trusted_head=head,
            ),
            self.signer,
            expected_head=head,
        )
        self.assertEqual(
            governor_requests(self.ledger, self.root, "graph-memory", {a["id"]: cert}),
            [],
        )


if __name__ == "__main__":
    unittest.main()
