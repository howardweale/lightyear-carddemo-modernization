from __future__ import annotations

import json
import queue
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen

from lightyear_control_tower.operational import (
    OperationalControlTower,
    OperationalEventStore,
    OperationalSource,
)
from lightyear_knowledge_graph.explorer import ExplorerServer, GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 16, 1, 0, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class LiveControlTowerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.clock = MutableClock(NOW)
        self.store = OperationalEventStore(self.root / "events.sqlite3", now=self.clock)

    def test_event_envelope_is_replayable_subscribable_and_hash_chained(self) -> None:
        first = self.store.append(
            "factory.projection.changed", "factory", "run:one", {"status": "passed"}
        )
        self.assertEqual(1, first["sequence"])
        self.assertEqual("op-", first["event_id"][:3])
        channel = self.store.subscribe(after=0)
        self.assertEqual(first["content_sha256"], channel.get_nowait()["content_sha256"])
        second = self.store.append(
            "runtime.projection.changed", "runtime", "run:two", {"events": 4}
        )
        self.assertEqual(second["content_sha256"], channel.get(timeout=1)["content_sha256"])
        self.store.unsubscribe(channel)
        with self.assertRaises(queue.Empty):
            channel.get_nowait()
        self.assertEqual("passed", self.store.validate()["status"])
        with closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.execute(
                "UPDATE operational_events SET payload_json='{}' WHERE sequence=1"
            )
        self.assertEqual("failed", self.store.validate()["status"])

    def test_control_tower_contracts_are_versioned_and_command_plane_is_disabled(self) -> None:
        for name in ("operational-event.schema.json", "operational-status.schema.json"):
            schema = json.loads((ROOT / "control-tower/schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        policy = json.loads((ROOT / "control-tower/policy.json").read_text())
        self.assertEqual("disabled", policy["command_plane"])
        self.assertTrue(policy["loopback_only"])
        self.assertEqual(
            {"factory", "portfolio", "recovery", "quality", "memory", "data", "runtime", "audit"},
            set(policy["sources"]),
        )

    def test_projection_changes_freshness_and_alerts_are_observable(self) -> None:
        runtime = self.root / "runtime.json"
        runtime.write_text("{}", encoding="utf-8")
        durable_summary = {
            "items": [{
                "item_id": "item-dead", "state": "dead_letter", "lease_expires_at": None
            }]
        }
        sources = (
            OperationalSource(
                "recovery", (self.root / "missing.sqlite3",), "transactional-ledger", 2,
                lambda: durable_summary,
            ),
            OperationalSource(
                "runtime", (runtime,), "runtime-observation", 5,
                lambda: {"statistics": {"run_count": 1}},
            ),
            OperationalSource(
                "audit", (self.root / "audit.json",), "hash-chained-audit", 5,
                lambda: {"trust_posture": {"promotion_status": "blocked"}},
            ),
        )
        tower = OperationalControlTower(self.store, sources, now=self.clock)
        result = tower.scan()
        self.assertEqual({"recovery", "runtime", "audit"}, set(result["changed_sources"]))
        status = tower.status()
        self.assertEqual("critical", status["status"])
        self.assertTrue(status["read_only"])
        self.assertEqual("disabled", status["command_plane"])
        self.assertEqual(2, len(status["alerts"]))
        initial_events = self.store.events(limit=100)
        tower.scan()
        self.assertEqual(len(initial_events), len(self.store.events(limit=100)))
        restarted = OperationalControlTower(self.store, sources, now=self.clock)
        restarted.scan()
        self.assertEqual(len(initial_events), len(self.store.events(limit=100)))
        self.clock.value = NOW + timedelta(seconds=31)
        stale = tower.status()
        runtime_status = next(item for item in stale["sources"] if item["source"] == "runtime")
        self.assertEqual("stale", runtime_status["freshness"])
        self.assertTrue(any(item["alert_id"] == "alert:runtime:runtime-stale" for item in stale["alerts"]))

    def test_http_exposes_status_and_sse_without_command_authority(self) -> None:
        payload = load_graph(ROOT / "knowledge/graph.snapshot.json.gz")
        server = ExplorerServer(
            ("127.0.0.1", 0),
            GraphExplorerIndex(payload, max_nodes=20),
            ROOT / "knowledge/viewer",
            operational_store=self.store,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(f"{base}/api/operations/status", timeout=5) as response:
                status = json.load(response)
            self.assertEqual("lightyear-live-evidence-control-plane", status["plane_type"])
            self.assertTrue(status["read_only"])
            with urlopen(f"{base}/api/operations/stream?after=9999", timeout=5) as response:
                self.assertEqual("text/event-stream; charset=utf-8", response.headers["Content-Type"])
                self.assertEqual("retry: 2000", response.readline().decode().strip())
                self.assertEqual("event: ready", response.readline().decode().strip())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        explorer = (ROOT / "src/lightyear_knowledge_graph/explorer.py").read_text()
        self.assertNotIn('path == "/api/operations/command"', explorer)


if __name__ == "__main__":
    unittest.main()
