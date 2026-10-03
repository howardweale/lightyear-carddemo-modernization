import hashlib
import json
import shutil
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from lightyear_control_tower.campaign_observer import (
    CampaignSource,
    alerts,
    journal_lines,
    closed_failures,
)
from lightyear_control_tower.decisions import verify_envelope

FIXTURE = Path(__file__).parent / "fixtures/decision-console/b04"
NOW = datetime(2026, 10, 1, 18, tzinfo=timezone.utc)


class ObserverTests(unittest.TestCase):
    def test_number_export_reuses_existing_engine_replay_without_native_values(self):
        from tests.test_paired_campaign import PairedCampaignTests, SimulatedRunner
        from lightyear_workflow import campaign_engine as engine
        from lightyear_control_tower.campaign_observer import NumberSource
        from lightyear_control_tower.decisions import canonical
        from unittest.mock import patch

        fixture = PairedCampaignTests(
            "test_simulated_receipt_never_acquires_native_status_and_reads_do_not_write"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        run = fixture.start()
        engine.execute(fixture.root, run, runner_factory=SimulatedRunner)
        auth = engine.get_authorization(fixture.root, run)
        events = engine.verified_events(fixture.root, auth)
        folder = fixture.root / "observer-export"
        folder.mkdir()
        (folder / "authorization.json").write_bytes(canonical(auth))
        (folder / "events.json").write_bytes(canonical(events))
        source = NumberSource(
            fixture.root,
            folder,
            folder,
            engine.public_key(fixture.root),
            read_mode="immutable-export",
        )
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
        with patch(
            "subprocess.run",
            side_effect=AssertionError("Observer must never launch a process"),
        ):
            result = source.project("number", now=NOW)
        self.assertEqual("passed-simulated", result["state"])
        self.assertEqual(20, result["totals"]["controls_passed"])
        self.assertIsNone(result["totals"]["rate"])
        self.assertTrue(
            all(
                "oracle" not in row and "alloydb" not in row for row in result["trials"]
            )
        )
        self.assertEqual(
            before,
            {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()},
        )

    def test_b04_exact_archived_bytes_alert_at_cohort_three(self):
        manifest = json.loads((FIXTURE / "provenance.json").read_bytes())
        for f in manifest["files"]:
            self.assertEqual(
                f["sha256"],
                hashlib.sha256((FIXTURE / f["path"]).read_bytes()).hexdigest(),
            )
        key = (FIXTURE / "authority.public.pem").read_bytes()
        source = CampaignSource(
            FIXTURE,
            FIXTURE / "published",
            FIXTURE / "work/ms94/stage-b-04",
            key,
            read_mode="immutable-export",
        )
        before = {
            p: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in FIXTURE.rglob("*")
            if p.is_file()
        }
        a = source.project("b04", now=NOW)
        b = source.project("b04", now=NOW)
        self.assertEqual(a, b)
        self.assertEqual("void", a["state"])
        self.assertEqual(3, a["totals"]["cohort_completed"])
        self.assertEqual(10, a["used"]["calls"])
        self.assertIsNone(a["used"]["compilations"])
        self.assertEqual(
            before,
            {
                p: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in before
            },
        )
        repeat = next(x for x in a["alerts"] if x["code"] == "repeated-cause")
        self.assertEqual(["cohort-01", "cohort-03"], repeat["trials"])
        self.assertTrue(repeat["diagnostic_class"].startswith("gate-failure:"))
        self.assertIn("combined-native-judge", repeat["location"])
        self.assertTrue(
            any(
                x["code"] == "gate-decline-pattern" and x["trial"] == "cohort-02"
                for x in a["alerts"]
            )
        )
        a["trials"] = [t for t in a["trials"] if t["id"] != "cohort-03"]
        self.assertFalse(any(x["code"] == "repeated-cause" for x in alerts(a, now=NOW)))
        self.assertIsNone(a["totals"]["rate"])
        self.assertTrue(
            all(v == "verified" for v in a["integrity"]["signatures"].values())
        )
        # Minimal fixture intentionally lacks the full private executable; never
        # represent a public-only fixture as full snapshot verification.
        self.assertIn("snapshot-unavailable", a["integrity"]["issues"])

    def test_live_journal_writer_partial_record_no_lock_or_source_write(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "journal.jsonl"
            path.write_bytes(b'{"sequence":1}\n')
            ready = threading.Event()
            finish = threading.Event()

            def writer():
                with path.open("ab", buffering=0) as f:
                    f.write(b'{"sequence":')
                    ready.set()
                    finish.wait(3)
                    f.write(b"2}\n")

            t = threading.Thread(target=writer)
            t.start()
            ready.wait(3)
            before = (path.read_bytes(), path.stat().st_mtime_ns)
            self.assertEqual([{"sequence": 1}], journal_lines(path))
            self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
            finish.set()
            t.join()
            self.assertEqual([{"sequence": 1}, {"sequence": 2}], journal_lines(path))

    def test_same_trial_repeated_attempts_and_pilots_do_not_count_as_cohort_rate(self):
        failure = {"class": "x", "origin": "candidate", "location": "line1"}
        view = {
            "trials": [{"id": "c1", "phase": "cohort", "failures": [failure, failure]}],
            "limits": {},
            "used": {},
            "integrity": {"verified": True},
        }
        self.assertEqual([], alerts(view, now=NOW))
        view["trials"].append({"id": "p1", "phase": "pilot", "failures": [failure]})
        self.assertEqual([], alerts(view, now=NOW))


if __name__ == "__main__":
    unittest.main()
