"""Synthetic CI tests. These do not scan private files or call a model."""
import json
import unittest
from tools.ci import p1_reports as reports


class P1ReportTests(unittest.TestCase):
    root = "/checkout"
    paths = {"src/example.py", "fixture/example.js"}

    def ruff(self, message="unused import", line=1):
        return reports.normalize("ruff", [dict(filename="/checkout/src/example.py",
            code="F401", location=dict(row=line, column=1), message=message)], self.root, self.paths)

    def test_gitleaks_never_emits_seed_or_secret_fields(self):
        secret = "SYNTHETIC-NEVER-PUBLISH-THIS-STRING"
        row = dict(File="src/example.py", RuleID="synthetic", StartLine=1,
                   Secret=secret, Match=secret, Message=secret, Email=secret)
        normalized = reports.normalize("gitleaks", [row], self.root, self.paths)
        public = reports.public_summary(normalized)
        self.assertNotIn(secret, json.dumps(normalized))
        self.assertNotIn(secret, json.dumps(public))
        self.assertEqual(public["total"], 1)
        self.assertEqual(public["files"], [dict(path="src/example.py", count=1)])

    def test_quality_messages_are_opaque_even_if_they_quote_source(self):
        marker = "SYNTHETIC-PRIVATE-LIKE-VALUE"
        normalized = self.ruff(marker)
        self.assertNotIn(marker, json.dumps(normalized))
        self.assertNotIn(marker, json.dumps(reports.public_summary(normalized)))

    def test_unknown_paths_and_traversal_refuse_without_echoing_payload(self):
        for path in ("../SECRET", "/elsewhere/SECRET", "src/SECRET.py", "src/\nSECRET.py"):
            with self.subTest(path=path):
                try:
                    reports.relative_path(path, self.root, self.paths)
                except reports.ReportRefused as exc:
                    self.assertNotIn("SECRET", str(exc))
                else:
                    self.fail("unsafe or unbound path accepted")

    def test_malformed_report_refuses_instead_of_returning_zero(self):
        for tool, payload in (("ruff", {}), ("mypy", [{}]), ("gitleaks", [{}]),
                              ("codeql", {"version": "2.1.0", "runs": []}), ("unknown", [])):
            with self.subTest(tool=tool), self.assertRaises(reports.ReportRefused):
                reports.normalize(tool, payload, self.root, self.paths)

    def test_security_sarif_severity_and_message_suppression(self):
        payload = dict(version="2.1.0", runs=[dict(tool=dict(driver=dict(rules=[
            dict(id="test", properties={"security-severity": "9.8"})])), results=[
            dict(ruleId="test", message=dict(text="SYNTHETIC-SECRET"), locations=[
                dict(physicalLocation=dict(artifactLocation=dict(uri="fixture/example.js"),
                                           region=dict(startLine=2)))])])])
        result = reports.public_summary(reports.normalize("codeql", payload, self.root, self.paths))
        self.assertEqual(result["severity_counts"], {"critical": 1})
        self.assertNotIn("SYNTHETIC-SECRET", json.dumps(result))

    def test_baseline_accepts_shrinking_and_rejects_expansion(self):
        base = self.ruff()
        empty = dict(schema=base["schema"], tool=base["tool"], findings=[])
        self.assertTrue(reports.baseline_gate(base, empty, empty)["passed"])
        with self.assertRaisesRegex(reports.ReportRefused, "baseline-expanded"):
            reports.baseline_gate(empty, base, base)

    def test_new_findings_cannot_hide_in_unchanged_baseline(self):
        with self.assertRaisesRegex(reports.ReportRefused, "new-quality-findings"):
            reports.baseline_gate(self.ruff(), self.ruff(), self.ruff(line=2))

    def test_security_findings_cannot_be_baselined(self):
        report = dict(tool="gitleaks", findings=[])
        with self.assertRaisesRegex(reports.ReportRefused, "security-baseline-forbidden"):
            reports.baseline_gate(report, report, report)

    def test_mypy_error_and_unknown_severity(self):
        row = dict(file="src/example.py", severity="error", code="assignment", line=1,
                   column=1, message="SYNTHETIC-SECRET")
        report = reports.normalize("mypy", [row], self.root, self.paths)
        self.assertEqual(reports.public_summary(report)["severity_counts"], {"error": 1})
        row["severity"] = "not-a-severity"
        with self.assertRaisesRegex(reports.ReportRefused, "scanner-severity"):
            reports.normalize("mypy", [row], self.root, self.paths)

    def test_dependency_descriptions_are_never_published(self):
        for tool, row in (
            ("pip-audit", dict(name="synthetic", version="1", vulns=[
                dict(id="synthetic-id", description="SYNTHETIC-SECRET")])),
            ("dependency-check", dict(fileName="synthetic.jar", vulnerabilities=[
                dict(name="synthetic-id", severity="CRITICAL", description="SYNTHETIC-SECRET")])),
        ):
            with self.subTest(tool=tool):
                result = reports.dependency_report(tool, dict(dependencies=[row]),
                    "src/example.py", self.root, self.paths)
                self.assertNotIn("SYNTHETIC-SECRET", json.dumps(result))
                self.assertEqual(reports.public_summary(result)["total"], 1)

    def test_dependency_skip_and_absent_inventory_fail(self):
        for payload in ({}, dict(dependencies=[dict(skip_reason="SYNTHETIC-SECRET")])):
            with self.assertRaises(reports.ReportRefused) as caught:
                reports.dependency_report("pip-audit", payload, "src/example.py", self.root, self.paths)
            self.assertNotIn("SYNTHETIC-SECRET", str(caught.exception))

    def test_empty_failed_scan_cannot_be_reported_as_clean(self):
        empty = dict(tool="ruff", findings=[])
        for code, complete in ((1, True), (2, True), (0, False)):
            with self.assertRaises(reports.ReportRefused):
                reports.execution_gate("ruff", code, empty, complete)
        self.assertTrue(reports.execution_gate("ruff", 0, empty, True)["clean"])
        self.assertFalse(reports.execution_gate("ruff", 1, self.ruff(), True)["clean"])

    def test_format_baseline_is_also_shrink_only(self):
        report = self.ruff()
        report["tool"] = "ruff-format"
        empty = dict(schema=report["schema"], tool="ruff-format", findings=[])
        self.assertTrue(reports.baseline_gate(report, empty, empty)["passed"])
        with self.assertRaisesRegex(reports.ReportRefused, "baseline-expanded"):
            reports.baseline_gate(empty, report, report)
