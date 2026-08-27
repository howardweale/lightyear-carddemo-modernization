from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.durable import DurableQueue, DurableWorker
from lightyear_factory.portfolio import (
    PortfolioManifest,
    plan_portfolio,
    sign_portfolio_approval,
    verify_portfolio_approval,
)
from lightyear_factory.store import DurableStore


ROOT = Path(__file__).resolve().parents[1]
KEY = b"durable-portfolio-approval-key-32-bytes"
NOW = datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc)


def receipt(status: str = "passed") -> dict[str, object]:
    result: dict[str, object] = {"status": status, "receipt_type": "test-work-cell"}
    result["content_sha256"] = canonical_hash(result)
    return result


class DurableFactoryTest(unittest.TestCase):
    def setUp(self) -> None:
        manifest = PortfolioManifest.load(ROOT / "factory/portfolio/carddemo-portfolio.json")
        self.plan, orders = plan_portfolio(
            manifest, ROOT, ROOT / "knowledge/graph.snapshot.json.gz"
        )
        self.orders = orders
        envelope = sign_portfolio_approval(
            self.plan,
            KEY,
            approver_id="human-controller",
            key_id="durable-approver",
            issued_at=NOW,
            ttl_seconds=600,
        )
        self.admission = verify_portfolio_approval(
            self.plan, envelope, {"durable-approver": KEY}, now=NOW
        )
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.queue = DurableQueue(Path(self.directory.name) / "control.sqlite3")

    def submit(self, run_id: str = "durable-run-001") -> dict[str, object]:
        return self.queue.submit(self.plan, run_id, self.admission, now=NOW)

    def test_submission_is_idempotent_but_human_approval_is_single_use(self) -> None:
        first = self.submit()
        repeated = self.submit()
        self.assertFalse(first["idempotent"])
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(len(first["items"]), 4)
        with self.assertRaisesRegex(ContractError, "already been consumed"):
            self.submit("durable-run-002")

    def test_plan_must_schedule_every_order_exactly_once(self) -> None:
        malformed = json.loads(json.dumps(self.plan))
        malformed["waves"][0]["work_order_ids"].append(
            malformed["waves"][0]["work_order_ids"][0]
        )
        malformed["content_sha256"] = canonical_hash(malformed, {"content_sha256"})
        admission = dict(self.admission)
        admission["plan_sha256"] = malformed["content_sha256"]
        admission["content_sha256"] = canonical_hash(admission, {"content_sha256"})
        with self.assertRaisesRegex(ContractError, "exactly"):
            self.queue.submit(malformed, "durable-run-bad", admission, now=NOW)

    def test_transactional_workers_never_receive_the_same_item(self) -> None:
        self.submit()
        barrier = threading.Barrier(3)
        leases: list[dict[str, object] | None] = []

        def lease(worker: str) -> None:
            barrier.wait()
            leases.append(self.queue.lease_next(worker, now=NOW, lease_seconds=30))

        threads = [threading.Thread(target=lease, args=(f"worker-{index}",)) for index in (1, 2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(len(leases), 2)
        self.assertEqual(len({item["item_id"] for item in leases if item}), 2)

    def test_lease_authority_heartbeat_and_crash_recovery(self) -> None:
        self.submit()
        lease = self.queue.lease_next("worker-one", now=NOW, lease_seconds=10)
        assert lease is not None
        forged = dict(lease)
        forged["lease_token"] = "not-the-token"
        with self.assertRaisesRegex(ContractError, "authority"):
            self.queue.start(forged, now=NOW)
        self.queue.start(lease, now=NOW)
        heartbeat = self.queue.heartbeat(
            lease, now=NOW + timedelta(seconds=5), lease_seconds=20
        )
        self.assertEqual(heartbeat["lease_expires_at"], "2026-08-15T01:00:25Z")
        self.assertEqual(
            self.queue.recover_expired(now=NOW + timedelta(seconds=24))["recovered"], 0
        )
        recovered = self.queue.recover_expired(now=NOW + timedelta(seconds=26))
        self.assertEqual(recovered["recovered"], 1)
        replacement = self.queue.lease_next(
            "worker-two", now=NOW + timedelta(seconds=26), lease_seconds=10
        )
        assert replacement is not None
        self.assertEqual(replacement["item_id"], lease["item_id"])
        self.assertEqual(replacement["attempt"], 2)
        with self.assertRaisesRegex(ContractError, "required lease state"):
            self.queue.complete(lease, receipt(), now=NOW + timedelta(seconds=27))

    def test_completed_cells_are_not_repeated_and_wave_barrier_is_enforced(self) -> None:
        self.submit()
        first = self.queue.lease_next("worker-one", now=NOW)
        second = self.queue.lease_next("worker-two", now=NOW)
        assert first and second
        self.queue.start(first, now=NOW)
        self.queue.complete(first, receipt(), now=NOW + timedelta(seconds=1))
        self.assertIsNone(self.queue.lease_next("worker-three", now=NOW + timedelta(seconds=1)))
        self.queue.start(second, now=NOW)
        self.queue.complete(second, receipt(), now=NOW + timedelta(seconds=2))
        third = self.queue.lease_next("worker-three", now=NOW + timedelta(seconds=2))
        fourth = self.queue.lease_next("worker-four", now=NOW + timedelta(seconds=2))
        assert third and fourth
        self.assertEqual(third["wave"], 2)
        self.assertEqual(fourth["wave"], 2)
        self.queue.start(third, now=NOW + timedelta(seconds=2))
        pending = self.queue.complete(third, receipt(), now=NOW + timedelta(seconds=3))
        self.assertEqual(pending["state"], "running")
        self.queue.start(fourth, now=NOW + timedelta(seconds=3))
        final = self.queue.complete(fourth, receipt(), now=NOW + timedelta(seconds=4))
        self.assertEqual(final["state"], "passed")
        self.assertIsNone(self.queue.lease_next("worker-five", now=NOW + timedelta(seconds=5)))

    def test_retries_backoff_dead_letter_and_block_descendants(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        for order in plan["orders"]:
            order["max_attempts"] = 2
        plan["content_sha256"] = canonical_hash(plan, {"content_sha256"})
        admission = dict(self.admission)
        admission["plan_sha256"] = plan["content_sha256"]
        admission["content_sha256"] = canonical_hash(admission, {"content_sha256"})
        self.queue.submit(plan, "durable-retry-001", admission, now=NOW)
        lease = self.queue.lease_next("worker-one", now=NOW)
        assert lease
        state = self.queue.fail(lease, "transient_error", now=NOW, backoff_seconds=10)
        self.assertEqual(state["items"][0]["state"], "queued")
        peer = self.queue.lease_next("worker-peer", now=NOW + timedelta(seconds=1))
        assert peer
        self.queue.start(peer, now=NOW + timedelta(seconds=1))
        self.queue.complete(peer, receipt(), now=NOW + timedelta(seconds=2))
        self.assertIsNone(self.queue.lease_next("worker-two", now=NOW + timedelta(seconds=9)))
        retry = self.queue.lease_next("worker-two", now=NOW + timedelta(seconds=10))
        assert retry
        state = self.queue.fail(
            retry, "persistent_error", now=NOW + timedelta(seconds=10), backoff_seconds=0
        )
        self.assertEqual(state["state"], "blocked")
        self.assertEqual(state["items"][0]["state"], "dead_letter")
        self.assertEqual(state["items"][2]["state"], "blocked")

    def test_worker_executes_exact_identity_and_indexes_receipt(self) -> None:
        self.submit()
        calls: list[str] = []

        def execute(order, item_id):
            calls.append(f"{order.order_id}:{item_id}")
            return receipt()

        result = DurableWorker(self.queue, "worker-one", self.orders, execute).run_once(now=NOW)
        assert result
        self.assertEqual(result["items"][0]["state"], "passed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.queue.snapshot()["statistics"]["indexed_artifacts"], 1)

    def test_event_chain_detects_tampering(self) -> None:
        self.submit()
        self.assertEqual(self.queue.validate()["status"], "passed")
        with closing(sqlite3.connect(self.queue.path)) as connection, connection:
            connection.execute(
                "UPDATE durable_events SET payload_json='{}' WHERE sequence=1"
            )
        validation = self.queue.validate()
        self.assertEqual(validation["status"], "failed")
        self.assertIn("event:1:content-hash", validation["errors"])

    def test_dashboard_projection_is_strictly_read_only(self) -> None:
        missing = Path(self.directory.name) / "missing.sqlite3"
        self.assertEqual(DurableStore(missing).summary()["status"], "not_configured")
        self.assertFalse(missing.exists())
        self.submit()
        before = self.queue.path.stat().st_mtime_ns
        snapshot = DurableStore(self.queue.path).summary()
        self.assertEqual(snapshot["status"], "passed")
        self.assertTrue(snapshot["read_only"])
        self.assertEqual(before, self.queue.path.stat().st_mtime_ns)
        explorer = (ROOT / "src/lightyear_knowledge_graph/explorer.py").read_text()
        self.assertIn('path == "/api/durable/summary"', explorer)
        self.assertNotIn('path == "/api/durable/recover"', explorer)
        self.assertNotIn('path == "/api/durable/lease"', explorer)
        for name in (
            "durable-conformance.schema.json",
            "durable-lease.schema.json",
            "durable-state.schema.json",
            "durable-snapshot.schema.json",
        ):
            schema = json.loads((ROOT / "factory/schema" / name).read_text())
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")


if __name__ == "__main__":
    unittest.main()
