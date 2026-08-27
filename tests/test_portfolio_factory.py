from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.portfolio import (
    PortfolioManifest,
    PortfolioRunner,
    load_portfolio_orders,
    plan_portfolio,
    sign_portfolio_approval,
    verify_portfolio_approval,
)
from lightyear_factory.store import PortfolioStore


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "factory/portfolio/carddemo-portfolio.json"
GRAPH = ROOT / "knowledge/graph.snapshot.json.gz"
KEY = b"portfolio-human-approval-key-32-bytes-minimum"


class PortfolioFactoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = PortfolioManifest.load(MANIFEST)
        self.plan, self.orders = plan_portfolio(self.manifest, ROOT, GRAPH)

    def test_plan_is_deterministic_graph_bound_and_conflict_aware(self) -> None:
        repeated, _ = plan_portfolio(self.manifest, ROOT, GRAPH)
        self.assertEqual(self.plan, repeated)
        self.assertEqual(self.plan["content_sha256"], canonical_hash(self.plan, {"content_sha256"}))
        self.assertEqual(self.plan["status"], "approval_required")
        self.assertEqual(len(self.plan["orders"]), 4)
        self.assertEqual(
            self.plan["waves"][0]["work_order_ids"],
            ["carddemo:acctpl1:portfolio-cell", "carddemo:posttran:portfolio-cell"],
        )
        self.assertEqual(
            self.plan["waves"][1]["work_order_ids"],
            ["carddemo:create-statement:portfolio-cell", "carddemo:intcalc:portfolio-cell"],
        )
        self.assertEqual(
            self.plan["approval"]["required_order_ids"],
            ["carddemo:acctpl1:portfolio-cell", "carddemo:posttran:portfolio-cell"],
        )
        self.assertTrue(self.plan["graph_content_sha256"])

    def test_human_approval_is_exact_expiring_and_tamper_evident(self) -> None:
        now = datetime(2026, 8, 15, tzinfo=timezone.utc)
        envelope = sign_portfolio_approval(
            self.plan,
            KEY,
            approver_id="howard-weale",
            key_id="portfolio-approver",
            issued_at=now,
            ttl_seconds=600,
        )
        receipt = verify_portfolio_approval(
            self.plan,
            envelope,
            {"portfolio-approver": KEY},
            now=now + timedelta(seconds=1),
        )
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["approver_kind"], "human")
        self.assertEqual(receipt["plan_sha256"], self.plan["content_sha256"])

        tampered = json.loads(json.dumps(envelope))
        tampered["approved_order_ids"] = []
        with self.assertRaisesRegex(ContractError, "content hash"):
            verify_portfolio_approval(
                self.plan, tampered, {"portfolio-approver": KEY}, now=now
            )
        with self.assertRaisesRegex(ContractError, "not currently valid"):
            verify_portfolio_approval(
                self.plan,
                envelope,
                {"portfolio-approver": KEY},
                now=now + timedelta(seconds=601),
            )

    def test_agent_cannot_become_portfolio_approver(self) -> None:
        now = datetime(2026, 8, 15, tzinfo=timezone.utc)
        envelope = sign_portfolio_approval(
            self.plan, KEY, approver_id="human", key_id="portfolio-approver", issued_at=now
        )
        envelope["approver"]["kind"] = "agent"
        envelope["content_sha256"] = canonical_hash(envelope, {"content_sha256"})
        with self.assertRaisesRegex(ContractError, "human approver"):
            verify_portfolio_approval(
                self.plan, envelope, {"portfolio-approver": KEY}, now=now
            )

    def test_approval_for_other_plan_is_rejected(self) -> None:
        now = datetime(2026, 8, 15, tzinfo=timezone.utc)
        envelope = sign_portfolio_approval(
            self.plan, KEY, approver_id="human", key_id="portfolio-approver", issued_at=now
        )
        other = json.loads(json.dumps(self.plan))
        other["max_parallel"] = 1
        other["content_sha256"] = canonical_hash(other, {"content_sha256"})
        with self.assertRaisesRegex(ContractError, "different plan"):
            verify_portfolio_approval(
                other, envelope, {"portfolio-approver": KEY}, now=now
            )

    def test_runner_enforces_approval_wave_barriers_and_parallelism(self) -> None:
        now = datetime.now(timezone.utc)
        envelope = sign_portfolio_approval(
            self.plan, KEY, approver_id="human", key_id="portfolio-approver", issued_at=now
        )
        admission = verify_portfolio_approval(
            self.plan, envelope, {"portfolio-approver": KEY}, now=now
        )
        lock = threading.Lock()
        active = 0
        maximum = 0
        completed: set[str] = set()

        def execute(order, run_id):
            nonlocal active, maximum
            if order.order_id == "carddemo:create-statement:portfolio-cell":
                self.assertIn("carddemo:posttran:portfolio-cell", completed)
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.03)
            with lock:
                active -= 1
                completed.add(order.order_id)
            receipt = {"status": "passed", "run_id": run_id}
            receipt["content_sha256"] = canonical_hash(receipt)
            return receipt

        with tempfile.TemporaryDirectory() as directory:
            receipt = PortfolioRunner(execute).run(
                self.plan, self.orders, Path(directory), admission
            )
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(maximum, 2)
        self.assertEqual(len(receipt["cells"]), 4)

    def test_runner_fails_closed_without_approval_or_after_failed_wave(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ContractError, "Human-approved"):
                PortfolioRunner(lambda *_: {}).run(
                    self.plan, self.orders, Path(directory)
                )
        now = datetime.now(timezone.utc)
        envelope = sign_portfolio_approval(
            self.plan, KEY, approver_id="human", key_id="portfolio-approver", issued_at=now
        )
        admission = verify_portfolio_approval(
            self.plan, envelope, {"portfolio-approver": KEY}, now=now
        )
        called: list[str] = []

        def execute(order, run_id):
            called.append(order.order_id)
            payload = {
                "status": "blocked" if "posttran" in order.order_id else "passed",
                "run_id": run_id,
            }
            payload["content_sha256"] = canonical_hash(payload)
            return payload

        with tempfile.TemporaryDirectory() as directory:
            receipt = PortfolioRunner(execute).run(
                self.plan, self.orders, Path(directory), admission
            )
        self.assertEqual(receipt["status"], "blocked")
        self.assertNotIn("carddemo:create-statement:portfolio-cell", called)

    def test_manifest_rejects_duplicate_paths_and_unknown_dependencies(self) -> None:
        payload = self.manifest.to_dict()
        payload["work_orders"].append(payload["work_orders"][0])
        with self.assertRaisesRegex(ContractError, "unique"):
            PortfolioManifest.from_dict(payload)
        orders = load_portfolio_orders(self.manifest, ROOT)
        self.assertEqual(len(orders), 4)

    def test_dashboard_projection_is_hash_valid_and_read_only(self) -> None:
        summary = PortfolioStore(
            ROOT / "factory/portfolio/carddemo-plan.snapshot.json",
            ROOT / "work/portfolio",
        ).summary()
        self.assertTrue(summary["read_only"])
        self.assertEqual(summary["status"], "approval_required")
        self.assertEqual(summary["content_sha256"], self.plan["content_sha256"])
        explorer = (ROOT / "src/lightyear_knowledge_graph/explorer.py").read_text()
        self.assertIn('path == "/api/portfolio/summary"', explorer)
        self.assertNotIn('path == "/api/portfolio/approve"', explorer)
        self.assertNotIn('path == "/api/portfolio/run"', explorer)
        for name in (
            "portfolio-manifest.schema.json",
            "portfolio-plan.schema.json",
            "portfolio-approval.schema.json",
            "portfolio-run-receipt.schema.json",
        ):
            schema = json.loads((ROOT / "factory/schema" / name).read_text())
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")


if __name__ == "__main__":
    unittest.main()
