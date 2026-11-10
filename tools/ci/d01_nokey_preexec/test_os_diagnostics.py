"""Synthetic diagnostics tests; run only in the existing macOS CI jobs."""
import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import os_diagnostics as diagnostic


class OSDiagnosticsTests(unittest.TestCase):
    def report(self):
        rows = []
        for i, (case, operation) in enumerate(sorted(diagnostic.EXPECTED)):
            for policy in ("baseline", "combined"):
                rows.append(dict(case=case, operation=operation, policy=policy,
                    reaped=True, frames=[dict(message=dict(kind="d01-preexec",
                        pid=100 + i, nproc=[0, 0], sandbox_rc=0))]))
        return dict(schema="d01-nokey-preexec-prototype/1", rows=rows)

    def ips(self, **changes):
        report = dict(pid=123, procName="python3.12",
            captureTime=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            termination=dict(namespace="SIGNAL", code=6), asi={"dyld": ["example"]},
            threads=[{"private": "not exported"}], procPath="/not/exported",
            environment={"not": "exported"})
        report.update(changes)
        return (json.dumps({"incident_id": "not exported"}) + "\n" +
                json.dumps(report)).encode()

    def test_requires_exact_confined_inventory_and_policy(self):
        report = self.report()
        self.assertEqual(len(diagnostic.confined_pids(json.dumps(report))), 8)
        row = next(r for r in report["rows"] if r["policy"] == "combined")
        for member, value in (("pid", True), ("nproc", [0, 1]), ("sandbox_rc", -99)):
            changed = json.loads(json.dumps(report))
            target = next(r for r in changed["rows"] if r["policy"] == "combined")
            target["frames"][0]["message"][member] = value
            with self.assertRaises(ValueError):
                diagnostic.confined_pids(json.dumps(changed))
        row["reaped"] = False
        with self.assertRaises(ValueError):
            diagnostic.confined_pids(json.dumps(report))

    def test_duplicate_or_missing_confined_pid_is_rejected(self):
        report = self.report()
        rows = [r for r in report["rows"] if r["policy"] == "combined"]
        rows[1]["frames"][0]["message"]["pid"] = rows[0]["frames"][0]["message"]["pid"]
        with self.assertRaises(ValueError):
            diagnostic.confined_pids(json.dumps(report))
        report["rows"].pop()
        with self.assertRaises(ValueError):
            diagnostic.confined_pids(json.dumps(report))

    def test_log_filters_worker_pid_not_emitter_or_substring(self):
        raw = (b"kernel[123]: Sandbox: python3(1234) deny(1) file-read-data /wrong\n"
               b"kernel[0]: Sandbox: python3(123) allow file-read-data /wrong\n"
               b"kernel[0]: Sandbox: python3(123) deny(1) sysctl-read exact.item\n")
        rows, overflow = diagnostic.kernel_records(raw, {123})
        self.assertEqual(len(rows), 1)
        self.assertIn("exact.item", rows[0]["line"])
        self.assertFalse(overflow)
        command = diagnostic.log_command({123, 456})
        self.assertEqual(command[:7], ["/usr/bin/log", "show", "--last", "10m",
                                     "--style", "compact", "--predicate"])
        self.assertIn('process == "kernel"', command[-1])
        self.assertIn('eventMessage CONTAINS "(123)"', command[-1])

    def test_truncated_and_oversized_lines_are_unknown(self):
        rows, overflow = diagnostic.kernel_records(
            b"Sandbox: python3(123) deny(1) file-read-data /incomplete", {123})
        self.assertEqual(rows, [])
        self.assertTrue(overflow)
        rows, overflow = diagnostic.kernel_records(
            ("Sandbox: python3(123) deny(1) " + "\u2603" * diagnostic.CAP + "\n").encode(),
            {123})
        self.assertEqual(rows, [])
        self.assertTrue(overflow)

    def test_json_escapes_log_control_bytes(self):
        rows, _ = diagnostic.kernel_records(
            b"Sandbox: python3(123) deny(1) file-read-data /\x1b[31m\n", {123})
        output = diagnostic.encoded(rows)
        self.assertNotIn("\x1b", output)
        self.assertIn("\\u001b", output)
        self.assertEqual(json.loads(output), rows)

    def test_two_object_ips_exports_only_selected_fields(self):
        item = diagnostic.crash_fields(self.ips(), {123}, time.time())
        self.assertEqual(set(item), {"pid", "termination", "asi"})
        self.assertNotIn("not exported", diagnostic.encoded(item))
        self.assertNotIn("procPath", diagnostic.encoded(item))

    def test_ips_wrong_pid_name_time_or_malformed_is_not_evidence(self):
        for change in (dict(pid=1234), dict(procName="other"),
                       dict(captureTime="2000-01-01T00:00:00+00:00")):
            self.assertIsNone(diagnostic.crash_fields(self.ips(**change), {123}, time.time()))
        for raw in (self.ips() + b"unexpected", b"{}", self.ips(termination="invalid")):
            with self.assertRaises((ValueError, KeyError)):
                diagnostic.crash_fields(raw, {123}, time.time())

    def test_file_reads_refuse_symlink_and_oversize(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "python3.ips"
            path.write_bytes(b"12345")
            with self.assertRaises(ValueError):
                diagnostic.read_regular(path, 4)
            link = Path(root) / "alias.ips"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                diagnostic.read_regular(link, 8)

    def test_crash_collection_missing_and_output_overflow_stay_unknown(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "python3-test.ips"
            path.write_bytes(self.ips())
            result = diagnostic.crash_records(Path(root), {123, 456}, time.time(),
                                               time.monotonic() + 5)
            self.assertEqual(result["missing_pids"], [456])
            self.assertEqual(result["status"], "UNKNOWN")
            path.write_bytes(self.ips(asi={"large": ["x" * diagnostic.CAP]}))
            result = diagnostic.crash_records(Path(root), {123}, time.time(),
                                               time.monotonic() + 5)
            self.assertEqual(result["records"], [])
            self.assertTrue(result["errors"])

    def test_query_capture_clean_eof_and_combined_cap(self):
        def run(code):
            return diagnostic.capture([sys.executable, "-I", "-B", "-c", code],
                                      time.monotonic() + 5)
        good = run("import os; os.write(1,b'line\\n')")
        self.assertTrue(good["eof"])
        self.assertEqual(good["stdout"], b"line\n")
        self.assertEqual(good["returncode"], 0)
        noisy = run("import os; os.write(2,b'x'*20000); os.write(1,b'x'*20000)")
        self.assertTrue(noisy["overflow"])
        self.assertLessEqual(len(noisy["stdout"]) + len(noisy["stderr"]),
                             diagnostic.CAP + 1)
        self.assertIsNotNone(noisy["returncode"])

    def test_query_deadline_kills_and_reaps_only_owned_query(self):
        result = diagnostic.capture(
            [sys.executable, "-I", "-B", "-c", "import time; time.sleep(10)"],
            time.monotonic() + 0.2)
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["eof"])
        self.assertIsNotNone(result["returncode"])


if __name__ == "__main__":
    unittest.main()
