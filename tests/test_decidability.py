"""Safety and accounting tests for unfamiliar-corpus calibration."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_calibration.adapters import discover, import_idempiere, scan
from lightyear_calibration.cli import main
from lightyear_calibration.contracts import CalibrationError, digest, read_json, seal
from lightyear_calibration.instrument import assess, build_report, compare_reports, validate_report
from lightyear_calibration.reporting import html_report, publish

ROOT = Path(__file__).resolve().parents[1]


def make_snapshot(status="indeterminate", reasons=None, outcomes=None):
    reasons = reasons if reasons is not None else ["character-empty-string-length-and-collation-policy"]
    outcomes = outcomes if outcomes is not None else (["equivalent"] if status == "decided" else [])
    return {"corpus_id": "test", "adapter": "oracle-postgresql-sql", "corpus_sha256": "a" * 64,
            "gate": {"implementation": "baseline"}, "cases": [{"id": "case-a", "verdict": "equivalent" if status == "decided" else "indeterminate"}],
            "records": [{"id": "record-a", "case_id": "case-a", "lane": "oracle", "kind": "add-column",
                         "status": status, "outcomes": outcomes, "reason_codes": reasons, "units": 2,
                         "source": {"path": "a.sql", "sha256": "b" * 64, "first_unit": 1, "last_unit": 2}}],
            "provenance": {"mode": "local-gate-replay", "scope": "fixture"}}


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for side in ("source", "target"):
            (self.root / side).mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def file(self, side, name, content):
        (self.root / side / name).write_text(content, encoding="utf-8")

    def manifest(self, adapter="oracle-postgresql-sql"):
        return discover(self.root / "source", self.root / "target", adapter, "unfamiliar")

    def test_scans_actual_gate_with_complete_unfamiliar_corpus(self):
        self.file("source", "money.sql", "ALTER TABLE x ADD amount NUMBER(10,2);")
        self.file("target", "money.sql", "ALTER TABLE x ADD amount NUMERIC(10,2);")
        self.file("source", "policy.sql", "ALTER TABLE x ADD memo VARCHAR2(20);")
        self.file("target", "policy.sql", "ALTER TABLE x ADD memo VARCHAR(20);")
        report = build_report(scan(self.manifest()))
        self.assertEqual(4, report["summary"]["in_scope_units"])
        self.assertEqual(2, report["summary"]["decided_units"])
        self.assertEqual(1, report["summary"]["cases"]["equivalent"])
        self.assertEqual(1, len(report["normalization_proposals"]))
        self.assertFalse(report["claims"]["normalizations_applied"])
        validate_report(report)

    def test_unpaired_files_remain_in_denominator_and_clusters(self):
        self.file("source", "alone.sql", "ALTER TABLE x ADD amount NUMBER(10,2);")
        report = build_report(scan(self.manifest()))
        self.assertEqual(1, report["summary"]["in_scope_units"])
        self.assertEqual(0, report["summary"]["decided_units"])
        self.assertIn("missing-target-file", [c["reason_code"] for c in report["causes"]])

    def test_whole_estate_files_outside_adapter_are_explicit(self):
        self.file("source", "a.sql", "SELECT mysterious();")
        self.file("source", "Application.java", "class Application {}")
        report = build_report(scan(self.manifest()))
        self.assertEqual(["Application.java"], report["provenance"]["excluded_files"]["source"])
        self.assertFalse(report["claims"]["whole_estate_equivalence"])

    def test_manifest_cannot_omit_or_double_count_a_file(self):
        self.file("source", "a.sql", "SELECT unknown();")
        self.file("source", "b.sql", "SELECT unknown();")
        manifest = self.manifest()
        omitted = deepcopy(manifest)
        omitted["cases"].pop()
        with self.assertRaisesRegex(CalibrationError, "every eligible"):
            scan(omitted)
        repeated = deepcopy(manifest)
        repeated["cases"][1]["source"] = "a.sql"
        with self.assertRaisesRegex(CalibrationError, "multiple cases"):
            scan(repeated)

    def test_duplicate_ids_and_same_roots_rejected(self):
        self.file("source", "a.sql", "SELECT unknown();")
        manifest = self.manifest()
        manifest["cases"] += deepcopy(manifest["cases"])
        with self.assertRaisesRegex(CalibrationError, "Duplicate"):
            scan(manifest)
        manifest = self.manifest()
        manifest["roots"]["target"] = manifest["roots"]["source"]
        with self.assertRaisesRegex(CalibrationError, "must differ"):
            scan(manifest)

    def test_unsafe_paths_and_symlinks_refused(self):
        self.file("source", "a.sql", "SELECT unknown();")
        for value in ("../a.sql", "/a.sql", "nested/../a.sql", "C:/a.sql", "a\\b.sql"):
            manifest = self.manifest()
            manifest["cases"][0]["source"] = value
            with self.subTest(value=value), self.assertRaises(CalibrationError):
                scan(manifest)
        try:
            (self.root / "target" / "a.sql").symlink_to(self.root / "source" / "a.sql")
        except (OSError, NotImplementedError):
            self.skipTest("Symlink privilege unavailable")
        with self.assertRaisesRegex(CalibrationError, "Symbolic"):
            self.manifest()

    def test_empty_comment_only_files_never_report_full_decidability(self):
        self.file("source", "a.sql", "-- comment\n")
        self.file("target", "a.sql", "-- comment\n")
        report = build_report(scan(self.manifest()), .5)
        self.assertIsNone(report["summary"]["decidability"]["fraction"])
        self.assertEqual("no-comparable-units", report["threshold"]["status"])
        self.assertEqual(1, report["summary"]["cases"]["indeterminate"])
        self.assertEqual(["no-comparable-sql-units"], report["clusters"][0]["reason_codes"])

    def test_sql_divergence_counts_as_decidable_and_is_preserved(self):
        self.file("source", "a.sql", "ALTER TABLE x MODIFY y DEFAULT 1;")
        self.file("target", "a.sql", "ALTER TABLE x ALTER COLUMN y SET DEFAULT 2;")
        report = build_report(scan(self.manifest()))
        self.assertEqual(1.0, report["summary"]["decidability"]["fraction"])
        self.assertEqual(1, report["summary"]["cases"]["divergent"])
        validate_report(report)

    def test_non_utf8_and_size_limits_fail_before_publishing(self):
        (self.root / "source" / "a.sql").write_bytes(b"\xff")
        with self.assertRaisesRegex(CalibrationError, "UTF-8"):
            scan(self.manifest())
        self.file("source", "a.sql", "SELECT unknown();")
        with patch("lightyear_calibration.adapters.MAX_FILE", 3), self.assertRaises(CalibrationError):
            scan(self.manifest())

    def test_five_percent_corpus_emits_report_and_threshold_failure(self):
        for i in range(20):
            self.file("source", f"{i}.sql", "ALTER TABLE x ADD y NUMBER(10);" if i == 0 else "SELECT unknown();")
            self.file("target", f"{i}.sql", "ALTER TABLE x ADD y NUMERIC(10);" if i == 0 else "SELECT unknown();")
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps(self.manifest()))
        out = self.root / "report"
        with redirect_stdout(io.StringIO()):
            code = main(["scan", "--manifest", str(manifest), "--output", str(out), "--minimum-decidability", ".7"])
        self.assertEqual(3, code)
        report = read_json(out / "report.json")
        self.assertEqual(.05, report["summary"]["decidability"]["fraction"])
        self.assertEqual("below-minimum", report["threshold"]["status"])
        self.assertTrue((out / "index.html").is_file())

    def test_complete_scan_is_independent_of_manifest_order(self):
        for name in ("a.sql", "b.sql"):
            self.file("source", name, "SELECT unknown();")
        m = self.manifest()
        first = build_report(scan(m))
        m["cases"].reverse()
        self.assertEqual(first, build_report(scan(m)))

    def test_runtime_adapter_reuses_real_transfer_gate_and_retains_business_failure(self):
        source = {"encoding": "integer-cents-v1", "accounts": [{"id": "a", "owner": "owner", "cents": 100}], "operations": [], "outcomes": []}
        target = {"encoding": "decimal-journal-v1", "accounts": [{"id": "a", "owner": "owner", "amount": "1.00"}], "operations": [], "outcomes": []}
        self.file("source", "a.json", json.dumps(source))
        self.file("target", "a.json", json.dumps(target))
        report = build_report(scan(self.manifest("transfer-observations")))
        self.assertEqual(1, report["summary"]["cases"]["equivalent"])
        target["accounts"][0]["amount"] = "1.01"
        self.file("target", "a.json", json.dumps(target))
        report = build_report(scan(self.manifest("transfer-observations")))
        self.assertEqual(1, report["summary"]["cases"]["divergent"])
        self.assertEqual(0, report["provenance"]["runtime_invocations"])

    def test_runtime_unknown_output_and_duplicate_keys_remain_indeterminate(self):
        good = {"encoding": "integer-cents-v1", "accounts": [{"id": "a", "owner": "owner", "cents": 100}], "operations": [], "outcomes": []}
        self.file("source", "a.json", json.dumps(good))
        for raw in ('{"newCustomerFormat":1}', '{"encoding":1,"encoding":2}'):
            self.file("target", "a.json", raw)
            report = build_report(scan(self.manifest("transfer-observations")))
            self.assertEqual(1, report["summary"]["cases"]["indeterminate"])
            self.assertEqual(1, report["accounting"]["cluster_units"])
            self.assertEqual([], report["normalization_proposals"])

    def test_input_mutation_changes_corpus_identity(self):
        self.file("source", "a.sql", "SELECT a();")
        m = self.manifest()
        first = scan(m)
        self.file("source", "a.sql", "SELECT b();")
        self.assertNotEqual(first["corpus_sha256"], scan(m)["corpus_sha256"])


class InstrumentTests(unittest.TestCase):
    def test_clusters_partition_all_records_but_cause_counts_overlap(self):
        s = make_snapshot(reasons=["character-empty-string-length-and-collation-policy", "baseline-object-required"])
        report = build_report(s)
        self.assertEqual(2, report["accounting"]["cluster_units"])
        self.assertEqual(4, sum(c["units"] for c in report["causes"]))
        b = report["normalization_proposals"][0]["blast_radius"]
        self.assertEqual(0, b["units_with_no_other_recorded_blocker"])
        self.assertEqual({"baseline-object-required": 2}, b["remaining_blocker_units_by_cause"])
        self.assertIsNone(b["predicted_decidability_gain"])

    def test_blast_radius_includes_existing_decisions_and_divergences(self):
        s = make_snapshot()
        for cid, outcome in (("good", "equivalent"), ("bad", "divergent")):
            s["cases"].append({"id": cid, "verdict": outcome})
            s["records"].append({**deepcopy(s["records"][0]), "id": cid, "case_id": cid, "status": "decided", "outcomes": [outcome], "reason_codes": []})
        report = build_report(s)
        proposed = report["normalization_proposals"][0]
        b = proposed["blast_radius"]
        self.assertEqual(6, b["scoped_units"])
        self.assertEqual(4, b["already_decided_units"])
        self.assertEqual(2, b["known_divergent_units"])
        entry = deepcopy(proposed["entry"])
        entry["selector"]["case_ids"] = ["case-a"]
        narrowed = assess(report, entry)
        self.assertEqual(2, narrowed["blast_radius"]["scoped_units"])
        self.assertNotEqual(proposed["proposal_id"], narrowed["proposal_id"])

    def test_stale_wildcard_and_executable_proposals_refused(self):
        report = build_report(make_snapshot())
        entry = report["normalization_proposals"][0]["entry"]
        for field, value in (("executable", True), ("status", "approved"), ("corpus_sha256", "f"*64), ("gate_sha256", "f"*64)):
            changed = {**entry, field: value}
            with self.subTest(field=field), self.assertRaises(CalibrationError):
                assess(report, changed)
        changed = deepcopy(entry)
        changed["selector"]["kinds"] = ["*"]
        with self.assertRaises(CalibrationError):
            assess(report, changed)
        changed = deepcopy(entry)
        changed["addresses"] = ["unsupported-syntax"]
        with self.assertRaisesRegex(CalibrationError, "cannot become"):
            assess(report, changed)

    def test_parser_gaps_and_unknown_reasons_are_not_normalizations(self):
        for reason, kind in (("unsupported-syntax", "parser-or-adapter-work"), ("never-seen-customer-cause", "unclassified-investigation"),
                             ("dml-schema-trigger-and-coercion-context-required", "semantic-evidence")):
            report = build_report(make_snapshot(reasons=[reason]))
            self.assertEqual(kind, report["causes"][0]["kind"])
            self.assertEqual([], report["normalization_proposals"])

    def test_duplicate_or_omitted_evidence_and_reasonless_unknowns_refused(self):
        for mutate in (lambda s: s["records"].append(deepcopy(s["records"][0])), lambda s: s["records"].clear(),
                       lambda s: s["records"][0].update(reason_codes=[]), lambda s: s["records"][0].update(units=True)):
            s = make_snapshot()
            mutate(s)
            with self.assertRaises(CalibrationError):
                build_report(s)

    def test_derived_report_tampering_detected_even_when_resealed(self):
        for mutate in (lambda r: r["summary"].update(decided_units=200),
                       lambda r: r["by_lane"]["oracle"].update(decided_units=200),
                       lambda r: r["accounting"].update(cluster_units=0),
                       lambda r: r["threshold"].update(status="met"),
                       lambda r: r["clusters"][0].update(record_ids=[]),
                       lambda r: r["normalization_proposals"][0]["blast_radius"].update(scoped_units=0),
                       lambda r: r["claims"].update(whole_estate_equivalence=True)):
            r = build_report(make_snapshot())
            mutate(r)
            r = seal({k:v for k,v in r.items() if k != "content_sha256"})
            with self.assertRaises(CalibrationError):
                validate_report(r)

    def test_rerun_measures_real_new_decisions_on_unchanged_inputs(self):
        before = build_report(make_snapshot())
        s = make_snapshot("decided", reasons=[])
        s["gate"]["implementation"] = "updated"
        after = build_report(s)
        change = compare_reports(before, after)
        self.assertEqual(1, change["newly_decided_cases"])
        self.assertEqual(1., change["decidability_fraction_delta"])
        self.assertTrue(change["gate_changed"])
        self.assertFalse(change["normalization_causality_established"])

    def test_rerun_rejects_changed_corpus_and_records_lost_divergence(self):
        first = make_snapshot("decided", reasons=[], outcomes=["divergent"])
        first["cases"][0]["verdict"] = "divergent"
        before = build_report(first)
        after = build_report(make_snapshot("decided", reasons=[]))
        change = compare_reports(before, after)
        self.assertEqual(["case-a"], change["divergences_no_longer_reported"])
        self.assertEqual(["record-a"], change["unit_divergences_no_longer_reported"])
        self.assertTrue(change["review_required"])
        s = make_snapshot()
        s["corpus_sha256"] = "e"*64
        with self.assertRaisesRegex(CalibrationError, "identical corpus"):
            compare_reports(before, build_report(s))

    def test_unit_regression_detected_even_if_case_stays_divergent(self):
        s = make_snapshot("decided", reasons=[], outcomes=["divergent"])
        s["cases"][0]["verdict"] = "divergent"
        s["records"].append({**deepcopy(s["records"][0]), "id": "another", "source": {"path":"a.sql", "first_unit":3, "last_unit":4, "sha256":"b"*64}})
        before = build_report(s)
        s["records"][0]["outcomes"] = ["equivalent"]
        after = build_report(s)
        change = compare_reports(before, after)
        self.assertEqual([], change["changed_cases"])
        self.assertEqual(["record-a"], change["unit_divergences_no_longer_reported"])
        self.assertTrue(change["review_required"])

    def test_changed_unit_partition_does_not_invent_unit_lift(self):
        before = build_report(make_snapshot())
        s = make_snapshot("decided", reasons=[])
        s["records"][0]["units"] = 1
        s["records"][0]["source"]["last_unit"] = 1
        s["records"].append({**deepcopy(s["records"][0]), "id": "split-record", "source": {
            **s["records"][0]["source"], "first_unit": 2, "last_unit": 2}})
        after = build_report(s)
        change = compare_reports(before, after)
        self.assertFalse(change["unit_partition_unchanged"])
        self.assertIsNone(change["decidability_fraction_delta"])
        self.assertTrue(change["review_required"])

    def test_reports_escape_customer_labels_and_never_copy_raw_values(self):
        s = make_snapshot(reasons=["<script>alert(1)</script>"])
        s["corpus_id"] = '<img src=x onerror="alert(1)">'
        report = build_report(s)
        rendered = html_report(report)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img src=x", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("Content-Security-Policy", rendered)

    def test_threshold_invalid_values_and_no_implicit_threshold(self):
        for value in (-1, 1.1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(CalibrationError):
                build_report(make_snapshot(), value)
        self.assertEqual("not-configured", build_report(make_snapshot())["threshold"]["status"])

    def test_publish_refuses_overwriting_prior_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            r = build_report(make_snapshot())
            publish(r, output)
            original = (output / "report.json").read_bytes()
            with self.assertRaises(CalibrationError):
                publish(r, output)
            self.assertEqual(original, (output / "report.json").read_bytes())

    def test_duplicate_json_and_nonfinite_numbers_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            for value in ('{"x":1,"x":2}', '{"x":NaN}'):
                p.write_text(value)
                with self.assertRaises(CalibrationError):
                    read_json(p)


class RetainedEstateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy = read_json(ROOT / "factory/idempiere-divergence-audit/stage2-comparison.json")
        cls.manifest = read_json(ROOT / "factory/idempiere-divergence-audit/pairing-manifest.json")
        cls.snapshot = import_idempiere(cls.legacy, cls.manifest)

    def test_real_estate_baseline_and_complete_accounting(self):
        r = build_report(self.snapshot)
        self.assertEqual(1078, r["summary"]["cases"]["total"])
        self.assertEqual(1077, r["summary"]["cases"]["indeterminate"])
        self.assertEqual(776, r["summary"]["decided_units"])
        self.assertEqual(111293, r["summary"]["in_scope_units"])
        self.assertEqual(64414, r["by_lane"]["oracle"]["input_units"])
        self.assertEqual(388, r["by_lane"]["oracle"]["decided_units"])
        self.assertEqual(110517, sum(c["units"] for c in r["clusters"]))
        all_refs = [rid for c in r["clusters"] for rid in c["record_ids"]]
        self.assertEqual(len(all_refs), len(set(all_refs)))
        self.assertEqual({row["id"] for row in r["records"] if row["status"] in {"indeterminate", "unsupported"}}, set(all_refs))
        self.assertFalse(r["provenance"]["gate_replayed"])
        self.assertEqual("retained-gate-report", r["provenance"]["mode"])
        self.assertGreaterEqual(len(r["normalization_proposals"]), 4)
        validate_report(r)

    def test_retained_pair_omission_hash_drift_and_invalid_accounting_rejected(self):
        for mutate in (lambda r: r["results"].pop(), lambda r: r["statistics"].update(pairs=0),
                       lambda r: r["bindings"].update(source_commit="fake")):
            changed = deepcopy(self.legacy)
            mutate(changed)
            changed = seal({k:v for k,v in changed.items() if k != "content_sha256"})
            with self.assertRaises(CalibrationError):
                import_idempiere(changed, self.manifest)
        changed = deepcopy(self.legacy)
        row = changed["results"][0]
        row["segments"]["oracle"][0]["first_unit"] = 2
        changed["results"][0] = seal({k:v for k,v in row.items() if k != "content_sha256"})
        changed = seal({k:v for k,v in changed.items() if k != "content_sha256"})
        with self.assertRaises(CalibrationError):
            import_idempiere(changed, self.manifest)


if __name__ == "__main__":
    unittest.main()
