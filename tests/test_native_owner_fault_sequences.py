"""CI-only fault-SEQUENCE negatives for the inactive native-owner seam.

Every observation here is a typed synthetic ProcessScopeObservation produced by
an in-test NativeProcessOwner fake, read against an in-memory clock. Nothing is
launched, stopped, reaped or signed. Passing proves seam behaviour only; it is
not native ownership, cleanup or qualification proof.
"""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest
from unittest.mock import patch

from lightyear_control_tower.decisions import canonical
from lightyear_execution.external_signing import SigningBinding, SigningRefused, SigningWindow
from lightyear_execution.mac_owner_lifecycle import (
    MacOwnerLifecycle, OwnerLifecycleBinding, OwnerProcess)
from lightyear_execution.mac_owner_native import (
    MacOwnerNativeAdapter, NativeProcessOwner, ProcessScopeObservation)

WALL0 = datetime(2099, 1, 1, tzinfo=timezone.utc)
MONO0 = 10
EXPIRES_AT = "2099-01-01T01:00:00Z"
EXPIRES_DT = datetime(2099, 1, 1, 1, tzinfo=timezone.utc)
DEADLINE = 50  # Original admission monotonic deadline; must never be rebased.
LAUNCH = "a" * 64
SCOPE_REFUSED = "native-scope-unknown-incomplete-or-mixed"
CLEANUP_UNAVAILABLE = "native-cleanup-unavailable-no-resume"
WINDOW_CLOSED = "original-signing-window-closed"

_ORIG_OBSERVE_START = MacOwnerLifecycle.observe_start_once
_ORIG_OBSERVE_CLEANUP = MacOwnerLifecycle.observe_cleanup_once


class FakeClock:
    """In-memory (wall, monotonic) source; never reads or changes the OS clock."""

    def __init__(self, wall=WALL0, mono=MONO0):
        self.wall, self.mono = wall, mono

    def __call__(self):
        return self.wall, self.mono

    def advance(self, seconds):
        self.wall += timedelta(seconds=seconds)
        self.mono += seconds


class ScriptedOwner(NativeProcessOwner):
    """Typed fake owner: each step returns a value, raises an exception, or calls a function."""

    def __init__(self, *, launch_step, enumerate_step, reap_step):
        self.script = {"launch": launch_step, "enumerate": enumerate_step, "reap": reap_step}
        self.calls = []

    def _step(self, phase, binding, identity, deadline):
        self.calls.append((phase, binding, identity, deadline))
        action = self.script[phase]
        if isinstance(action, BaseException):
            raise action
        if callable(action):
            return action(binding, identity, deadline)
        return action

    def launch_once(self, binding, original_deadline):
        return self._step("launch", binding, None, original_deadline)

    def enumerate_scope(self, binding, launch_identity, original_deadline):
        return self._step("enumerate", binding, launch_identity, original_deadline)

    def stop_and_reap_once(self, binding, launch_identity, original_deadline):
        return self._step("reap", binding, launch_identity, original_deadline)


def phases(backend):
    return [call[0] for call in backend.calls]


@contextmanager
def lifecycle_spies():
    """Spy (not replace) the lifecycle sinks so fabricated proof would be visible."""
    with patch.object(MacOwnerLifecycle, "observe_start_once", autospec=True,
                      side_effect=_ORIG_OBSERVE_START) as start_spy, \
            patch.object(MacOwnerLifecycle, "observe_cleanup_once", autospec=True,
                         side_effect=_ORIG_OBSERVE_CLEANUP) as cleanup_spy:
        yield start_spy, cleanup_spy


class NativeOwnerFaultSequenceTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.signing = SigningBinding("1" * 40, "2" * 64, "fixture-run", "case-1", 1, EXPIRES_AT)
        self.binding = OwnerLifecycleBinding(self.signing, "3" * 64, "4" * 64,
                                             "5" * 64, "6" * 64, "7" * 64)
        self.window = SigningWindow(EXPIRES_AT, DEADLINE)
        self.processes = (OwnerProcess(100, "8" * 64), OwnerProcess(101, "9" * 64))

    def obs(self, *, processes=None, complete=True, escaped=False, reaped=False):
        return ProcessScopeObservation(
            self.binding, LAUNCH, self.processes if processes is None else processes,
            complete, escaped, reaped)

    def adapter(self, backend):
        return MacOwnerNativeAdapter(
            binding=self.binding, window=self.window, launch_identity_sha256=LAUNCH,
            expected_processes=self.processes, backend=backend, clock=self.clock)

    def assert_terminal(self, owner, backend, expected_phases):
        """No restart, no resumed cleanup, and no further owner traffic."""
        with self.assertRaises(SigningRefused):
            owner.start_once()
        with self.assertRaises(SigningRefused) as ctx:
            owner.cleanup_once()
        self.assertEqual(CLEANUP_UNAVAILABLE, str(ctx.exception))
        self.assertEqual(expected_phases, phases(backend))

    def expected_raw(self, phase, wall, mono):
        # Mirrors MacOwnerNativeAdapter._observation (mac_owner_native.py:78-88).
        status = "running" if phase == "started" else "exited-and-reaped"
        return canonical(dict(
            schema="mac-owner-lifecycle-observation/1", binding=asdict(self.binding),
            original_monotonic_deadline=DEADLINE, phase=phase,
            sequence=1 if phase == "started" else 2, scope_complete=True,
            processes=[dict(**asdict(p), status=status) for p in self.processes],
            observed_at=wall.isoformat(), observed_monotonic=mono))

    def test_launch_uncertainty_then_cleanup_exception_preserves_first_failure_and_blocks_restart(self):
        cases = (
            ("launch-raises", OSError("synthetic uncertain launch"), OSError,
             "synthetic uncertain launch"),
            ("launch-reports-incomplete-scope", self.obs(complete=False), SigningRefused,
             SCOPE_REFUSED),
        )
        for label, launch_step, first_type, first_message in cases:
            with self.subTest(label):
                cleanup_error = RuntimeError("synthetic cleanup failure")
                backend = ScriptedOwner(launch_step=launch_step, enumerate_step=self.obs(),
                                        reap_step=cleanup_error)
                owner = self.adapter(backend)
                with lifecycle_spies() as (start_spy, cleanup_spy):
                    with self.assertRaises(first_type) as ctx:
                        owner.start_once()
                    start_spy.assert_not_called()
                    cleanup_spy.assert_not_called()
                # The FIRST fault surfaces; the cleanup exception never replaces it.
                self.assertIsNot(cleanup_error, ctx.exception)
                self.assertNotIsInstance(ctx.exception, RuntimeError)
                self.assertEqual(first_message, str(ctx.exception))
                if isinstance(launch_step, BaseException):
                    self.assertIs(launch_step, ctx.exception)
                # Exactly one cleanup request, bound to the ORIGINAL deadline; no enumerate.
                self.assertEqual(["launch", "reap"], phases(backend))
                self.assertEqual(("reap", self.binding, LAUNCH, DEADLINE), backend.calls[-1])
                self.assertEqual(DEADLINE, backend.calls[0][3])
                self.assert_terminal(owner, backend, ["launch", "reap"])

    def test_valid_launch_then_enumeration_fault_and_failing_reentrant_cleanup_never_completes(self):
        variants = (
            ("identity-mismatch", self.obs(processes=(
                self.processes[0], OwnerProcess(101, "c" * 64)))),
            ("coverage-missing-process", self.obs(processes=self.processes[:1])),
            ("coverage-incomplete", self.obs(complete=False)),
        )
        for label, enumerated in variants:
            with self.subTest(label):
                backend = ScriptedOwner(launch_step=self.obs(), enumerate_step=enumerated,
                                        reap_step=None)
                owner = self.adapter(backend)
                reentry = []

                def reap(binding, identity, deadline, _owner=owner, _backend=backend,
                         _log=reentry):
                    if phases(_backend).count("reap") > 1:
                        raise RuntimeError("re-entered cleanup")  # Guard against recursion.
                    for name in ("cleanup_once", "start_once"):
                        try:
                            getattr(_owner, name)()
                        except BaseException as exc:  # Record any re-entry outcome.
                            _log.append((name, type(exc).__name__))
                        else:
                            _log.append((name, "accepted"))
                    raise RuntimeError("synthetic cleanup failure")

                backend.script["reap"] = reap
                with lifecycle_spies() as (start_spy, cleanup_spy):
                    with self.assertRaises(SigningRefused) as ctx:
                        owner.start_once()
                    self.assertEqual(SCOPE_REFUSED, str(ctx.exception))
                    # Re-entry from inside the owner's cleanup is refused, not resumed.
                    self.assertEqual([("cleanup_once", "SigningRefused"),
                                      ("start_once", "SigningRefused")], reentry)
                    self.assertEqual(["launch", "enumerate", "reap"], phases(backend))
                    self.assertTrue(all(call[3] == DEADLINE for call in backend.calls))
                    self.assert_terminal(owner, backend, ["launch", "enumerate", "reap"])
                    # No lifecycle record of any kind, so no complete success exists.
                    start_spy.assert_not_called()
                    cleanup_spy.assert_not_called()

    def test_exact_boundary_expiry_during_enumeration_keeps_original_deadline_and_rejects_late_success(self):
        boundaries = (
            ("monotonic-equals-deadline", lambda clock: setattr(clock, "mono", DEADLINE)),
            ("wall-equals-expiry", lambda clock: setattr(clock, "wall", EXPIRES_DT)),
        )
        for label, expire in boundaries:
            with self.subTest(label):
                self.clock = FakeClock()
                good = self.obs()

                def enumerate_then_expire(binding, identity, deadline, _clock=self.clock,
                                          _expire=expire, _good=good):
                    _expire(_clock)
                    return _good  # Otherwise perfect, but observed at the boundary.

                backend = ScriptedOwner(launch_step=good, enumerate_step=enumerate_then_expire,
                                        reap_step=self.obs(reaped=True))
                owner = self.adapter(backend)
                with lifecycle_spies() as (start_spy, cleanup_spy):
                    with self.assertRaises(SigningRefused) as ctx:
                        owner.start_once()
                    self.assertEqual(WINDOW_CLOSED, str(ctx.exception))
                    self.assertEqual(["launch", "enumerate", "reap"], phases(backend))
                    # Cleanup still requested once, with the ORIGINAL deadline (not rebased).
                    self.assertEqual([DEADLINE] * 3, [call[3] for call in backend.calls])
                    self.assertEqual(("reap", self.binding, LAUNCH, DEADLINE), backend.calls[-1])
                    # A perfect reaped report after expiry still cannot complete anything.
                    self.assert_terminal(owner, backend, ["launch", "enumerate", "reap"])
                    start_spy.assert_not_called()
                    cleanup_spy.assert_not_called()

    def test_pid_reuse_with_different_birth_identity_refused_despite_matching_pids_and_count(self):
        reused_scopes = (
            ("fresh-birth-identity", (OwnerProcess(100, "8" * 64), OwnerProcess(101, "c" * 64))),
            ("swapped-birth-identities", (OwnerProcess(100, "9" * 64), OwnerProcess(101, "8" * 64))),
        )
        for when in ("enumeration", "cleanup"):
            for label, reused in reused_scopes:
                with self.subTest(when=when, scope=label):
                    # Preconditions: PID numbers and count match exactly; digests do not.
                    self.assertEqual([p.pid for p in self.processes], [p.pid for p in reused])
                    self.assertEqual(len(self.processes), len(reused))
                    self.assertNotEqual(self.processes, reused)
                    if when == "enumeration":
                        backend = ScriptedOwner(
                            launch_step=self.obs(), enumerate_step=self.obs(processes=reused),
                            reap_step=self.obs(reaped=True))
                    else:
                        backend = ScriptedOwner(
                            launch_step=self.obs(), enumerate_step=self.obs(),
                            reap_step=self.obs(processes=reused, reaped=True))
                    owner = self.adapter(backend)
                    with lifecycle_spies() as (start_spy, cleanup_spy):
                        if when == "enumeration":
                            with self.assertRaises(SigningRefused) as ctx:
                                owner.start_once()
                            start_spy.assert_not_called()
                        else:
                            owner.start_once()
                            self.assertEqual(1, start_spy.call_count)
                            with self.assertRaises(SigningRefused) as ctx:
                                owner.cleanup_once()
                        self.assertEqual(SCOPE_REFUSED, str(ctx.exception))
                        # The adapter must not synthesize an all-process record from
                        # expected inventory when the observed identities differ.
                        cleanup_spy.assert_not_called()
                        self.assert_terminal(owner, backend, ["launch", "enumerate", "reap"])
                        cleanup_spy.assert_not_called()

    def test_duplicate_cleanup_after_failed_or_partial_first_cleanup_stays_consumed(self):
        variants = (
            ("reap-raises", OSError("synthetic reap failure"), OSError),
            ("partial-not-reaped", self.obs(reaped=False), SigningRefused),
            ("descendant-escaped-during-cleanup", self.obs(reaped=True, escaped=True),
             SigningRefused),
        )
        for label, first_reap, first_type in variants:
            with self.subTest(label):
                backend = ScriptedOwner(launch_step=self.obs(), enumerate_step=self.obs(),
                                        reap_step=first_reap)
                owner = self.adapter(backend)
                owner.start_once()
                with lifecycle_spies() as (_, cleanup_spy):
                    with self.assertRaises(first_type):
                        owner.cleanup_once()
                    # The owner would now report a perfect cleanup; it must never be asked.
                    backend.script["reap"] = self.obs(reaped=True)
                    for _ in range(2):
                        with self.assertRaises(SigningRefused) as ctx:
                            owner.cleanup_once()
                        self.assertEqual(CLEANUP_UNAVAILABLE, str(ctx.exception))
                    self.assert_terminal(owner, backend, ["launch", "enumerate", "reap"])
                    cleanup_spy.assert_not_called()

    def test_exact_synthetic_sequence_completes_once_and_retains_nonqualifying_flags(self):
        backend = ScriptedOwner(launch_step=self.obs(), enumerate_step=self.obs(),
                                reap_step=self.obs(reaped=True))
        owner = self.adapter(backend)
        with lifecycle_spies() as (start_spy, cleanup_spy):
            self.assertIsNone(owner.start_once())
            started_at = (self.clock.wall, self.clock.mono)
            self.clock.advance(1)
            raw = owner.cleanup_once()
            cleaned_at = (self.clock.wall, self.clock.mono)
            self.assertEqual(1, start_spy.call_count)
            self.assertEqual(1, cleanup_spy.call_count)
        record = json.loads(raw)
        self.assertEqual(canonical(record), raw)
        for field in ("native_proof", "admission_authorized", "automatic_resend",
                      "restart_authorized"):
            self.assertIs(False, record[field])
        self.assertEqual(DEADLINE, record["original_monotonic_deadline"])
        self.assertEqual(asdict(self.binding), record["binding"])
        self.assertEqual([asdict(p) for p in self.processes], record["processes"])
        self.assertEqual(hashlib.sha256(self.expected_raw("started", *started_at)).hexdigest(),
                         record["start_observation_sha256"])
        self.assertEqual(hashlib.sha256(self.expected_raw("cleaned", *cleaned_at)).hexdigest(),
                         record["cleanup_observation_sha256"])
        self.assertEqual([("launch", self.binding, None, DEADLINE),
                          ("enumerate", self.binding, LAUNCH, DEADLINE),
                          ("reap", self.binding, LAUNCH, DEADLINE)], backend.calls)
        self.assert_terminal(owner, backend, ["launch", "enumerate", "reap"])


if __name__ == "__main__":
    unittest.main()
