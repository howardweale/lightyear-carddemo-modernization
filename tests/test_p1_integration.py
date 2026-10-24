from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.ci import p1_codeql, p1_security_collect
from tools.ci.p1_reports import ReportRefused


class P1IntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)


    def test_dependency_fingerprints_bind_findings_without_raw_details(self):
        marker = "SYNTHETIC-PRIVATE-DIAGNOSTIC"
        dependency = dict(name=marker, version="synthetic-version", vulns=[
            dict(id="SYNTHETIC-ADVISORY", description=marker)])
        payload = dict(dependencies=[dependency])
        with patch.object(p1_security_collect, "capture", return_value=(1, json.dumps(payload).encode(), marker.encode())):
            result = p1_security_collect.run_dependency([], self.root, "pip-audit", "pyproject.toml", self.root, {"pyproject.toml"})
        expected = p1_security_collect.digest(["pip-audit", marker, "synthetic-version", "SYNTHETIC-ADVISORY"])
        self.assertEqual([expected], result["finding_fingerprints"])
        self.assertTrue(result["completed"])
        self.assertFalse(result["clean"])
        self.assertEqual(1, result["findings"])
        for forbidden in (marker, "synthetic-version", "SYNTHETIC-ADVISORY", "description"):
            self.assertNotIn(forbidden, json.dumps(result))
        dependency["vulns"][0]["id"] = "SYNTHETIC-DIFFERENT-ADVISORY"
        with patch.object(p1_security_collect, "capture", return_value=(1, json.dumps(payload).encode(), b"")):
            changed = p1_security_collect.run_dependency([], self.root, "pip-audit", "pyproject.toml", self.root, {"pyproject.toml"})
        self.assertNotEqual(result["finding_fingerprints"], changed["finding_fingerprints"])


    def test_dependency_diagnostic_preserves_failure_without_streams(self):
        marker = "SYNTHETIC-RAW-SECRET-DETAIL"
        with patch.object(p1_security_collect, "capture", return_value=(2, marker.encode(), marker.encode())):
            with self.assertRaises(p1_security_collect.DependencyIncomplete) as raised:
                p1_security_collect.run_dependency([], self.root, "dependency-check", "pom.xml", self.root, {"pom.xml"})
        row = p1_security_collect.failure("pom.xml", raised.exception)
        self.assertFalse(row["completed"])
        self.assertFalse(row["clean"])
        self.assertEqual("parse", row["diagnostic"]["stage"])
        self.assertEqual(2, row["diagnostic"]["exit_code"])
        self.assertEqual(len(marker), row["diagnostic"]["stderr_bytes"])
        self.assertNotIn(marker, json.dumps(row))

    def test_security_cli_keeps_closed_failure_artifact(self):
        output = self.root / "security-diagnostic"
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), patch.object(p1_security_collect.sys, "argv",
                ["collector", "gitleaks", "--base", "a" * 40, "--output", str(output)]), \
                patch.object(p1_security_collect, "gitleaks", side_effect=ReportRefused("tool-distribution")), \
                redirect_stderr(StringIO()) as stderr:
            self.assertEqual(1, p1_security_collect.main())
        report = json.loads((output / "gitleaks-incomplete.json").read_text())
        self.assertFalse(report["completed"])
        self.assertFalse(report["clean"])
        self.assertEqual("tool-distribution", report["diagnostic"]["refusal_code"])
        marker = "SYNTHETIC-RAW-SECRET-DETAIL"
        self.assertNotIn(marker, json.dumps(p1_security_collect.diagnostic(ReportRefused(marker))))

    def test_dependency_groups_cover_all_extras_and_empty_groups(self):
        (self.root / "pyproject.toml").write_text('[project]\ndependencies=[]\n[project.optional-dependencies]\na=["idna==3.10"]\nb=[]\n[dependency-groups]\nc=["PyYAML==6.0.3"]\n')
        rows = p1_security_collect.python_groups(self.root, {"pyproject.toml", "requirements-ci.txt"})
        self.assertEqual({"default", "a", "b", "c", "requirements-file"}, {r[1] for r in rows})

    def test_dynamic_and_included_dependencies_fail_closed(self):
        for text in ('[project]\ndynamic=["dependencies"]\n', '[dependency-groups]\ntest=[{include-group="hidden"}]\n'):
            (self.root / "pyproject.toml").write_text(text)
            with self.assertRaises(ReportRefused):
                p1_security_collect.python_groups(self.root, {"pyproject.toml"})

    def test_dependency_resolution_cannot_report_empty_success(self):
        with patch.object(p1_security_collect, "capture", return_value=(0, b'{"dependencies":[]}', b"")):
            with self.assertRaisesRegex(ReportRefused, "empty-resolution"):
                p1_security_collect.run_dependency([], self.root, "pip-audit", "pyproject.toml", self.root, {"pyproject.toml"})

    def test_dependency_analysis_errors_refuse_even_with_findings(self):
        payload = dict(dependencies=[dict(fileName="fixture.jar", vulnerabilities=[dict(name="synthetic", severity="HIGH")])], scanInfo=dict(analysisExceptions=["private raw text"]))
        with patch.object(p1_security_collect, "capture", return_value=(1, json.dumps(payload).encode(), b"")):
            with self.assertRaisesRegex(ReportRefused, "dependency-incomplete"):
                p1_security_collect.run_dependency([], self.root, "dependency-check", "pom.xml", self.root, {"pom.xml"})

    def sarif(self, with_probe=True, real=False, failed=False):
        def result(path):
            return dict(ruleId="py/code-injection", message=dict(text="SYNTHETIC-RAW-DIAGNOSTIC"), locations=[dict(physicalLocation=dict(artifactLocation=dict(uri=path), region=dict(startLine=1)))])
        rows = [result("p1-synthetic-codeql/probe.py")] if with_probe else []
        if real:
            rows.append(result("src/a.py"))
        payload = dict(version="2.1.0", runs=[dict(tool=dict(driver=dict(rules=[dict(id="py/code-injection", properties={"security-severity": "9.8"})])), invocations=[dict(executionSuccessful=not failed)], results=rows)])
        folder = self.root / "raw"
        folder.mkdir(exist_ok=True)
        (folder / "python.sarif").write_text(json.dumps(payload))
        return folder

    def test_codeql_requires_real_negative_control_result(self):
        folder = self.sarif(with_probe=False)
        with patch.object(p1_codeql, "capture", return_value=(0, b"src/a.py\0", b"")):
            with self.assertRaisesRegex(ReportRefused, "negative-control"):
                p1_codeql.reduce(self.root, "python", folder, self.root / "public")

    def test_codeql_control_not_counted_as_repository_finding(self):
        with patch.object(p1_codeql, "capture", return_value=(0, b"src/a.py\0", b"")):
            self.assertTrue(p1_codeql.reduce(self.root, "python", self.sarif(), self.root / "public"))
        report = json.loads((self.root / "public/python.json").read_text())
        self.assertEqual(0, report["summary"]["total"])
        self.assertTrue(report["negative_control_detected"])

    def test_codeql_real_findings_fail_and_raw_text_never_published(self):
        with patch.object(p1_codeql, "capture", return_value=(0, b"src/a.py\0", b"")):
            self.assertFalse(p1_codeql.reduce(self.root, "python", self.sarif(real=True), self.root / "public"))
        raw = (self.root / "public/python.json").read_text()
        self.assertNotIn("SYNTHETIC-RAW-DIAGNOSTIC", raw)
        self.assertNotIn("p1-synthetic-codeql", raw)
        self.assertEqual({"critical": 1}, json.loads(raw)["summary"]["severity_counts"])

    def test_failed_codeql_invocation_refuses_clean_result(self):
        with patch.object(p1_codeql, "capture", return_value=(0, b"src/a.py\0", b"")):
            with self.assertRaisesRegex(ReportRefused, "incomplete"):
                p1_codeql.reduce(self.root, "python", self.sarif(failed=True), self.root / "public")

    def test_cli_suppresses_exception_payload_and_traceback(self):
        output = StringIO()
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), patch("sys.argv", ["tool", "pip-audit", "--output", str(self.root / "cli-failure")]), patch.object(p1_security_collect, "pip_audit", side_effect=ValueError("SYNTHETIC-SECRET-DETAIL")), redirect_stdout(output), redirect_stderr(output):
            self.assertEqual(1, p1_security_collect.main())
        self.assertNotIn("SYNTHETIC-SECRET-DETAIL", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())
        self.assertTrue((self.root / "cli-failure/pip-audit-incomplete.json").is_file())
        self.assertNotIn("SYNTHETIC-SECRET-DETAIL", (self.root / "cli-failure/pip-audit-incomplete.json").read_text())

    def test_control_creation_is_inert_and_exclusive(self):
        p1_codeql.prepare(self.root, "python")
        self.assertTrue((self.root / "p1-synthetic-codeql/probe.py").is_file())
        with self.assertRaises(FileExistsError):
            p1_codeql.prepare(self.root, "python")

    def test_codeql_incomplete_diagnostic_never_serializes_arbitrary_errors(self):
        for error in (ValueError("SYNTHETIC-SECRET"), KeyError("SYNTHETIC-SECRET"),
                      ReportRefused("SYNTHETIC-SECRET")):
            row = p1_codeql.failure_report("javascript-typescript", error)
            self.assertFalse(row["completed"])
            self.assertEqual("unclassified", row["refusal_code"])
            self.assertNotIn("SYNTHETIC-SECRET", json.dumps(row))
        self.assertEqual("codeql-negative-control", p1_codeql.failure_report(
            "javascript-typescript", ReportRefused("codeql-negative-control"))["refusal_code"])

    def test_codeql_failure_cli_retains_incomplete_report_and_nonzero_exit(self):
        output = self.root / "diagnostic"
        console = StringIO()
        args = ["tool", "reduce", "--language", "javascript-typescript", "--sarif", "unused",
                "--output", str(output)]
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), patch("sys.argv", args), patch.object(
            p1_codeql, "reduce", side_effect=ReportRefused("codeql-negative-control")), redirect_stderr(console):
            self.assertEqual(1, p1_codeql.main())
        report = json.loads((output / "javascript-typescript-incomplete.json").read_text())
        self.assertFalse(report["completed"])
        self.assertEqual("codeql-negative-control", report["refusal_code"])
        self.assertFalse((output / "javascript-typescript.json").exists())

    def test_format_json_keeps_bound_paths_and_refuses_malformed_results(self):
        from tools.ci.p1_quality_collect import format_json_report
        from tools.ci.p1_reports import execution_gate
        row = dict(code="unformatted", filename=str(self.root / "src/a.py"),
                   message="SYNTHETIC-RAW", fix=dict(edits=[dict(content="SYNTHETIC-RAW")]))
        encode = lambda rows: json.dumps(rows).encode()
        report = format_json_report(encode([row]), self.root, {"src/a.py"})
        self.assertEqual(["src/a.py"], [r["path"] for r in report["findings"]])
        self.assertNotIn("SYNTHETIC-RAW", json.dumps(report))
        self.assertEqual(1, execution_gate("ruff-format", 1, report, True)["findings"])
        clean = format_json_report(b"[]", self.root, {"src/a.py"})
        self.assertTrue(execution_gate("ruff-format", 0, clean, True)["clean"])
        for raw in (b"not-json", b"{}", encode([row, row]), encode([dict(row, code="syntax-error")]),
                    encode([dict(row, filename="src/unknown.py")])):
            with self.subTest(raw=raw), self.assertRaises(ReportRefused):
                format_json_report(raw, self.root, {"src/a.py"})
        for code, result in ((1, clean), (0, report), (2, report)):
            with self.subTest(code=code), self.assertRaises(ReportRefused):
                execution_gate("ruff-format", code, result, True)

    def test_format_collector_names_every_file_and_refuses_stderr(self):
        from tools.ci import p1_quality_collect
        (self.root / "src").mkdir()
        (self.root / "src/a.py").write_text("x = 1\n")
        (self.root / "src/b.pyi").write_text("x: int\n")
        for index, stderr in enumerate((b"", b"SYNTHETIC-RAW-ERROR")):
            commands = []
            def capture(command, root):
                commands.append(command)
                if command[:2] == ["git", "ls-files"]:
                    return 0, b"src/a.py\0src/b.pyi\0", b""
                if command[:2] == ["git", "rev-parse"]:
                    return 0, b"a" * 40, b""
                if "format" in command:
                    return 0, b"[]", stderr
                return 0, b"" if "mypy" in command else b"[]", b""
            output = self.root / ("quality-" + str(index))
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), patch.object(
                    p1_quality_collect, "capture", side_effect=capture), patch.object(
                    p1_quality_collect, "version", side_effect=lambda name: {"ruff": "0.17.2", "mypy": "2.4.0"}[name]):
                self.assertEqual(not bool(stderr), p1_quality_collect.collect(self.root, output))
            command = next(c for c in commands if "format" in c)
            self.assertIn("--output-format=json", command)
            self.assertEqual(["src/a.py", "src/b.pyi"], command[-2:])
            public = (output / "summary.json").read_text()
            self.assertEqual(2, json.loads(public)["file_count"])
            self.assertNotIn("SYNTHETIC-RAW-ERROR", public)

    def test_grouped_codeql_preserves_control_real_findings_and_severity(self):
        for index, real in enumerate((False, True)):
            folder = self.sarif(real=real)
            source = folder / "python.sarif"
            payload = json.loads(source.read_text())
            run = payload["runs"][0]
            rules = run["tool"]["driver"].pop("rules")
            run["tool"]["extensions"] = [dict(name="synthetic-pack", rules=rules)]
            for row in run["results"]:
                row["rule"] = dict(id=row["ruleId"], index=0, toolComponent=dict(index=0, name="synthetic-pack"))
            source.write_text(json.dumps(payload))
            output = self.root / ("grouped-" + str(index))
            with patch.object(p1_codeql, "capture", return_value=(0, b"src/a.py\0", b"")):
                self.assertEqual(not real, p1_codeql.reduce(self.root, "python", folder, output))
            public = (output / "python.json").read_text()
            self.assertEqual(int(real), json.loads(public)["summary"]["total"])
            self.assertEqual({"critical": 1} if real else {}, json.loads(public)["summary"]["severity_counts"])
            self.assertNotIn("SYNTHETIC-RAW-DIAGNOSTIC", public)

    def test_grouped_codeql_refuses_failed_ambiguous_or_unbound_rules(self):
        from copy import deepcopy
        from tools.ci.p1_reports import codeql_rules, normalize
        folder = self.sarif(real=True)
        original = json.loads((folder / "python.sarif").read_text())
        run = original["runs"][0]
        run["tool"]["extensions"] = [dict(name="pack", rules=run["tool"]["driver"].pop("rules"))]
        cases = []
        bad = deepcopy(original); bad["runs"][0]["invocations"][0]["executionSuccessful"] = False; cases.append(bad)
        bad = deepcopy(original); bad["runs"][0]["tool"]["driver"]["rules"] = deepcopy(run["tool"]["extensions"][0]["rules"]); cases.append(bad)
        bad = deepcopy(original); bad["runs"][0]["tool"]["extensions"][0]["rules"] = []; cases.append(bad)
        for reference in (dict(index=-1), dict(index=9), dict(index=0, toolComponent=dict(index=9)),
                          dict(index=0, toolComponent=dict(index=0, name="wrong")), dict(id="wrong")):
            bad = deepcopy(original); bad["runs"][0]["results"][0]["rule"] = reference; cases.append(bad)
        for bad in cases:
            with self.subTest(case=bad), self.assertRaises(ReportRefused):
                normalize("codeql", bad, self.root, {"src/a.py", "p1-synthetic-codeql/probe.py"})
        self.assertEqual({"py/code-injection"}, set(codeql_rules(run)))

    def test_maven_diagnostics_are_closed_counts_and_never_make_failure_clean(self):
        marker = b"SYNTHETIC-RAW-SECRET"
        output = marker + b" PluginResolutionException BUILD FAILURE"
        with patch.object(p1_security_collect, "capture", return_value=(1, output, marker)):
            with self.assertRaises(p1_security_collect.DependencyIncomplete) as raised:
                p1_security_collect.run_dependency([], self.root, "dependency-check", "pom.xml",
                    self.root, {"pom.xml"}, self.root / "missing.json")
        result = p1_security_collect.failure("pom.xml", raised.exception)
        self.assertFalse(result["completed"])
        self.assertFalse(result["clean"])
        self.assertFalse(result["diagnostic"]["report_present"])
        self.assertEqual(1, result["diagnostic"]["marker_counts"]["plugin-resolution"])
        self.assertNotIn(marker.decode(), json.dumps(result))

    def test_gitleaks_probe_is_deterministic_high_entropy_and_not_allowlisted_alphabet(self):
        from collections import Counter
        from math import log2
        probe = p1_security_collect.gitleaks_probe()
        self.assertEqual(probe, p1_security_collect.gitleaks_probe())
        self.assertRegex(probe, r"^ghp_[0-9a-f]{36}$")
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", probe)
        entropy = -sum((n / len(probe)) * log2(n / len(probe)) for n in Counter(probe).values())
        self.assertGreater(entropy, 3)

    def test_tls_endpoint_diagnostics_are_counts_only(self):
        marker = b"SYNTHETIC-SECRET-DETAIL"
        raw = marker + b" services.nvd.nist.gov PKIX path building failed SunCertPathBuilderException"
        result = p1_security_collect.maven_diagnostic(raw, b"", None)
        self.assertEqual(1, result["marker_counts"]["endpoint-nvd"])
        self.assertEqual(0, result["marker_counts"]["endpoint-cisa"])
        self.assertEqual(1, result["marker_counts"]["certificate-path"])
        self.assertFalse(result["report_present"])
        self.assertNotIn(marker.decode(), json.dumps(result))

    def test_codeql_review_retains_only_bound_rule_and_numeric_location(self):
        folder = self.sarif(real=True)
        source = folder / "python.sarif"
        payload = json.loads(source.read_text())
        run = payload["runs"][0]
        run["tool"]["driver"]["rules"][0]["properties"]["security-severity"] = "7.5"
        row = run["results"][1]
        row["codeFlows"] = [dict(message="SYNTHETIC-PRIVATE-FLOW")]
        row["locations"][0]["physicalLocation"]["region"].update(
            endLine=3, snippet=dict(text="SYNTHETIC-PRIVATE-SOURCE"))
        source.write_text(json.dumps(payload))
        output = self.root / "review-locations"
        with patch.object(p1_codeql, "capture", return_value=(0, b"src/a.py\0", b"")):
            self.assertFalse(p1_codeql.reduce(self.root, "python", folder, output))
        public = (output / "python.json").read_text()
        result = json.loads(public)
        self.assertEqual(1, len(result["review_locations"]))
        detail = result["review_locations"][0]
        self.assertEqual({"path", "rule_id", "start_line", "end_line", "severity", "fingerprint"}, set(detail))
        self.assertEqual(("src/a.py", "py/code-injection", 1, 3, "high"),
            tuple(detail[k] for k in ("path", "rule_id", "start_line", "end_line", "severity")))
        self.assertEqual(64, len(detail["fingerprint"]))
        self.assertEqual(0, result["critical_details_withheld"])
        for marker in ("SYNTHETIC-RAW-DIAGNOSTIC", "SYNTHETIC-PRIVATE-FLOW", "SYNTHETIC-PRIVATE-SOURCE", "p1-synthetic-codeql"):
            self.assertNotIn(marker, public)

    def test_codeql_critical_details_are_withheld_but_gate_still_fails(self):
        folder = self.sarif(real=True)
        output = self.root / "critical-review"
        with patch.object(p1_codeql, "capture", return_value=(0, b"src/a.py\0", b"")):
            self.assertFalse(p1_codeql.reduce(self.root, "python", folder, output))
        public = (output / "python.json").read_text()
        result = json.loads(public)
        self.assertEqual({"critical": 1}, result["summary"]["severity_counts"])
        self.assertEqual(1, result["summary"]["total"])
        self.assertEqual([], result["summary"]["files"])
        self.assertEqual([], result["review_locations"])
        self.assertEqual(1, result["critical_details_withheld"])
        self.assertTrue(result["private_operator_review_required"])
        for marker in ("src/a.py", "py/code-injection", "SYNTHETIC-RAW-DIAGNOSTIC"):
            self.assertNotIn(marker, public)

    def test_codeql_review_rejects_invalid_locations_rules_and_unbound_paths(self):
        from copy import deepcopy
        original = json.loads((self.sarif(real=True) / "python.sarif").read_text())
        original["runs"][0]["tool"]["driver"]["rules"][0]["properties"]["security-severity"] = "7.5"
        cases = []
        for value in (0, -1, True, "SYNTHETIC-PRIVATE-LOCATION", 100000001, None):
            bad = deepcopy(original)
            bad["runs"][0]["results"][1]["locations"][0]["physicalLocation"]["region"]["startLine"] = value
            cases.append(bad)
        bad = deepcopy(original)
        bad["runs"][0]["results"][1]["locations"][0]["physicalLocation"]["region"]["endLine"] = 0
        cases.append(bad)
        bad = deepcopy(original)
        bad["runs"][0]["results"][1]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] = "src/unknown.py"
        cases.append(bad)
        bad = deepcopy(original)
        bad["runs"][0]["tool"]["driver"]["rules"].append(dict(id="SYNTHETIC-PRIVATE-RULE", properties={"security-severity": "7.5"}))
        bad["runs"][0]["results"][1]["ruleId"] = "SYNTHETIC-PRIVATE-RULE"
        cases.append(bad)
        for index, payload in enumerate(cases):
            folder = self.root / ("bad-review-" + str(index)); folder.mkdir()
            (folder / "python.sarif").write_text(json.dumps(payload))
            output = self.root / ("bad-public-" + str(index))
            with patch.object(p1_codeql, "capture", return_value=(0, b"src/a.py\0", b"")):
                with self.assertRaises(ReportRefused) as raised:
                    p1_codeql.reduce(self.root, "python", folder, output)
            self.assertNotIn("SYNTHETIC-PRIVATE", str(raised.exception))
            self.assertFalse((output / "python.json").exists())
