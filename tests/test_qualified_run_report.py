"""CI-only synthetic rubric tests; fixtures are not native/held-out proof."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lightyear_factory.qualified_run_report import (
    CONTROL_IDS, ReportError, load_rules, render_bundle, write_report,
)

ROOT = Path(__file__).resolve().parents[1]
E = "a" * 40
RULES_PATH = "spec/qualified-run-outcomes/2026-11-07/tiers.json"


class Bundle:
    def __init__(self, root, passed=19, state="completed", count=19, gate_count=8):
        self.root = root
        self.include_controls = state != "not_started"
        self.controls = [dict(schema="qualified-run-control/1", run_id="ci-fixture",
                              exact_e=E, control_id=x, status="PASS", reason="")
                         for x in CONTROL_IDS]
        policy = json.loads((ROOT / RULES_PATH).read_bytes())
        policy["case_count"] = count
        policy["version"] = "synthetic-ci-only"
        self.rules_ref = self.save("rules.json", policy)
        self.cases = [f"synthetic-case-{i}" for i in range(count)]
        self.gates = [f"synthetic-gate-{i}" for i in range(gate_count)]
        definition = dict(file="synthetic-fixture-only", commit=E, sha256="b" * 64)
        self.catalog = dict(schema="qualified-run-frozen-catalog/1", run_id="ci-fixture",
                            exact_e=E, limit_ids=["spend", "wall"],
                            cases=[dict(id=x, definition=definition) for x in self.cases],
                            gates=[dict(id=x, definition=definition) for x in self.gates])
        self.run = dict(schema="qualified-run-status/1", run_id="ci-fixture", exact_e=E,
                        state=state, answers_exposed=False, catalog_changed_after_freeze=False,
                        evidence_missing=False, verifier_disagrees=False, limit_exceeded=False,
                        control_failed_open=False,
                        limits=dict(spend=True, wall=True), reason="Synthetic observed reason.",
                        stopped_on="control" if state == "stopped" else "none")
        self.rows = [
            dict(schema="qualified-run-case/1", run_id="ci-fixture", exact_e=E,
                 case_id=case, origin="judge", reason="Observed difference." if i >= passed else "",
                 difference="Expected1; actual2." if i >= passed else "",
                 gates={g: "PASS" if i < passed else "FAIL" for g in self.gates})
            for i, case in enumerate(self.cases)]
        self.verifier_edit = lambda value: None
        self.publication_edit = lambda value: None
        self.bundle_edit = lambda value: None

    def save(self, name, value):
        raw = (json.dumps(value) + "\n").encode()
        (self.root / name).write_bytes(raw)
        return dict(path=name, sha256=sha256(raw).hexdigest())

    def materialize(self):
        catalog_ref = self.save("catalog.json", self.catalog)
        self.run["catalog_sha256"] = catalog_ref["sha256"]
        run_ref = self.save("run.json", self.run)
        bundle = dict(schema="qualified-run-report-bundle/1", rules_sha256=self.rules_ref["sha256"],
                      run=run_ref, catalog=catalog_ref, cases=[])
        if self.include_controls:
            bundle["controls"] = [self.save(f"control-{i}.json", r)
                                  for i, r in enumerate(self.controls)]
        if self.run["state"] != "not_started":
            for i, row in enumerate(self.rows):
                row["catalog_sha256"] = catalog_ref["sha256"]
                bundle["cases"].append(self.save(f"case-{i}.json", row))
            passed = sum(all(v == "PASS" for v in r["gates"].values()) for r in self.rows)
            refs = [run_ref, catalog_ref, *bundle["controls"], *bundle["cases"]]
            verifier = dict(schema="qualified-run-open-verifier/1", run_id="ci-fixture",
                            exact_e=E, catalog_sha256=catalog_ref["sha256"],
                            case_gates={r["case_id"]: r["gates"] for r in self.rows},
                            passed_cases=passed, limits=deepcopy(self.run["limits"]),
                            control_outcomes={r["control_id"]: r["status"] for r in self.controls},
                            input_receipt_sha256=sorted(r["sha256"] for r in refs),
                            status=("STOPPED" if self.run["state"] == "stopped" else
                                    "PASS" if passed == len(self.cases) else "FAIL" if passed == 0 else "PARTIAL"))
            self.verifier_edit(verifier)
            bundle["verifier"] = self.save("verifier.json", verifier)
            refs.append(bundle["verifier"])
            publication = dict(schema="qualified-run-publication/1", run_id="ci-fixture",
                               exact_e=E, catalog_sha256=catalog_ref["sha256"],
                               receipts=[dict(sha256=r["sha256"],
                                              url="https://example.invalid/" + r["path"],
                                              readback_verified=True) for r in refs])
            self.publication_edit(publication)
            bundle["publication"] = self.save("publication.json", publication)
        self.kwargs = dict(rules_path=self.root / "rules.json", rules_sha256=self.rules_ref["sha256"],
                           catalog_sha256=catalog_ref["sha256"])
        self.bundle_edit(bundle)
        self.save("bundle.json", bundle)
        return self.root / "bundle.json"

    def report(self):
        return render_bundle(self.materialize(), **self.kwargs)


class QualifiedRunReportTests(unittest.TestCase):
    def test_approved_boundaries_and_reasons(self):
        for passed, expected in [(0, "D"), (1, "C"), (9, "C"), (10, "B"), (18, "B"), (19, "A")]:
            with self.subTest(passed=passed), TemporaryDirectory() as temp:
                result = Bundle(Path(temp), passed).report()
                self.assertEqual(result["tier"], expected)
                self.assertEqual(result["passed_cases"], passed)
                self.assertFalse(result["authority_granted"])
                self.assertTrue(result["receipts"])

    def test_no_run_needs_reason_but_not_unexecuted_case_receipts(self):
        with TemporaryDirectory() as temp:
            b = Bundle(Path(temp), state="not_started")
            self.assertEqual(b.report()["tier"], "E")
            b.run["reason"] = ""
            self.assertEqual(b.report()["tier"], "F")

    def test_f_overrides_no_run_and_clean_stop_for_each_disqualifier(self):
        for state in ("not_started", "stopped"):
            for flag in ("limit_exceeded", "answers_exposed", "catalog_changed_after_freeze",
                         "evidence_missing", "verifier_disagrees", "control_failed_open"):
                with self.subTest(state=state, flag=flag), TemporaryDirectory() as temp:
                    b = Bundle(Path(temp), passed=5, state=state)
                    b.run[flag] = True
                    self.assertEqual(b.report()["tier"], "F")

    def test_stop_before_limit_exceeded_is_d_even_with_passes(self):
        with TemporaryDirectory() as temp:
            b = Bundle(Path(temp), passed=10, state="stopped")
            b.run["stopped_on"] = "limit"
            b.rows[-1]["gates"][b.gates[0]] = "NOT_RUN"
            self.assertEqual(b.report()["tier"], "D")
            b.run["limit_exceeded"] = True
            self.assertEqual(b.report()["tier"], "F")

    def test_strong_partial_requires_judge_and_named_difference(self):
        for field, value in [("origin", "controller"), ("difference", "")]:
            with self.subTest(field=field), TemporaryDirectory() as temp:
                b = Bundle(Path(temp), passed=10)
                b.rows[-1][field] = value
                self.assertEqual(b.report()["tier"], "F")
        with TemporaryDirectory() as temp:
            b = Bundle(Path(temp), passed=9)
            b.rows[-1]["origin"] = "controller"
            b.rows[-1]["difference"] = ""
            self.assertEqual(b.report()["tier"], "C")

    def test_all_eight_gates_required_for_each_counted_pass(self):
        with TemporaryDirectory() as temp:
            b = Bundle(Path(temp), passed=10)
            b.rows[0]["gates"][b.gates[0]] = "FAIL"
            b.rows[0]["reason"] = "Observed mismatch."
            self.assertEqual(b.report()["tier"], "C")

    def test_incomplete_duplicate_unknown_inventory_and_verdicts_are_f(self):
        edits = [
            lambda b: b.rows.pop(),
            lambda b: b.rows[1].update(case_id=b.rows[0]["case_id"]),
            lambda b: b.rows[0].update(case_id=999),
            lambda b: b.rows[0]["gates"].pop(b.gates[0]),
            lambda b: b.rows[0]["gates"].update(extra="PASS"),
            lambda b: b.rows[0]["gates"].update({b.gates[0]: None}),
            lambda b: b.catalog["cases"][0]["definition"].update(commit=None),
            lambda b: b.run["limits"].update(spend=None),
            lambda b: b.run.pop("answers_exposed"),
        ]
        for edit in edits:
            with self.subTest(edit=edit), TemporaryDirectory() as temp:
                b = Bundle(Path(temp))
                edit(b)
                self.assertEqual(b.report()["tier"], "F")

    def test_verifier_identity_counts_gates_limits_and_hashes_must_agree(self):
        edits = [
            lambda v: v.update(exact_e="c" * 40),
            lambda v: v.update(passed_cases=18),
            lambda v: v.update(case_gates={}),
            lambda v: v.update(limits={}),
            lambda v: v.update(input_receipt_sha256=[]),
            lambda v: v.update(status="FAIL"),
        ]
        for edit in edits:
            with self.subTest(edit=edit), TemporaryDirectory() as temp:
                b = Bundle(Path(temp))
                b.verifier_edit = edit
                self.assertEqual(b.report()["tier"], "F")

    def test_a_requires_publication_readback_of_every_receipt(self):
        for edit in (lambda p: p["receipts"].pop(),
                     lambda p: p["receipts"][0].update(readback_verified=False),
                     lambda p: p["receipts"][0].update(sha256="0" * 64)):
            with self.subTest(edit=edit), TemporaryDirectory() as temp:
                b = Bundle(Path(temp))
                b.publication_edit = edit
                self.assertEqual(b.report()["tier"], "F")

    def test_tampered_missing_and_escaping_inputs_fail_closed(self):
        with TemporaryDirectory() as temp:
            b = Bundle(Path(temp))
            path = b.materialize()
            (Path(temp) / "case-0.json").write_text("{}")
            self.assertEqual(render_bundle(path, **b.kwargs)["tier"], "F")
            (Path(temp) / "run.json").unlink()
            self.assertEqual(render_bundle(path, **b.kwargs)["tier"], "F")
        with TemporaryDirectory() as temp:
            b = Bundle(Path(temp))
            b.bundle_edit = lambda v: v["run"].update(path="../outside.json")
            self.assertEqual(b.report()["tier"], "F")

    def test_duplicate_json_and_rule_edits_do_not_score(self):
        with TemporaryDirectory() as temp:
            b = Bundle(Path(temp))
            path = b.materialize()
            path.write_text('{"schema":"one","schema":"two"}')
            self.assertEqual(render_bundle(path, **b.kwargs)["tier"], "F")
            rule_path = Path(temp) / RULES_PATH
            rule_path.parent.mkdir(parents=True)
            rule_path.write_text("{}")
            with self.assertRaisesRegex(ReportError, "approved-tier-rules-changed"):
                load_rules(rule_path, b.rules_ref["sha256"])

    def test_case_and_condition_binding_is_external_not_nineteen_drills(self):
        for count, gates in [(1, 4), (7, 5), (19, 8)]:
            with self.subTest(count=count), TemporaryDirectory() as temp:
                b = Bundle(Path(temp), passed=count, count=count, gate_count=gates)
                result = b.report()
                self.assertEqual(result["tier"], "A")
                self.assertEqual(result["case_denominator"], count)
                self.assertEqual(result["gate_denominator"], gates)
                b.kwargs["catalog_sha256"] = "0" * 64
                self.assertEqual(render_bundle(Path(temp) / "bundle.json", **b.kwargs)["tier"], "F")

    def test_every_control_must_pass_before_positive_claim(self):
        with TemporaryDirectory() as temp:
            b = Bundle(Path(temp), passed=19)
            b.controls[-1].update(status="FAIL_OPEN", reason="Failed open.")
            self.assertEqual(b.report()["tier"], "F")
            b.controls.pop()
            self.assertEqual(b.report()["tier"], "F")

    def test_control_stop_before_execution_is_d_and_failed_open_is_f(self):
        with TemporaryDirectory() as temp:
            b = Bundle(Path(temp), state="not_started")
            b.include_controls = True
            b.controls[-1].update(status="STOPPED", reason="Refused as designed.")
            self.assertEqual(b.report()["tier"], "D")
            b.controls[-1].update(status="FAIL_OPEN")
            self.assertEqual(b.report()["tier"], "F")

    def test_verifier_must_confirm_control_outcomes(self):
        with TemporaryDirectory() as temp:
            b = Bundle(Path(temp))
            b.verifier_edit = lambda v: v.update(control_outcomes={})
            self.assertEqual(b.report()["tier"], "F")

    def test_report_is_exclusive_and_prints_mechanical_tier(self):
        with TemporaryDirectory() as temp:
            b = Bundle(Path(temp), 10)
            source = b.materialize()
            output = Path(temp) / "final-report.json"
            result = write_report(source, output, **b.kwargs)
            self.assertEqual(result["tier"], "B")
            self.assertEqual(json.loads(output.read_text())["tier_name"], "Strong partial")
            with self.assertRaises(FileExistsError):
                write_report(source, output, **b.kwargs)


if __name__ == "__main__":
    unittest.main()
