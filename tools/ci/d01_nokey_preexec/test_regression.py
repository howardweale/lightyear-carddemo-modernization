"""CI-only adversarial checks: incomplete native evidence never becomes refusal."""
import copy
import errno
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regression import classify

DIGEST = "a" * 64


def sample(operation="raw-fork", policy="combined"):
    concurrent = operation.startswith("concurrent-")
    pairs = [(t, i) for t in range(4) for i in range(4)] if concurrent else [(0, 0)]
    confined = policy == "combined"
    records = [dict(thread=t, iteration=i, status=errno.EAGAIN if confined else 0,
                    child=None if confined else 200 + t * 4 + i, reaped=not confined,
                    wait_status=None if confined else 17 << 8,
                    resume_status=0 if operation == "spawn-suspended" and not confined else None,
                    error=0, forced=False, kill_status=-1) for t, i in pairs]
    return dict(operation=operation, pid=100, parent_pid=99, native_sha256=DIGEST,
                internal_error=0, ready_threads=4 if concurrent else 0,
                nproc_before=[0, 0] if confined else [100, 100],
                nproc_after=[0, 0] if confined else [100, 100],
                requested_nproc=[1, 1] if confined else [100, 100],
                raise_rc=-1 if confined else 0, raise_errno=errno.EPERM if confined else 0,
                relax_rc=-1 if confined else 0, relax_errno=errno.EPERM if confined else 0,
                attempts=records)


class RegressionAccounting(unittest.TestCase):
    def judge(self, row, witness=b"", policy="combined"):
        return classify(row, witness, policy, 100, 99, DIGEST)

    def test_complete_refusal_and_positive_controls(self):
        for operation in ("raw-fork", "vfork", "spawn-suspended", "raise-fork", "relax-fork",
                          "concurrent-fork", "concurrent-spawn"):
            with self.subTest(operation=operation):
                self.assertEqual(self.judge(sample(operation)), "KERNEL_REFUSAL_OBSERVED")
                self.assertEqual(self.judge(sample(operation, "baseline"),
                    b"X" * (16 if operation.startswith("concurrent-") else 1), "baseline"),
                    "POSITIVE_CONTROL_OBSERVED")

    def test_identity_or_helper_mismatch_refused(self):
        for key, value in (("pid", 101), ("parent_pid", 98), ("native_sha256", "b" * 64)):
            row = sample(); row[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.judge(row)

    def test_missing_or_duplicate_concurrent_attempt_refused(self):
        for mutation in (lambda r: r["attempts"].pop(),
                         lambda r: r["attempts"].__setitem__(1, copy.deepcopy(r["attempts"][0]))):
            row = sample("concurrent-fork"); mutation(row)
            with self.assertRaises(ValueError): self.judge(row)

    def test_positive_control_requires_every_witness_and_distinct_child(self):
        row = sample("concurrent-spawn", "baseline")
        with self.assertRaises(ValueError): self.judge(row, b"X" * 15, "baseline")
        row["attempts"][1]["child"] = row["attempts"][0]["child"]
        with self.assertRaises(ValueError): self.judge(row, b"X" * 16, "baseline")

    def test_refusal_cannot_hide_child_or_witness(self):
        with self.assertRaises(ValueError): self.judge(sample(), b"X")
        row = sample(); row["attempts"][0]["child"] = 200
        with self.assertRaises(ValueError): self.judge(row)

    def test_unknown_api_error_refused(self):
        row = sample(); row["attempts"][0]["status"] = errno.ENOSYS
        with self.assertRaises(ValueError): self.judge(row)

    def test_limit_change_or_missing_raises_refused(self):
        row = sample(); row["nproc_after"] = [1, 1]
        with self.assertRaises(ValueError): self.judge(row)
        row = sample("raise-fork"); row["raise_rc"] = 0
        with self.assertRaises(ValueError): self.judge(row)

    def test_relax_success_is_unknown_even_if_fork_refused(self):
        row = sample("relax-fork"); row["relax_rc"] = 0; row["relax_errno"] = 0
        with self.assertRaisesRegex(ValueError, "relaxation refusal unproved"): self.judge(row)

    def test_incomplete_native_execution_refused(self):
        row = sample(); row["internal_error"] = errno.ETIMEDOUT
        with self.assertRaises(ValueError): self.judge(row)
        row = sample("concurrent-fork"); row["ready_threads"] = 3
        with self.assertRaises(ValueError): self.judge(row)

    def test_positive_control_requires_reap_and_exact_exit(self):
        for key, value in (("reaped", False), ("wait_status", 122 << 8), ("forced", True)):
            row = sample(policy="baseline"); row["attempts"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.judge(row, b"X", "baseline")

    def test_suspended_control_requires_resume_success(self):
        row = sample("spawn-suspended", "baseline"); row["attempts"][0]["resume_status"] = errno.ESRCH
        with self.assertRaises(ValueError): self.judge(row, b"X", "baseline")

    def test_single_row_cannot_substitute_concurrent_coverage(self):
        row = sample("concurrent-fork"); row["attempts"] = row["attempts"][:1]
        with self.assertRaises(ValueError): self.judge(row)

class RegressionDiagnosticInventory(unittest.TestCase):
    def report(self):
        import regression_os_diagnostics as diagnostics
        rows = []
        for index, (case, operation) in enumerate(sorted(diagnostics.EXPECTED)):
            for policy in ("baseline", "combined"):
                pid = 1000 + index
                rows.append(dict(case=case, operation=operation, policy=policy, pid=pid, reaped=True,
                    frames=[dict(message=dict(kind="d01-preexec", pid=pid, sandbox_rc=0, nproc=[0, 0]))]))
        return dict(schema="d01-bound-worker-regression/1", rows=rows)

    def check(self, report):
        import json
        from regression_os_diagnostics import confined_pids
        return confined_pids(json.dumps(report).encode())

    def test_exact_regression_inventory(self):
        self.assertEqual(len(self.check(self.report())), 16)

    def test_original_schema_not_silently_accepted(self):
        report = self.report(); report["schema"] = "d01-nokey-preexec-prototype/1"
        with self.assertRaises(ValueError): self.check(report)

    def test_missing_or_duplicate_baseline_pair_refused(self):
        report = self.report(); report["rows"][0] = copy.deepcopy(report["rows"][2])
        with self.assertRaises(ValueError): self.check(report)
        report = self.report(); report["rows"].pop()
        with self.assertRaises(ValueError): self.check(report)

    def test_reused_pid_or_nonzero_limit_refused(self):
        report = self.report()
        for row in report["rows"]:
            if row["policy"] == "combined":
                row["pid"] = row["frames"][0]["message"]["pid"] = 1000
        with self.assertRaises(ValueError): self.check(report)
        report = self.report(); report["rows"][1]["frames"][0]["message"]["nproc"] = [1, 1]
        with self.assertRaises(ValueError): self.check(report)

class RegressionProtocol(unittest.TestCase):
    def test_native_maximum_frame_fits_unchanged_worker_cap(self):
        from lightyear_execution.mac_owner_process import _send, MAX_MESSAGE
        class Channel:
            def send_bytes(self, raw): self.raw = raw
        row = sample("concurrent-spawn", "baseline")
        row.update(pid=2**31-1, parent_pid=2**31-1, nproc_before=[2**64-1]*2,
                   nproc_after=[2**64-1]*2, requested_nproc=[2**64-1]*2)
        for record in row["attempts"]:
            for key in ("status", "child", "wait_status", "resume_status", "error", "kill_status"):
                record[key] = 2**31-1
        channel = Channel(); _send(channel, "d01-attempt", **row)
        self.assertLessEqual(len(channel.raw), MAX_MESSAGE)

    def test_replacement_identity_requires_all_bound_fields(self):
        from observe import validate_replacement
        row = dict(pid=100, parent_pid=99, operation="spawn-setexec", nproc=[0, 0], interpreter="/runtime/bin/python3")
        validate_replacement(row, 100, 99, "spawn-setexec", [0, 0], "/runtime/bin/python3")
        for key, value in (("pid", 101), ("parent_pid", 98), ("operation", "exec-other"),
                           ("nproc", [1, 1]), ("interpreter", "/other/python3")):
            changed = dict(row); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_replacement(changed, 100, 99, "spawn-setexec", [0, 0], "/runtime/bin/python3")

    def test_missing_baseline_control_downgrades_native_refusal(self):
        from regression import require_controls
        rows = [dict(case="S1", operation="none", policy=p, observation="NORMAL_WORK_OBSERVED")
                for p in ("baseline", "combined")]
        rows.append(dict(case="S1", operation="raw-fork", policy="combined", observation="KERNEL_REFUSAL_OBSERVED"))
        require_controls(rows)
        self.assertEqual(rows[-1]["observation"], "UNKNOWN")

    def test_missing_confined_normal_work_downgrades_all_operations(self):
        from regression import require_controls
        rows = [dict(case="S1", operation="raw-fork", policy=p,
                     observation="POSITIVE_CONTROL_OBSERVED" if p == "baseline" else "KERNEL_REFUSAL_OBSERVED")
                for p in ("baseline", "combined")]
        require_controls(rows)
        self.assertTrue(all(row["observation"] == "UNKNOWN" for row in rows))

class SetExecIdentityControl(unittest.TestCase):
    def test_returning_child_is_not_a_setexec_control(self):
        with self.assertRaisesRegex(ValueError, "same worker image"):
            classify(sample("spawn-setexec", "baseline"), b"X", "baseline", 100, 99, DIGEST)
