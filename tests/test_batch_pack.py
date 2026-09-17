from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from lightyear_workflow.batch_pack import (PackError, SourceLane, TargetLane, load, plan, validate_pack)

PACK = Path(__file__).resolve().parents[1] / "spec/batch-packs/carddemo-intcalc.pack.json"


class FakeReader:
    def __init__(self, datasets): self.datasets = datasets; self.calls = []
    def job(self, jobname, job_id=None):
        self.calls.append(("job", jobname)); return {"jobid": job_id or "JOB1", "retcode": "CC 0000"}
    def dataset(self, name):
        self.calls.append(("dataset", name)); return self.datasets.get(name, b"")


class PackValidationTests(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads(PACK.read_text())

    def mutated(self, change):
        raw = copy.deepcopy(self.raw); change(raw); return raw

    def test_a_valid_pack_loads(self):
        pack = validate_pack(self.raw)
        self.assertEqual(len(pack.jobs), 2)
        self.assertEqual(pack.comparisons, 3)

    def test_the_source_lane_may_not_submit(self):
        """The read-only posture is enforced by the loader, not by convention."""
        with self.assertRaises(PackError) as caught:
            validate_pack(self.mutated(lambda r: r["source"].update(verbs=["observe", "submit"])))
        self.assertIn("observed, never driven", str(caught.exception))

    def test_a_set_comparison_without_a_key_is_refused(self):
        """Otherwise record order is ignored and nobody is told."""
        with self.assertRaises(PackError):
            validate_pack(self.mutated(lambda r: r["jobs"][0]["compare"][0].pop("key")))

    def test_a_job_comparing_nothing_is_refused(self):
        with self.assertRaises(PackError):
            validate_pack(self.mutated(lambda r: r["jobs"][0].update(compare=[])))

    def test_dataset_names_are_validated(self):
        with self.assertRaises(PackError):
            validate_pack(self.mutated(lambda r: r["jobs"][0]["inputs"].append("../../etc/passwd")))

    def test_job_names_are_validated(self):
        with self.assertRaises(PackError):
            validate_pack(self.mutated(lambda r: r["jobs"][0].update(jobname="not a jobname")))

    def test_an_empty_pack_is_refused(self):
        with self.assertRaises(PackError):
            validate_pack(self.mutated(lambda r: r.update(jobs=[])))


class PlanTests(unittest.TestCase):
    def test_the_plan_shows_no_source_submission(self):
        """Run before a customer grants access. It is computed, not asserted."""
        self.assertEqual(plan(load(PACK))["source_submits"], [])

    def test_the_plan_names_every_dataset_read(self):
        reads = plan(load(PACK))["source_reads"]
        self.assertIn("CARDDEMO.ACCTFILE", reads)
        self.assertIn("CARDDEMO.TRANFILE", reads)


class LaneTests(unittest.TestCase):
    def setUp(self):
        self.pack = load(PACK)
        self.job = self.pack.jobs[0]
        self.data = {c.dataset: b"x" for c in self.job.compare}

    def test_the_source_lane_cannot_submit(self):
        self.assertFalse(hasattr(SourceLane, "submit"))
        self.assertFalse(hasattr(SourceLane, "replay"))

    def test_observing_the_source_submits_nothing(self):
        reader = FakeReader(self.data)
        result = SourceLane(reader).observe(self.job)
        self.assertFalse(result["submitted_by_us"])
        self.assertNotIn("submit", {call[0] for call in reader.calls})

    def test_the_target_replay_records_its_origin(self):
        submitted = []
        reader = FakeReader(self.data)
        source = SourceLane(FakeReader(self.data)).observe(self.job)
        target = TargetLane(reader, lambda name, inputs: submitted.append(name) or "JOB9") \
            .replay(self.job, source)
        self.assertTrue(target["submitted_by_us"])
        self.assertEqual(target["replayed_from"], source["run"])
        self.assertEqual(submitted, ["INTCALC"])


if __name__ == "__main__":
    unittest.main()
