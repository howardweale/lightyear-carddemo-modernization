"""Offline seed inspection must never become an execution claim."""
import unittest
from pathlib import Path

from lightyear_calibration.contracts import CalibrationError, read_json, verify
from tools.prepare_idempiere_runtime import registrations, classify_pairs


class RuntimePreflightTests(unittest.TestCase):
    def dump(self, body="postgresql/a.sql\ta.sql\tY\tCO"):
        return "COPY adempiere.ad_migrationscript (filename, name, isapply, status) FROM stdin;\n" + body + "\n\\.\n"

    def pair(self):
        return {"pair_id": "a", "postgresql": {"path": "migration/iD13/postgresql/a.sql"}}

    def test_registration_is_offline_and_never_admits_execution(self):
        result = classify_pairs([self.pair()], registrations(self.dump()))[0]
        self.assertEqual("seed-declares-applied", result["seed_registration_status"])
        self.assertIsNone(result["native_execution_eligible"])

    def test_unregistered_is_not_automatically_eligible(self):
        result = classify_pairs([self.pair()], [])[0]
        self.assertEqual("not-in-seed-register", result["seed_registration_status"])
        self.assertIsNone(result["native_execution_eligible"])

    def test_duplicate_incomplete_or_mismatched_registration_is_ambiguous(self):
        rows = registrations(self.dump())
        for sample in (rows + rows, [{**rows[0], "isapply": "N"}], [{**rows[0], "status": "ER"}],
                       [{**rows[0], "name": "wrong.sql"}]):
            with self.subTest(rows=sample):
                self.assertEqual("registration-ambiguous", classify_pairs([self.pair()], sample)[0]["seed_registration_status"])

    def test_malformed_or_multiple_sections_fail_closed(self):
        for text in ("", self.dump() + self.dump(), self.dump("too\tfew"),
                     self.dump("postgresql/a.sql\ta\\t.sql\tY\tCO")):
            with self.subTest(text=text), self.assertRaises(CalibrationError):
                registrations(text)

    def test_maintenance_is_separately_identified(self):
        pair = self.pair()
        pair["postgresql"]["path"] = "migration/processes_post_migration/postgresql/a.sql"
        self.assertTrue(classify_pairs([pair], [])[0]["post_migration_maintenance"])

    def test_retained_preflight_has_no_native_or_customer_claim(self):
        root = Path(__file__).resolve().parents[1]
        receipt = read_json(root / "docs/calibration/idempiere-runtime/preflight.json")
        verify(receipt)
        baseline = read_json(root / "docs/calibration/idempiere/measurement.json")
        self.assertEqual(baseline["content_sha256"], receipt["baseline_sha256"])
        self.assertEqual(baseline["counts"]["after"], receipt["baseline_counts"])
        self.assertEqual(1078, len(receipt["cases"]))
        self.assertEqual(1078, sum(receipt["seed_registration_counts"].values()))
        self.assertEqual(1054, receipt["seed_registration_counts"]["seed-declares-applied"])
        self.assertEqual(24, receipt["seed_registration_counts"]["not-in-seed-register"])
        self.assertEqual(4, sum(c["post_migration_maintenance"] for c in receipt["cases"]))
        self.assertTrue(all(c["native_execution_eligible"] is None for c in receipt["cases"]))
        self.assertEqual(0, receipt["native_catalog_captures"])
        self.assertEqual(0, receipt["native_migration_executions"])
        self.assertFalse(receipt["customer_equivalence_claim"])


if __name__ == "__main__":
    unittest.main()
