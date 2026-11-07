"""CI-only injected owner observations; no native process is started."""
from dataclasses import replace
import json
import unittest

from lightyear_execution.external_signing import SigningRefused
from lightyear_execution.mac_owner_native import (
    MacOwnerNativeAdapter, NativeProcessOwner, ProcessScopeObservation)
import test_mac_owner_lifecycle as fixture_support


class FixtureOwner(NativeProcessOwner):
    def __init__(self, observation):
        self.observation = observation
        self.calls = []
        self.launch_error = None
        self.enumerated = observation
        self.cleaned = replace(observation, exited_and_reaped=True)

    def launch_once(self, binding, deadline):
        self.calls.append(("launch", binding, deadline))
        if self.launch_error:
            raise self.launch_error
        return self.observation

    def enumerate_scope(self, binding, identity, deadline):
        self.calls.append(("enumerate", binding, deadline))
        return self.enumerated

    def stop_and_reap_once(self, binding, identity, deadline):
        self.calls.append(("reap", binding, deadline))
        return self.cleaned


class MacOwnerNativeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_support.MacOwnerLifecycleTests()
        self.fixture.setUp()
        self.observation = ProcessScopeObservation(
            self.fixture.binding, "a"*64, self.fixture.processes, True, False, False)
        self.backend = FixtureOwner(self.observation)
        self.owner = self.make_owner()

    def make_owner(self):
        return MacOwnerNativeAdapter(
            binding=self.fixture.binding, window=self.fixture.window,
            launch_identity_sha256="a"*64, expected_processes=self.fixture.processes,
            backend=self.backend, clock=self.fixture.clock)

    def test_complete_fixture_retains_nonqualifying_limits_and_original_deadline(self):
        self.owner.start_once()
        record = json.loads(self.owner.cleanup_once())
        self.assertFalse(record["native_proof"])
        self.assertFalse(record["admission_authorized"])
        self.assertEqual(["launch", "enumerate", "reap"], [c[0] for c in self.backend.calls])
        self.assertTrue(all(c[2] == 50 for c in self.backend.calls))
        with self.assertRaises(SigningRefused):
            self.owner.start_once()
        with self.assertRaises(SigningRefused):
            self.owner.cleanup_once()

    def test_launch_failure_attempts_cleanup_without_retry(self):
        self.backend.launch_error = OSError("uncertain launch")
        with self.assertRaises(OSError):
            self.owner.start_once()
        self.assertEqual(["launch", "reap"], [c[0] for c in self.backend.calls])
        with self.assertRaises(SigningRefused):
            self.owner.start_once()

    def test_child_escape_unknown_identity_mixed_launch_and_arbitrary_json_refused(self):
        faults = [replace(self.observation, escaped=True),
                  replace(self.observation, complete=False),
                  replace(self.observation, processes=self.fixture.processes[:1]),
                  replace(self.observation, launch_identity_sha256="b"*64),
                  {"complete": True}]
        for bad in faults:
            with self.subTest(bad=bad):
                self.backend = FixtureOwner(self.observation)
                self.backend.enumerated = bad
                owner = self.make_owner()
                with self.assertRaises(SigningRefused):
                    owner.start_once()
                self.assertEqual("reap", self.backend.calls[-1][0])

    def test_partial_cleanup_never_produces_complete_record(self):
        self.owner.start_once()
        self.backend.cleaned = replace(self.backend.cleaned, exited_and_reaped=False)
        with self.assertRaises(SigningRefused):
            self.owner.cleanup_once()
        with self.assertRaises(SigningRefused):
            self.owner.cleanup_once()

    def test_expiry_after_launch_still_requests_cleanup_without_extending_deadline(self):
        self.owner.start_once()
        self.fixture.mono = 51
        with self.assertRaises(SigningRefused):
            self.owner.cleanup_once()
        self.assertEqual(("reap", self.fixture.binding, 50), self.backend.calls[-1])

    def test_wall_expiry_and_clock_regression_fail_closed(self):
        from datetime import timedelta
        self.fixture.wall += timedelta(days=1)
        with self.assertRaises(SigningRefused):
            self.owner.start_once()
        self.assertNotIn("launch", [c[0] for c in self.backend.calls])
        self.fixture.setUp()
        self.backend = FixtureOwner(self.observation)
        owner = self.make_owner()
        owner.start_once()
        self.fixture.mono = 9
        with self.assertRaises(SigningRefused):
            owner.cleanup_once()
