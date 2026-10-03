"""Zero-model B06 controller boundary and real Tower HTTP/Windows regression."""

import base64
import copy
import hashlib
import json
import os
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, Mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lightyear_control_tower.b06 import (
    SCOPE,
    LAUNCH_FIELDS,
    B06TowerBoundary,
    StatusWriter,
    DecisionReader,
    write_request,
    project_exports,
    read_exports,
    atomic_new,
    register,
)
from lightyear_control_tower.campaign_observer import CampaignRegistry
from lightyear_control_tower.client import ConsoleClient
from lightyear_control_tower.decisions import canonical, digest
from lightyear_control_tower.server import ConsoleAPI, create_server
from tests import test_decision_console as fixtures


class B06Tests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ConsoleTests(
            "test_provision_no_roles_and_role_changes_journaled"
        )
        self.f.scope = SCOPE
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.s = self.f.service
        self.root = self.f.root
        self.engine = Path(self.f.tmp.name) / "engine"
        self.engine.mkdir()
        self.key = Ed25519PrivateKey.generate()
        self.public = self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.artifacts = {
            k: canonical({"fixture": k, "campaign": "b06-fixture"})
            for k in LAUNCH_FIELDS
        }
        self.launch_id, self.bound = write_request(
            self.root, "campaign-authorization", self.artifacts
        )
        self.bindings = {k: self.bound[k] for k in LAUNCH_FIELDS}
        self.now = datetime.now(timezone.utc)
        end = (
            self.now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=32)
        ).replace(day=1)
        # A disposable fixture must still have a full launch window when CI runs
        # during the last four days of a real month; production dates are frozen.
        if end - self.now <= timedelta(hours=97):
            end = (end + timedelta(days=32)).replace(day=1)
        self.calendar = {
            "clock_mode": "unmodified-real-time",
            "period_end_exclusive_utc": end.isoformat(),
            "latest_launch_utc": (end - timedelta(hours=96, seconds=1)).isoformat(),
        }
        self.exports = self.engine / "tower-export"
        self.boundary = B06TowerBoundary(
            StatusWriter(self.exports, self.sign, self.public),
            self.bindings,
            self.calendar,
            fixture=True,
        )
        self.boundary.emit(self.now)
        keypath = Path(self.f.tmp.name) / "producer.public.pem"
        keypath.write_bytes(self.public)
        config = self.root / "control-tower/campaigns.json"
        config.parent.mkdir(exist_ok=True)
        config.write_bytes(
            canonical(
                {
                    "schema": "tower-campaign-registry/1",
                    "campaigns": [
                        {
                            "id": "ms94-b06",
                            "scope": SCOPE,
                            "adapter": "ms94-b06",
                            "read_mode": "write-once-status",
                            "export_directory": str(self.exports),
                            "trusted_public_key": str(keypath),
                            "bindings": self.bindings,
                        }
                    ],
                }
            )
        )

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

    def decide(self, item, outcome):
        event = self.s.decide(
            self.f.token, self.f.payload(item_id=item, outcome=outcome)
        )
        return self.s.proof(self.f.token, event["content_sha256"])

    def launch(self):
        proof = self.decide(self.launch_id, "authorized")
        self.boundary.launch(
            proof,
            self.s.public_key,
            self.bound,
            proof["journal"]["journal_head_sha256"],
            self.now,
            lambda: True,
        )

    def trial(self, name, journey="J1", state="failed", fingerprints=None):
        return {
            "id": name,
            "journey": journey,
            "phase": "cohort",
            "state": state,
            "fingerprints": fingerprints or [],
            "receipt_sha256": digest(name),
        }

    def finish(self, t):
        self.boundary.start_trial(
            {k: t[k] for k in ("id", "journey", "phase")}, self.now
        )
        return self.boundary.finish_trial(t, self.now)

    def pause(self, label="pause-1", reasons=None):
        parts = {k: self.artifacts[k] for k in ("campaign", "plan", "executable")}
        parts["pause"] = canonical(
            self.sign(
                {
                    "schema": "b06-pause/1",
                    "fixture": label,
                    "reasons": reasons or ["equipment-suspect"],
                }
            )
        )
        item, bound = write_request(self.root, "b06-pause", parts)
        self.boundary.pause(bound, reasons or ["equipment-suspect"], item, self.now)
        return item, bound

    def test_launch_requires_every_binding_and_admission_before_start(self):
        proof = self.decide(self.launch_id, "authorized")
        head = proof["journal"]["journal_head_sha256"]
        altered = {**self.bound, "template": "e" * 64}
        with self.assertRaisesRegex(ValueError, "binding"):
            self.boundary.launch(
                proof, self.s.public_key, altered, head, self.now, lambda: True
            )
        with self.assertRaisesRegex(ValueError, "admission"):
            self.boundary.launch(
                proof, self.s.public_key, self.bound, head, self.now, lambda: False
            )
        self.assertIsNone(self.boundary.started)
        self.assertEqual(1, len(list(self.exports.glob("*.json"))))
        with self.assertRaisesRegex(ValueError, "latest-launch"):
            self.boundary.launch(
                proof,
                self.s.public_key,
                self.bound,
                head,
                datetime.fromisoformat(self.calendar["latest_launch_utc"])
                + timedelta(seconds=1),
                lambda: True,
            )
        self.boundary.launch(
            proof, self.s.public_key, self.bound, head, self.now, lambda: True
        )
        with self.assertRaisesRegex(ValueError, "single-launch"):
            self.boundary.launch(
                proof, self.s.public_key, self.bound, head, self.now, lambda: True
            )

    def test_real_signed_pause_round_trip_wrong_pause_continue_stop_void(self):
        self.launch()
        item, _ = self.pause()
        proof = self.decide(item, "continue")
        original = copy.deepcopy(self.boundary.value["trials"])
        self.assertEqual(
            "continue",
            self.boundary.resolve(
                proof,
                self.s.public_key,
                proof["journal"]["journal_head_sha256"],
                self.now,
            ),
        )
        self.assertEqual(original, self.boundary.value["trials"])
        self.finish(self.trial("fresh-slot", state="passed"))
        item2, _ = self.pause("pause-2")
        with self.assertRaisesRegex(ValueError, "bound-hash"):
            self.boundary.resolve(
                proof,
                self.s.public_key,
                proof["journal"]["journal_head_sha256"],
                self.now,
            )
        self.assertEqual("paused", self.boundary.value["state"])
        stop = self.decide(item2, "stop")
        self.assertEqual(
            "stop",
            self.boundary.resolve(
                stop,
                self.s.public_key,
                stop["journal"]["journal_head_sha256"],
                self.now,
            ),
        )
        with self.assertRaises(ValueError):
            self.finish(self.trial("forbidden"))
        # A separate fresh fixture checks void; never resume the stopped campaign.
        other = B06TowerBoundary(
            StatusWriter(self.engine / "void-export", self.sign, self.public),
            self.bindings,
            self.calendar,
            fixture=True,
        )
        self.boundary = other
        self.launch()
        item3, _ = self.pause("pause-3")
        void = self.decide(item3, "void")
        self.assertEqual(
            "void",
            self.boundary.resolve(
                void,
                self.s.public_key,
                void["journal"]["journal_head_sha256"],
                self.now,
            ),
        )

    def test_repeat_once_per_trial_scoped_by_journey_and_suspect(self):
        self.launch()
        fingerprint = digest("candidate posting sequence")
        self.assertEqual(
            [],
            self.finish(
                self.trial("cohort-J1-01", fingerprints=[fingerprint, fingerprint])
            ),
        )
        self.assertEqual(
            [],
            self.finish(
                self.trial("cohort-J2-01", journey="J2", fingerprints=[fingerprint])
            ),
        )
        self.assertEqual(
            ["repeated-cause"],
            self.finish(self.trial("cohort-J1-02", fingerprints=[fingerprint])),
        )
        with self.assertRaises(ValueError):
            self.finish(self.trial("cannot-start"))
        item, _ = self.pause(reasons=["repeated-cause"])
        proof = self.decide(item, "continue")
        self.boundary.resolve(
            proof, self.s.public_key, proof["journal"]["journal_head_sha256"], self.now
        )
        self.assertEqual(
            ["equipment-suspect"],
            self.finish(self.trial("suspect", state="equipment-suspect")),
        )

    def test_provider_pause_not_candidate_failure_and_hard_deadline(self):
        self.launch()
        self.assertEqual(
            ["provider-unavailable"],
            self.finish(self.trial("provider", state="provider-unavailable")),
        )
        self.pause(reasons=["provider-unavailable"])
        view = project_exports(
            self.exports, self.public, "ms94-b06", self.bindings, self.now
        )
        self.assertEqual(0, view["totals"]["cohort_completed"])
        self.assertIn("provider-unavailable", [a["code"] for a in view["alerts"]])
        with self.assertRaisesRegex(
            ValueError, "campaign-hard-deadline|accounting-period"
        ):
            self.boundary.guard(self.now + timedelta(hours=96))

    def test_alerts_80_100_percent_stale_and_calendar(self):
        self.launch()
        self.boundary.start_trial(
            {"id": "active", "journey": "J3", "phase": "cohort"}, self.now
        )
        self.boundary.value["used"].update(calls=390, compilations=234)
        self.boundary.emit(self.now + timedelta(hours=96))
        now = self.now + timedelta(hours=96, minutes=46)
        view = project_exports(
            self.exports, self.public, "ms94-b06", self.bindings, now
        )
        alerts = view["alerts"]
        self.assertIn("stale", [a["code"] for a in alerts])
        self.assertEqual(6, len([a for a in alerts if a["code"] == "budget"]))
        later = datetime.fromisoformat(self.calendar["period_end_exclusive_utc"])
        self.assertIn(
            "clock-boundary",
            [
                a["code"]
                for a in project_exports(
                    self.exports, self.public, "ms94-b06", self.bindings, later
                )["alerts"]
            ],
        )

    def test_tamper_wrong_key_sequence_holes_and_nonoverwrite(self):
        first = self.exports / "000001.json"
        raw = first.read_bytes()
        with self.assertRaises(FileExistsError):
            atomic_new(first, {"changed": True})
        self.assertEqual(raw, first.read_bytes())
        with self.assertRaises(ValueError):
            StatusWriter(self.exports, self.sign, self.public)
        wrong = copy.deepcopy(self.bindings)
        wrong["campaign"] = "a" * 64
        with self.assertRaises(ValueError):
            read_exports(self.exports, self.public, "ms94-b06", wrong)
        first.write_bytes(raw.replace(b'"ready"', b'"void"'))
        self.assertEqual(
            "unavailable",
            CampaignRegistry(self.root, SCOPE).view("ms94-b06", now=self.now)["state"],
        )
        first.write_bytes(raw)
        first.rename(self.exports / "000002.json")
        with self.assertRaises(ValueError):
            read_exports(self.exports, self.public, "ms94-b06", self.bindings)

    def test_http_sse_mcp_and_fresh_decision_reader(self):
        from lightyear_control_tower.mcp import TowerTools

        server = create_server(self.s, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        client = ConsoleClient(f"http://127.0.0.1:{server.server_port}")
        token = client.login(self.f.credential)["token"]
        proof = self.decide(self.launch_id, "authorized")
        reader = DecisionReader(client, self.f.credential, self.s.public_key)
        received = reader.get(
            "campaign-authorization", self.bound, datetime.now(timezone.utc)
        )
        self.assertEqual(proof["decision_sha256"], received["decision_sha256"])
        view = client.campaign_status(token, "ms94-b06")
        self.assertTrue(view["integrity"]["verified"])
        self.assertTrue(view["fixture"])
        from urllib.request import Request, urlopen

        with urlopen(
            Request(
                client.url + "/api/tower/events",
                headers={"Authorization": "Bearer " + token},
            )
        ) as response:
            body = response.read().decode()
        self.assertIn("ms94-b06", body)
        self.assertNotIn(str(self.engine), body)
        credential = self.s.add_identity(
            "b06-reader", "Fixture observer", identity_kind="agent"
        )
        self.s.grant_roles("b06-reader", ["agent"], reason="Read-only fixture observer")
        tools = TowerTools(client, credential)
        self.assertTrue(tools.campaign_status("ms94-b06")["integrity"]["verified"])

    def test_windows_real_observer_never_opens_mutable_controller_files(self):
        self.launch()
        mutable = self.engine / "active.json"
        mutable.write_bytes(b"{}")
        failures = []
        done = threading.Event()
        registry = CampaignRegistry(self.root, SCOPE)

        def observe():
            while not done.is_set():
                try:
                    view = registry.view(
                        "ms94-b06", now=self.now + timedelta(seconds=30)
                    )
                    if not view["integrity"]["verified"]:
                        failures.append(view)
                except Exception as exc:
                    failures.append(str(exc))

        thread = threading.Thread(target=observe)
        thread.start()
        try:
            for i in range(30):
                pending = self.engine / "active.pending"
                pending.write_bytes(canonical({"counter": i}))
                os.replace(pending, mutable)
                before = (mutable.read_bytes(), mutable.stat().st_mtime_ns)
                self.boundary.emit(self.now + timedelta(seconds=i))
                registry.view("ms94-b06", now=self.now + timedelta(seconds=30))
                self.assertEqual(
                    before, (mutable.read_bytes(), mutable.stat().st_mtime_ns)
                )
        finally:
            done.set()
            thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], failures)
        self.assertEqual(32, len(list(self.exports.glob("*.json"))))

    def test_controller_publishes_pause_to_queue_and_consumes_exact_decision(self):
        self.launch()
        trial = self.trial("review-me", state="equipment-suspect")
        self.boundary.start_trial(
            {k: trial[k] for k in ("id", "journey", "phase")}, self.now
        )
        artifacts = {k: self.artifacts[k] for k in ("campaign", "plan", "executable")}
        item, bound = self.boundary.finish_and_review(
            trial, self.root, artifacts, self.now
        )
        self.assertEqual(bound, self.s.inbox.item(item)["bound"])
        view = CampaignRegistry(self.root, SCOPE).view("ms94-b06", now=self.now)
        self.assertEqual("paused", view["state"])
        self.assertEqual(item, view["pause"]["request_id"])
        proof = self.decide(item, "continue")
        self.boundary.resolve(
            proof, self.s.public_key, proof["journal"]["journal_head_sha256"], self.now
        )
        self.finish(self.trial("next-fresh-slot", journey="J2", state="passed"))
        self.assertEqual("equipment-suspect", self.boundary.value["trials"][0]["state"])

    def test_closed_exports_refuse_extra_data_and_prior_verdict_rewrite(self):
        self.launch()
        self.finish(self.trial("original", state="passed"))
        bad = copy.deepcopy(self.boundary.value)
        bad["private_capture"] = "must never be exported"
        with self.assertRaisesRegex(ValueError, "fields"):
            self.boundary.writer.emit(bad)
        bad = copy.deepcopy(self.boundary.value)
        bad["trials"][0]["state"] = "failed"
        self.boundary.writer.emit(bad)
        with self.assertRaisesRegex(ValueError, "prior-verdict"):
            read_exports(self.exports, self.public, "ms94-b06", self.bindings)

    def test_terminal_state_cannot_be_reopened_with_new_pause(self):
        self.launch()
        item, bound = self.pause()
        proof = self.decide(item, "void")
        self.boundary.resolve(
            proof, self.s.public_key, proof["journal"]["journal_head_sha256"], self.now
        )
        with self.assertRaisesRegex(ValueError, "restart"):
            self.boundary.pause(bound, ["equipment-suspect"], item, self.now)

    def test_poll_waits_for_exact_signed_decision_and_usage_is_monotonic(self):
        with self.assertRaisesRegex(ValueError, "live-campaign"):
            self.boundary.record_usage(0, 0, self.now)
        self.launch()
        self.boundary.record_usage(2, 1, self.now)
        with self.assertRaisesRegex(ValueError, "monotonic"):
            self.boundary.record_usage(1, 1, self.now)
        item, bound = self.pause()
        reader = Mock(key=self.s.public_key)
        reader.get.return_value = None
        self.assertIsNone(self.boundary.poll_pause(reader, self.now))
        self.assertEqual("paused", self.boundary.value["state"])
        reader.get.assert_called_once_with("b06-pause", bound, self.now)
        reader.get.return_value = self.decide(item, "stop")
        self.assertEqual("stop", self.boundary.poll_pause(reader, self.now))
        before = list(self.exports.glob("*.json"))
        with self.assertRaisesRegex(ValueError, "live-campaign"):
            self.boundary.record_usage(3, 2, self.now)
        with self.assertRaisesRegex(ValueError, "restart"):
            self.boundary.request_pause(self.root, {}, ["equipment-suspect"], self.now)
        self.assertEqual(before, list(self.exports.glob("*.json")))

    def test_registration_verifies_stream_without_overwrite_or_launch(self):
        target = Path(self.f.tmp.name) / "new-tower"
        keypath = Path(self.f.tmp.name) / "producer.public.pem"
        result = register(target, self.exports, keypath, self.bindings)
        self.assertFalse(result["process_started"])
        view = CampaignRegistry(target, SCOPE).view("ms94-b06", now=self.now)
        self.assertEqual("ready", view["state"])
        self.assertTrue(view["integrity"]["verified"])
        config = target / "control-tower/campaigns.json"
        before = config.read_bytes()
        with self.assertRaises(FileExistsError):
            register(target, self.exports, keypath, self.bindings)
        self.assertEqual(before, config.read_bytes())


if __name__ == "__main__":
    unittest.main()
