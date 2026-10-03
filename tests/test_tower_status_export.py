"""Real campaign-neutral producer/reader tests; no campaign or model execution."""

import base64
import copy
import hashlib
import json
import threading
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lightyear_control_tower.decisions import canonical, digest
from lightyear_control_tower.status_export import (
    StatusWriter,
    read_exports,
    project_exports,
    atomic_new,
)
from lightyear_control_tower.campaign_observer import CampaignRegistry


class StatusExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # macOS tempfile paths can begin with the system /var -> /private/var alias.
        # Use the canonical operator-selected root; export symlinks stay forbidden.
        self.root = Path(self.tmp.name).resolve()
        self.exports = self.root / "tower-export"
        self.key = Ed25519PrivateKey.generate()
        self.public = self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.now = datetime.now(timezone.utc)
        self.value = {
            "campaign_id": "inventory-demo",
            "at_utc": self.now.isoformat(),
            "bindings": {"plan": digest("demo")},
            "state": "running",
            "active_trial": {"id": "sample-1"},
            "fixture": True,
            "limits": {"items": 100},
            "used": {"items": 0},
            "details": {},
        }
        self.writer = StatusWriter(self.exports, self.sign, self.public, scope="demo")

    def sign(self, value):
        return {
            **value,
            "content_sha256": digest(value),
            "signature": {
                "algorithm": "Ed25519",
                "key_id": hashlib.sha256(self.public).hexdigest(),
                "value": base64.b64encode(self.key.sign(canonical(value))).decode(),
            },
        }

    def read(self):
        return read_exports(
            self.exports,
            self.public,
            "inventory-demo",
            self.value["bindings"],
            scope="demo",
        )

    def view(self, now=None):
        return project_exports(
            self.exports,
            self.public,
            "inventory-demo",
            self.value["bindings"],
            now or self.now,
            scope="demo",
        )

    def test_non_b06_producer_chain_and_ignored_partial_temporary_file(self):
        first = self.writer.emit(self.value)
        pending = self.exports / ".000002.json.partial.pending"
        pending.write_bytes(b'{"unfinished":')
        self.assertEqual(first, self.read())
        second = self.writer.emit(self.value)
        self.assertEqual("tower-status-export/1", second["schema"])
        self.assertEqual(first["content_sha256"], second["previous_sha256"])
        self.assertEqual(second, self.read())
        self.assertEqual(b'{"unfinished":', pending.read_bytes())

    def test_rename_never_overwrites_existing_export_even_with_two_writers(self):
        other = StatusWriter(self.exports, self.sign, self.public, scope="demo")
        barrier = threading.Barrier(2)
        outcomes = []

        def publish(writer):
            barrier.wait(timeout=10)
            try:
                outcomes.append(writer.emit(self.value))
            except FileExistsError:
                outcomes.append("collision")

        threads = [
            threading.Thread(target=publish, args=(w,)) for w in (self.writer, other)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(1, outcomes.count("collision"))
        first = (self.exports / "000001.json").read_bytes()
        with self.assertRaises(FileExistsError):
            atomic_new(self.exports / "000001.json", {"overwrite": True})
        self.assertEqual(first, (self.exports / "000001.json").read_bytes())
        self.assertEqual(1, self.read()["sequence"])
        self.assertEqual(["000001.json"], [p.name for p in self.exports.iterdir()])

    def test_signature_chain_gaps_and_scope_fail_closed(self):
        self.writer.emit(self.value)
        second = self.writer.emit(self.value)
        p = self.exports / "000002.json"
        changed = copy.deepcopy(second)
        changed["state"] = "paused"
        p.write_bytes(canonical(changed))
        with self.assertRaisesRegex(ValueError, "signature"):
            self.read()
        changed = {
            k: v for k, v in second.items() if k not in {"signature", "content_sha256"}
        }
        changed["previous_sha256"] = "f" * 64
        p.write_bytes(canonical(self.sign(changed)))
        with self.assertRaisesRegex(ValueError, "chain"):
            self.read()
        p.write_bytes(canonical(second))
        with self.assertRaisesRegex(ValueError, "campaign-mismatch"):
            read_exports(
                self.exports,
                self.public,
                "inventory-demo",
                self.value["bindings"],
                scope="wrong",
            )
        (self.exports / "000001.json").unlink()
        with self.assertRaisesRegex(ValueError, "sequence-gap"):
            self.read()
        keypath = self.root / "producer.pem"
        keypath.write_bytes(self.public)
        atomic_new(
            self.root / "control-tower/campaigns.json",
            {
                "schema": "tower-campaign-registry/1",
                "campaigns": [
                    {
                        "id": "inventory-demo",
                        "scope": "demo",
                        "adapter": "tower-status-export",
                        "read_mode": "write-once-status",
                        "export_directory": str(self.exports),
                        "trusted_public_key": str(keypath),
                        "bindings": self.value["bindings"],
                    }
                ],
            },
        )
        view = CampaignRegistry(self.root, "demo").view("inventory-demo", now=self.now)
        self.assertEqual("unavailable", view["state"])
        self.assertEqual(["export-sequence-gap"], view["integrity"]["issues"])

    def test_stale_at_45_minutes_only_while_active_and_details_not_projected(self):
        self.value["details"] = {"profile_only": "not-in-generic-route"}
        self.writer.emit(self.value)
        self.assertFalse(self.view(self.now + timedelta(seconds=2699))["stale"])
        view = self.view(self.now + timedelta(minutes=45))
        self.assertTrue(view["stale"])
        self.assertEqual("stale", view["alerts"][0]["code"])
        self.assertNotIn("not-in-generic-route", json.dumps(view))
        self.value.update(active_trial=None, state="completed")
        self.writer.emit(self.value)
        self.assertFalse(self.view(self.now + timedelta(days=1))["stale"])

    def test_real_writer_and_reader_concurrently_on_host_filesystem(self):
        self.writer.emit(self.value)
        done, reading = threading.Event(), threading.Event()
        failures, observed = [], []

        def observe():
            while not done.is_set():
                try:
                    observed.append(self.read()["sequence"])
                    reading.set()
                except Exception as exc:
                    failures.append(str(exc))
                    reading.set()

        thread = threading.Thread(target=observe)
        thread.start()
        try:
            self.assertTrue(reading.wait(timeout=10))
            for i in range(1, 41):
                self.value["used"]["items"] = i
                self.writer.emit(self.value)
        finally:
            done.set()
            thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], failures)
        self.assertGreater(len(observed), 1)
        self.assertEqual(sorted(observed), observed)
        self.assertEqual(41, self.read()["sequence"])


if __name__ == "__main__":
    unittest.main()
