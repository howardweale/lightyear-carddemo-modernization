"""Preparation must never acquire execution evidence or dispatch authority."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lightyear_workflow import campaigns as c

ROOT = Path(__file__).resolve().parents[1]


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime.now(timezone.utc)

    def snapshot(self, **changes):
        body = {"campaign_id": c.CAMPAIGN, "project": c.PROJECT, "region": c.REGION,
                "observed_at": self.now.isoformat(),
                "observations": [{"resource": key, "status": "observed", "state": "STOPPED"} for key in c.commands()]}
        body.update(changes)
        path = self.root / c.SNAPSHOT
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"readback": body, "sha256": c._hash(body)}), encoding="utf-8")
        return path

    def test_prepared_files_are_not_execution_or_authority(self):
        value = c.read_campaign(ROOT, "cloudbank", c.CAMPAIGN)
        self.assertEqual(value["source_prepared_cases"], 20)
        self.assertEqual(len({case["behavior_id"] for case in value["cases"]}), 5)
        self.assertIsNone(value["native_executed_cases"])
        self.assertIsNone(value["target_equivalent_cases"])
        self.assertFalse(value["dispatch_available"])
        self.assertEqual(value["status"], "planned")

    def test_missing_files_and_readback_are_unknown_without_writes(self):
        value = c.read_campaign(self.root, "cloudbank", c.CAMPAIGN)
        self.assertIsNone(value["source_prepared_cases"])
        self.assertEqual(value["readiness"]["status"], "unavailable")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_no_cross_estate_or_unknown_campaign(self):
        for estate, campaign in [("carddemo", c.CAMPAIGN), ("cloudbank", "typo"), ("typo", "retained")]:
            with self.assertRaises(ValueError):
                c.read_campaign(self.root, estate, campaign)

    def test_recent_stale_and_future_keep_observation_time(self):
        path = self.snapshot()
        before = path.read_bytes()
        with patch.object(subprocess, "run", side_effect=AssertionError("GET must not contact GCP")):
            recent = c.read_readiness(self.root, now=self.now)
            stale = c.read_readiness(self.root, now=self.now + timedelta(minutes=16))
            future = c.read_readiness(self.root, now=self.now - timedelta(seconds=1))
        self.assertEqual(recent["status"], "recent")
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(recent["observed_at"], stale["observed_at"])
        self.assertEqual(future["status"], "invalid")
        self.assertEqual(future["observations"], [])
        self.assertEqual(path.read_bytes(), before)

    def test_resealed_wrong_scope_wrong_resources_and_corruption_are_rejected(self):
        for changes in [{"project": "different"}, {"campaign_id": "different"}, {"region": "elsewhere"},
                        {"observations": []}, {"observed_at": "2026-01-01"}]:
            self.snapshot(**changes)
            self.assertEqual(c.read_readiness(self.root)["status"], "invalid")
        path = self.snapshot()
        path.write_text(path.read_text(encoding="utf-8").replace("STOPPED", "RUNNING"), encoding="utf-8")
        self.assertEqual(c.read_readiness(self.root)["observations"], [])

    def test_collector_failure_never_persists_private_output_or_success(self):
        with patch.object(c.shutil, "which", return_value="gcloud"), patch.object(subprocess, "run",
                side_effect=subprocess.CalledProcessError(1, "gcloud", stderr="private token")) as run:
            result = c.collect(self.root)
        self.assertEqual(run.call_count, 3)
        self.assertTrue(all(row["status"] == "unavailable" for row in result["observations"]))
        self.assertNotIn("private token", (self.root / c.SNAPSHOT).read_text(encoding="utf-8"))
        for call in run.call_args_list:
            args = call.args[0]
            self.assertIn("describe", args)
            self.assertIn(c.PROJECT, args)
            self.assertFalse({"start", "stop", "create", "update"} & set(args))

    def test_collector_rejects_wrong_resource_identity(self):
        with patch.object(c.shutil, "which", return_value="gcloud"), patch.object(subprocess, "run",
                return_value=subprocess.CompletedProcess([], 0, '{"name":"another-resource","state":"READY"}')):
            result = c.collect(self.root)
        self.assertTrue(all(row["status"] == "unavailable" for row in result["observations"]))
