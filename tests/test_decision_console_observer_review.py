"""Observe only disposable, concurrently replaced campaign artifacts."""

import copy
import hashlib
import json
import os
import shutil
import threading
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from tests import test_decision_console_workflows as fixtures
from lightyear_control_tower.campaign_observer import (
    CampaignSource,
    CampaignRegistry,
    alerts,
    closed_failures,
    utc_time,
)
from lightyear_control_tower.decisions import canonical, ZERO
from lightyear_control_tower.fileio import regular_reader
from lightyear_control_tower.requests import read_bytes

NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)


class ObserverReviewTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.WorkflowTests(
            "test_two_exact_release_decisions_offline_verify_and_tamper"
        )
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.campaign = self.root / "campaign"
        self.public = self.root / "published"
        self.campaign.mkdir()
        self.public.mkdir()
        self.snapshot = self.write(self.root / "execution-snapshot.json", {"files": {}})
        self.plan = self.write(
            self.campaign / "plan.json",
            {
                "slots": [{"phase": "cohort", "index": 1}],
                "max_client_invocations": 10,
                "max_compilations": 10,
                "max_elapsed_seconds": 10000,
                "per_trial_elapsed_seconds": 7200,
            },
        )
        (self.public / "plan.json").write_bytes(canonical(self.plan))
        bound = {
            "plan_sha256": self.plan["content_sha256"],
            "snapshot_sha256": self.snapshot["content_sha256"],
        }
        self.write(self.campaign / "declaration.json", bound)
        self.write(self.campaign / "authorization.json", bound)
        self.progress = self.write(
            self.campaign / "progress.json",
            {"results": [], "started_at": NOW.timestamp() - 8100},
        )
        self.active = self.write(
            self.campaign / "active.json",
            {"phase": "cohort", "index": 1, "started_at": NOW.timestamp() - 8100},
        )
        self.source = CampaignSource(
            self.root,
            self.public,
            self.campaign,
            self.f.service.public_key,
            read_mode="immutable-export",
        )

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        record = self.f.service.sign(value)
        path.write_bytes(canonical(record))
        return record

    def test_arbitrary_repeated_business_failure_uses_stage_message_and_origin(self):
        gate = {
            "status": "business-failure",
            "error": {
                "type": "BusinessViolation",
                "stage": "allocation-judge",
                "message": "Credit allocation did not reconcile",
                "origin": "application",
            },
        }
        failures = closed_failures(gate, {})
        self.assertEqual("application", failures[0]["origin"])
        self.assertEqual("allocation-judge", failures[0]["location"])
        view = {
            "trials": [
                {"id": "one", "phase": "cohort", "failures": failures},
                {"id": "two", "phase": "cohort", "failures": failures},
            ],
            "limits": {},
            "used": {},
            "integrity": {"verified": True},
        }
        self.assertTrue(
            any(a["code"] == "repeated-cause" for a in alerts(view, now=NOW))
        )
        changed = copy.deepcopy(gate)
        changed["error"]["message"] = "A different fault"
        self.assertNotEqual(
            failures[0]["class"], closed_failures(changed, {})[0]["class"]
        )
        for trial in view["trials"]:
            trial["failures"] = [{"class": "x", "origin": "unknown", "location": {}}]
        self.assertFalse(
            any(a["code"] == "repeated-cause" for a in alerts(view, now=NOW))
        )

    def test_epoch_times_utc_normalization_budget_and_boundary(self):
        value = self.source.project("fixture", now=NOW)
        self.assertEqual(8100, value["used"]["seconds"])
        self.write(self.campaign / "progress.json", {"results": []})
        self.assertEqual(
            8100, self.source.project("fixture", now=NOW)["used"]["seconds"]
        )
        self.assertIn("stale", [a["code"] for a in value["alerts"]])
        self.assertTrue(
            any(
                a["code"] == "budget" and a["budget"] == "seconds"
                for a in value["alerts"]
            )
        )
        value["used"]["slots"] = value["limits"]["slots"]
        self.assertFalse(
            any(a.get("budget") == "slots" for a in alerts(value, now=NOW))
        )
        value["calendar"] = {
            "clock_mode": "real-time-period-guarded",
            "period_end_exclusive_utc": "2026-10-02T12:10:00",
        }
        self.assertTrue(
            any(a["code"] == "clock-boundary" for a in alerts(value, now=NOW))
        )
        value["used"]["seconds"] = None
        self.assertFalse(
            any(a["code"] == "clock-boundary" for a in alerts(value, now=NOW))
        )
        self.assertEqual(
            utc_time("2026-10-02T12:00:00Z"), utc_time("2026-10-02T05:00:00-07:00")
        )

    def test_projection_identity_is_portable_across_absolute_roots(self):
        one = self.source.project("fixture", now=NOW)
        copied = self.root.parent / "relocated"
        copied.mkdir()
        shutil.copytree(self.campaign, copied / "campaign")
        shutil.copytree(self.public, copied / "published")
        shutil.copyfile(
            self.root / "execution-snapshot.json", copied / "execution-snapshot.json"
        )
        two = CampaignSource(
            copied,
            copied / "published",
            copied / "campaign",
            self.f.service.public_key,
            read_mode="immutable-export",
        ).project("fixture", now=NOW)
        self.assertEqual(one["content_sha256"], two["content_sha256"])
        self.assertTrue(
            all(
                ":" not in p and "\\" not in p
                for p in one["integrity"]["record_hashes"]
            )
        )

    @unittest.skipIf(
        os.name == "nt",
        "MoveFileEx refuses open destinations; live Windows sources fail closed",
    )
    def test_real_projection_allows_replace_and_append_during_open_read(self):
        first = self.write(
            self.root / "first.json",
            {"sequence": 1, "previous_sha256": ZERO, "occurred_at": NOW.isoformat()},
        )
        second = self.f.service.sign(
            {
                "sequence": 2,
                "previous_sha256": first["content_sha256"],
                "occurred_at": NOW.isoformat(),
            }
        )
        journal = self.campaign / "events.jsonl"
        journal.write_bytes(canonical(first) + b"\n")
        ready, replaced = threading.Event(), threading.Event()
        errors = []

        def writer():
            try:
                if not ready.wait(5):
                    raise AssertionError("Observer never opened progress")
                for i in range(40):
                    for name, value in (
                        ("progress", self.progress),
                        ("active", self.active),
                    ):
                        pending = self.campaign / (name + ".pending")
                        pending.write_bytes(canonical(value))
                        os.replace(pending, self.campaign / (name + ".json"))
                    if i == 0:
                        replaced.set()
                with journal.open("ab", buffering=0) as stream:
                    raw = canonical(second)
                    stream.write(raw[: len(raw) // 2])
                    stream.write(raw[len(raw) // 2 :] + b"\n")
            except BaseException as exc:
                import traceback

                errors.append(traceback.format_exc())
                replaced.set()

        def held_read(path):
            if path == self.campaign / "progress.json" and not ready.is_set():
                with regular_reader(path) as stream:
                    raw = stream.read()
                    ready.set()
                    if not replaced.wait(5):
                        raise AssertionError(
                            "Writer could not replace an open progress file"
                        )
                    return raw
            return read_bytes(path)

        thread = threading.Thread(target=writer)
        thread.start()
        try:
            with patch(
                "lightyear_control_tower.campaign_observer.read_bytes", held_read
            ):
                result = self.source.project("fixture", now=NOW)
                for _ in range(5):
                    self.assertNotEqual(
                        "unavailable", self.source.project("fixture", now=NOW)["state"]
                    )
        finally:
            ready.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        self.assertEqual("running", result["state"])
        before = {
            p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.campaign.iterdir()
        }
        result = self.source.project("fixture", now=NOW)
        self.assertEqual("verified", result["integrity"]["journal_chain"])
        self.assertEqual(
            before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
        )
        corrupt = {**second, "previous_sha256": "f" * 64}
        journal.write_bytes(canonical(first) + b"\n" + canonical(corrupt) + b"\n")
        result = self.source.project("fixture", now=NOW)
        self.assertEqual("invalid", result["integrity"]["journal_chain"])
        self.assertTrue(any(a["code"] == "integrity" for a in result["alerts"]))

    def test_windows_live_observer_never_opens_producer_files_during_replace(self):
        errors = []

        def writer():
            try:
                for _ in range(80):
                    for name, value in (
                        ("progress", self.progress),
                        ("active", self.active),
                    ):
                        pending = self.campaign / (name + ".pending")
                        pending.write_bytes(canonical(value))
                        os.replace(pending, self.campaign / (name + ".json"))
                    with (self.campaign / "events.jsonl").open("ab") as stream:
                        stream.write(b"{}\n")
            except BaseException as exc:
                errors.append(exc)

        self.source.read_mode = "live"
        thread = threading.Thread(target=writer)
        thread.start()
        try:
            with (
                patch("lightyear_control_tower.campaign_observer.os.name", "nt"),
                patch(
                    "lightyear_control_tower.campaign_observer.read_bytes",
                    side_effect=AssertionError("Live evidence opened"),
                ),
                patch(
                    "lightyear_control_tower.campaign_observer.regular_reader",
                    side_effect=AssertionError("Live input opened"),
                ),
            ):
                for _ in range(80):
                    result = self.source.project("fixture", now=NOW)
                    self.assertEqual("unavailable", result["state"])
                    self.assertIn(
                        "live-windows-observation-unavailable-use-immutable-export",
                        result["integrity"]["issues"],
                    )
        finally:
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        self.assertEqual(
            canonical(self.progress), (self.campaign / "progress.json").read_bytes()
        )
        self.assertEqual(
            80, len((self.campaign / "events.jsonl").read_bytes().splitlines())
        )

    def test_immutable_export_replays_complete_journal_prefix_and_detects_tampering(
        self,
    ):
        first = self.f.service.sign({"sequence": 1, "previous_sha256": ZERO})
        journal = self.campaign / "events.jsonl"
        journal.write_bytes(canonical(first) + b'\n{"incomplete":')
        before = journal.read_bytes(), journal.stat().st_mtime_ns
        result = self.source.project("fixture", now=NOW)
        self.assertEqual(
            "verified-complete-prefix", result["integrity"]["journal_chain"]
        )
        self.assertEqual(before, (journal.read_bytes(), journal.stat().st_mtime_ns))
        journal.write_bytes(canonical({**first, "previous_sha256": "a" * 64}) + b"\n")
        result = self.source.project("fixture", now=NOW)
        self.assertEqual("invalid", result["integrity"]["journal_chain"])
        self.assertTrue(any(a["code"] == "integrity" for a in result["alerts"]))

    def test_published_history_missing_gate_is_unavailable_not_false_mismatch(self):
        result = {
            "phase": "cohort",
            "index": 1,
            "status": "halted-no-supported-repair",
            "attempts": [
                {
                    "run_directory": "missing/run",
                    "gate_sha256": "a" * 64,
                    "result_class": "business-failure",
                }
            ],
        }
        self.write(
            self.public / "terminal/report.json",
            {"results": [result], "plan_sha256": self.plan["content_sha256"]},
        )
        projected = self.source.project("historical-b04", now=NOW)
        self.assertEqual("failed", projected["trials"][0]["state"])
        self.assertFalse(any("mismatch" in i for i in projected["integrity"]["issues"]))
        self.assertIn(
            "native-gate-unavailable:cohort-01", projected["integrity"]["issues"]
        )
        self.assertFalse(any(a["code"] == "integrity" for a in projected["alerts"]))
        (self.campaign / "active.json").unlink()
        (self.campaign / "progress.json").unlink()
        (self.public / "terminal/report.json").unlink()
        # A publication with no terminal artifacts is unknown, never pending work.
        self.assertEqual(
            "unavailable",
            self.source.project("historical-b01", now=NOW)["trials"][0]["state"],
        )

    def test_null_analyst_missing_receipt_hash_suspect_and_legacy_raw_hash(self):
        trial = self.campaign / "trials/cohort-01"
        native = self.root / "runs/one"
        gate = self.write(native / "gate.json", {"status": "execution-failure"})
        self.write(
            native / "diagnostic-projection.json",
            {
                "gate_sha256": gate["content_sha256"],
                "equipment_suspect": True,
                "diagnostics": [],
            },
        )
        self.write(trial / "feedback-1.json", {"analyst_proposal": None})
        receipt = {
            "status": "halted",
            "attempts": [
                {"run_directory": "runs/one", "gate_sha256": gate["content_sha256"]}
            ],
        }
        (trial / "receipt.json").write_bytes(canonical(receipt))
        self.write(
            self.campaign / "progress.json",
            {"results": [{"phase": "cohort", "index": 1, "receipt_sha256": "a" * 64}]},
        )
        legacy = b'{"operator": "historical typed decision"}'
        (self.public / "operator-adjudication.json").write_bytes(legacy)
        result = self.source.project("fixture", now=NOW)
        self.assertNotEqual("unavailable", result["state"])
        self.assertTrue(any(a["code"] == "equipment-suspect" for a in result["alerts"]))
        self.assertEqual(
            hashlib.sha256(legacy).hexdigest(),
            result["legacy_approvals"][0]["content_sha256"],
        )
        self.assertIsNone(result["used"]["calls"])
        self.write(
            native / "diagnostic-projection.json",
            {
                "gate_sha256": gate["content_sha256"],
                "diagnostics": [
                    {
                        "category": "candidate-runtime-exception",
                        "thrown_by": "candidate",
                        "candidate_frame": {"method": "run", "line": 4},
                    }
                ],
            },
        )
        for disposition, expected in (("accept", False), ("reject", True)):
            self.write(
                trial / "feedback-1.json",
                {
                    "analyst_proposal": {
                        "decisions": [
                            {
                                "disposition": disposition,
                                "reason": "insufficient-type-evidence",
                            }
                        ]
                    }
                },
            )
            projected = self.source.project("fixture", now=NOW)
            self.assertEqual(
                expected,
                any(a["code"] == "gate-decline-pattern" for a in projected["alerts"]),
            )


if __name__ == "__main__":
    unittest.main()
