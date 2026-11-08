"""CI-only real disposable spawn probes and public adapter refusal checks."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from lightyear_execution.mac_owner_process import RehearsalProcessOwner
import lightyear_execution.mac_owner_process as process_support
from lightyear_execution.external_signing import SigningRefused
from tools.native_owner_rehearsal import PublicJournal
import test_mac_owner_native as native_support


class ProcessOwnerTests(unittest.TestCase):
    def run_case(self, case, seconds=15):
        events = []
        cancel = lambda: case == "S6" and any(
            e["kind"] == "worker-observation" and e["observation"]["kind"] == "ready" for e in events)
        owner = RehearsalProcessOwner(case=case, duration=seconds, emit=events.append, cancel_requested=cancel)
        result = owner.run_once()
        with self.assertRaisesRegex(ValueError, "consumed-no-resume"):
            owner.run_once()
        self.assertEqual(1, sum(e["kind"] == "intent" for e in events))
        self.assertEqual(1, sum(e["kind"] == "cleanup-requested" for e in events))
        self.assertEqual(1, len({e["original_deadline"] for e in events}))
        self.assertEqual(1, len({e["cleanup_deadline"] for e in events}))
        self.assertEqual(events[0]["original_deadline"] + 5, events[0]["cleanup_deadline"])
        self.assertFalse(result["native_proof"])
        self.assertFalse(result["admission_authorized"])
        self.assertFalse(result["restart_authorized"])
        return result, events

    def test_real_child_and_grandchild_have_bound_identities_and_positive_reaps(self):
        for case in ("S1", "S3"):
            with self.subTest(case=case):
                result, events = self.run_case(case)
                self.assertEqual("PASS", result["status"])
                self.assertEqual("REAPED", result["cleanup_status"])
                identities = {p["role"]: p for p in result["identities"]}
                self.assertEqual(os.getpid(), identities["child"]["parent_pid"])
                if case == "S3":
                    self.assertEqual(identities["child"]["pid"], identities["grandchild"]["parent_pid"])
                    self.assertEqual(identities["grandchild"]["pid"], result["grandchild_reap"]["pid"])
                    self.assertEqual(0, result["grandchild_reap"]["exitcode"])
                self.assertLess(events[-1]["monotonic"], events[-1]["original_deadline"])

    def test_initialization_fault_cancel_and_missing_reap_never_pass(self):
        for case, reason in (("S4", "initialization-failed"), ("S6", "operator-cancelled"), ("S7", "completed")):
            with self.subTest(case=case):
                result, _ = self.run_case(case)
                self.assertEqual("FAIL", result["status"])
                self.assertEqual(reason, result["reason"])
                self.assertEqual("UNKNOWN" if case == "S7" else "REAPED", result["cleanup_status"])
                self.assertFalse(result["forced_parent_termination"])

    def test_original_deadline_is_not_reset_and_late_cleanup_is_not_success(self):
        result, events = self.run_case("S5", seconds=3)
        self.assertEqual("FAIL", result["status"])
        self.assertEqual("original-deadline-reached", result["reason"])
        self.assertEqual("REAPED", result["cleanup_status"])
        self.assertGreaterEqual(events[-1]["monotonic"], events[0]["original_deadline"])
        self.assertLess(events[-1]["monotonic"], events[0]["cleanup_deadline"])

    def test_journal_failure_after_launch_still_reaps_and_consumes(self):
        events = []
        def emit(event):
            events.append(event)
            if event["kind"] == "worker-observation":
                raise OSError("never publish raw detail")
        owner = RehearsalProcessOwner(case="S1", duration=15, emit=emit)
        result = owner.run_once()
        self.assertEqual("FAIL", result["status"])
        self.assertEqual("journal-failed", result["reason"])
        self.assertTrue(result["child_reap_observed"])
        self.assertNotIn("never publish raw detail", json.dumps(events))
        with self.assertRaises(ValueError):
            owner.run_once()

    def test_invalid_deadlines_and_arbitrary_command_are_not_launchable(self):
        for duration in (0, 61, True, float("nan"), float("inf"), "5"):
            with self.assertRaises(ValueError):
                RehearsalProcessOwner(case="S1", duration=duration, emit=lambda e: None)
        with self.assertRaises(ValueError):
            RehearsalProcessOwner(case="python arbitrary.py", duration=5, emit=lambda e: None)

    def test_unknown_process_identity_fails_closed_even_when_real_child_is_reaped(self):
        receive = process_support._receive
        def wrong_parent(channel):
            message = receive(channel)
            if message["kind"] == "identity":
                message["parent_pid"] = -1
            return message
        events = []
        with patch.object(process_support, "_receive", side_effect=wrong_parent):
            result = RehearsalProcessOwner(case="S1", duration=15, emit=events.append).run_once()
        self.assertEqual("FAIL", result["status"])
        self.assertEqual("UNKNOWN", result["cleanup_status"])
        self.assertTrue(result["child_reap_observed"])

    def test_real_isolated_launcher_with_spaces_unrelated_cwd_and_exclusive_returns(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp).resolve()
            code = parent / "bundle with spaces"
            for name in ("tools/native_owner_rehearsal.py", "src/lightyear_execution/mac_owner_process.py",
                         "src/lightyear_execution/__init__.py"):
                target = code / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / name, target)
            output = parent / "public returns"
            argv = [sys.executable, "-I", "-B", str(code / "tools/native_owner_rehearsal.py"),
                    "--case", "S2", "--output", str(output), "--seconds", "15", "--keys-unplugged"]
            completed = subprocess.run(argv, cwd=parent, capture_output=True, timeout=25, check=False)
            self.assertEqual(0, completed.returncode, completed.stdout.decode() + completed.stderr.decode())
            rows = (output / "events.jsonl").read_bytes().splitlines(keepends=True)
            previous = "0" * 64
            for sequence, raw in enumerate(rows, 1):
                row = json.loads(raw)
                self.assertEqual(sequence, row["sequence"])
                self.assertEqual(previous, row["previous_sha256"])
                previous = hashlib.sha256(raw).hexdigest()
            self.assertEqual("result", json.loads(rows[-1])["event"]["kind"])
            self.assertEqual("PASS", json.loads(rows[-1])["event"]["status"])
            before = (output / "events.jsonl").read_bytes()
            collision = subprocess.run(argv, cwd=parent, capture_output=True, timeout=5, check=False)
            self.assertEqual(2, collision.returncode)
            self.assertEqual(before, (output / "events.jsonl").read_bytes())

    def test_output_refuses_relative_traversal_and_existing_directory(self):
        with self.assertRaises(ValueError):
            PublicJournal(Path("relative"))
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp).resolve()
            with self.assertRaises(ValueError):
                PublicJournal(parent / ".." / "child")
            private = parent / "private parent"
            private.mkdir(mode=0o700)
            existing = private / "existing"
            existing.mkdir(mode=0o700)
            with self.assertRaises(FileExistsError):
                # The existing output must have an otherwise accepted parent;
                # /tmp itself is deliberately rejected as a writable parent.
                PublicJournal(existing)
            if os.name == "posix":
                public = parent / "world writable"
                public.mkdir(mode=0o700)
                public.chmod(0o777)
                try:
                    with self.assertRaisesRegex(ValueError, "output-parent-owner-or-mode-refused"):
                        PublicJournal(public / "new output")
                    self.assertFalse((public / "new output").exists())
                finally:
                    public.chmod(0o700)

    def test_closed_writer_during_cleanup_requires_real_reap_and_known_scope(self):
        poll = process_support._poll
        for case in ("S4", "S6", "S7"):
            with self.subTest(case=case):
                events = []
                def closed_writer(channel, timeout):
                    if any(e["kind"] == "cleanup-requested" for e in events):
                        error = OSError("private pipe detail")
                        error.winerror = 109
                        with patch.object(channel, "poll", side_effect=error):
                            return poll(channel, timeout)
                    return poll(channel, timeout)
                cancel = lambda: case == "S6" and any(
                    e["kind"] == "worker-observation" and e["observation"]["kind"] == "ready" for e in events)
                with patch.object(process_support, "_poll", side_effect=closed_writer):
                    result = RehearsalProcessOwner(case=case, duration=15, emit=events.append,
                                                  cancel_requested=cancel).run_once()
                self.assertEqual("FAIL", result["status"])
                self.assertEqual({"S4": "initialization-failed", "S6": "operator-cancelled",
                                  "S7": "completed"}[case], result["reason"])
                self.assertEqual("UNKNOWN" if case == "S7" else "REAPED", result["cleanup_status"])
                self.assertEqual(0, result["child_exitcode"])
                self.assertIsNone(result["cleanup_fault"])
                self.assertNotIn("private pipe detail", json.dumps(events))

    def test_other_pipe_error_keeps_first_fault_and_unknown_cleanup(self):
        poll = process_support._poll
        for code in (5, 6, 232):
            with self.subTest(winerror=code):
                events = []
                def broken_observation(channel, timeout):
                    if any(e["kind"] == "cleanup-requested" for e in events):
                        error = OSError("private pipe detail")
                        error.winerror = code
                        with patch.object(channel, "poll", side_effect=error):
                            return poll(channel, timeout)
                    return poll(channel, timeout)
                with patch.object(process_support, "_poll", side_effect=broken_observation):
                    result = RehearsalProcessOwner(case="S4", duration=15, emit=events.append).run_once()
                self.assertEqual("FAIL", result["status"])
                self.assertEqual("initialization-failed", result["reason"])
                self.assertEqual("UNKNOWN", result["cleanup_status"])
                self.assertEqual("cleanup-observation-unknown", result["cleanup_fault"])
                self.assertEqual(1, sum(e["kind"] == "cleanup-requested" for e in events))
                self.assertEqual(1, len({e["original_deadline"] for e in events}))
                self.assertNotIn("private pipe detail", json.dumps(events))

    def test_channel_closed_before_completion_never_becomes_pass(self):
        receive = process_support._receive
        for failure in (EOFError(), BrokenPipeError(), OSError(32, "private pipe detail")):
            events = []
            poll = process_support._poll
            def no_cleanup_poll(channel, timeout):
                self.assertFalse(any(e["kind"] == "cleanup-requested" for e in events))
                return poll(channel, timeout)
            def close_before_completed(channel):
                message = receive(channel)
                if message["kind"] == "completed":
                    with patch.object(channel, "recv_bytes", side_effect=failure):
                        return receive(channel)
                return message
            with patch.object(process_support, "_receive", side_effect=close_before_completed), \
                    patch.object(process_support, "_poll", side_effect=no_cleanup_poll):
                result = RehearsalProcessOwner(case="S1", duration=15, emit=events.append).run_once()
            self.assertEqual("FAIL", result["status"])
            self.assertEqual("worker-exited-before-completion", result["reason"])
            self.assertEqual(0, result["child_exitcode"])
            self.assertEqual("REAPED", result["cleanup_status"])
            self.assertNotIn("private pipe detail", json.dumps(events))

    def test_posix_operator_interrupt_targets_owner_then_owned_tree_cleanup(self):
        # Windows uses the callback cancellation probe; no Unix group signal there.
        if os.name != "posix":
            result, _ = self.run_case("S6")
            self.assertEqual("operator-cancelled", result["reason"])
            return
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp).resolve() / "interrupt"
            command = [sys.executable, "-I", "-B", str(root / "tools/native_owner_rehearsal.py"),
                       "--case", "S6", "--output", str(output), "--seconds", "15", "--keys-unplugged"]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True)
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if (output / "events.jsonl").exists():
                        rows = (output / "events.jsonl").read_bytes().splitlines()
                        if any(b'"kind":"ready"' in row for row in rows):
                            break
                    time.sleep(0.02)
                else:
                    self.fail("public worker did not become ready")
                os.killpg(process.pid, signal.SIGINT)  # CI-only owned new session, like terminal Ctrl-C.
                os.killpg(process.pid, signal.SIGINT)  # Repeated cancellation must not abort cleanup.
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(2, process.returncode, stderr.decode())
                final = json.loads(stdout.splitlines()[-1])
                self.assertEqual("operator-cancelled", final["reason"])
                self.assertEqual("REAPED", final["cleanup_status"])
                previous = "0" * 64
                for sequence, raw in enumerate((output / "events.jsonl").read_bytes().splitlines(keepends=True), 1):
                    row = json.loads(raw)
                    self.assertEqual(sequence, row["sequence"])
                    self.assertEqual(previous, row["previous_sha256"])
                    previous = hashlib.sha256(raw).hexdigest()
            finally:
                if process.poll() is None:
                    process.terminate()
                process.communicate(timeout=25)

    def test_no_undeclared_posix_child_or_resource_tracker_after_reap(self):
        if os.name != "posix":
            # Windows exercises the same pipe-stop owner, with positive reaps.
            self.assertEqual("REAPED", self.run_case("S3")[0]["cleanup_status"])
            return
        def children():
            process = subprocess.Popen(["ps", "-axo", "pid=,ppid="], stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(0, process.returncode, stderr.decode())
            return {int(pid) for line in stdout.splitlines() for pid, parent in [line.split()]
                    if int(parent) == os.getpid() and int(pid) != process.pid}
        before = children()
        for case in ("S1", "S3", "S4", "S6", "S7"):
            events, snapshots = [], []
            def observe(event):
                events.append(event)
                if event["kind"] == "worker-observation" and event["observation"]["kind"] == "ready":
                    declared = {e["observation"]["pid"] for e in events
                                if e["kind"] == "worker-observation"
                                and e["observation"].get("role") == "child"}
                    snapshots.append((children(), declared))
            owner = RehearsalProcessOwner(case=case, duration=15, emit=observe,
                cancel_requested=lambda: case == "S6" and bool(snapshots))
            result = owner.run_once()
            if case != "S4":
                self.assertEqual(1, len(snapshots))
                self.assertEqual(before | snapshots[0][1], snapshots[0][0])
            self.assertEqual(0, result["child_exitcode"])
            self.assertEqual(before, children())


class AdapterFaultEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.f = native_support.MacOwnerNativeTests()
        self.f.setUp()

    def test_unsorted_expected_and_observed_scope_is_canonical_without_deduplication(self):
        self.f.fixture.processes = tuple(reversed(self.f.fixture.processes))
        self.f.backend.enumerated = replace(self.f.observation, processes=self.f.fixture.processes)
        owner = self.f.make_owner()
        owner.start_once()
        record = json.loads(owner.cleanup_once())
        self.assertEqual([100, 101], [p["pid"] for p in record["processes"]])
        self.f.fixture.processes = (self.f.fixture.processes[0],) * 2
        with self.assertRaises(SigningRefused):
            self.f.make_owner()

    def test_fault_cleanup_evidence_retains_exception_partial_and_late_exact_result(self):
        for cleanup, expected in ((OSError("private arbitrary detail"), "cleanup-exception"),
                                  (replace(self.f.backend.cleaned, complete=False), "scope-unknown-or-incomplete"),
                                  (self.f.backend.cleaned, "scope-reaped-reported")):
            with self.subTest(expected=expected):
                backend = native_support.FixtureOwner(self.f.observation)
                original = RuntimeError("original fault")
                backend.launch_error = original
                self.f.backend = backend
                owner = self.f.make_owner()
                with patch.object(backend, "stop_and_reap_once", side_effect=cleanup if isinstance(cleanup, Exception) else None,
                                  return_value=cleanup) as reap:
                    with self.assertRaises(RuntimeError) as caught:
                        owner.start_once()
                self.assertIs(original, caught.exception)
                self.assertEqual(1, reap.call_count)
                evidence = owner.fault_cleanup_diagnostic
                record = json.loads(evidence)
                self.assertEqual(expected, record["outcome"])
                self.assertEqual(50, record["original_monotonic_deadline"])
                self.assertFalse(record["completion_authorized"])
                self.assertNotIn(b"private arbitrary", evidence)
                with self.assertRaises(SigningRefused):
                    owner.cleanup_once()
                self.assertEqual(evidence, owner.fault_cleanup_diagnostic)
