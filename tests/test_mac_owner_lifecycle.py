"""Disposable public observations only; no native ownership/cleanup qualification."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest
from unittest.mock import patch

from lightyear_control_tower.decisions import canonical
from lightyear_execution.external_signing import SigningBinding, SigningRefused, SigningWindow
from lightyear_execution.mac_owner_lifecycle import (
    MacOwnerLifecycle, OwnerLifecycleBinding, OwnerProcess,
)


class MacOwnerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.wall = datetime(2099, 1, 1, tzinfo=timezone.utc)
        self.mono = 10
        self.signing = SigningBinding("1" * 40, "2" * 64, "fixture-run", "case-1", 1,
                                      "2099-01-01T01:00:00Z")
        self.binding = OwnerLifecycleBinding(self.signing, "3" * 64, "4" * 64,
                                             "5" * 64, "6" * 64, "7" * 64)
        self.window = SigningWindow(self.signing.expires_at, 50)
        self.processes = (OwnerProcess(100, "8" * 64), OwnerProcess(101, "9" * 64))

    def clock(self):
        return self.wall, self.mono

    def owner(self, **changes):
        values = dict(binding=self.binding, window=self.window,
                      processes=self.processes, clock=self.clock)
        values.update(changes)
        return MacOwnerLifecycle(**values)

    def observation(self, phase="started", **changes):
        value = dict(
            schema="mac-owner-lifecycle-observation/1", binding=asdict(self.binding),
            original_monotonic_deadline=50, phase=phase,
            sequence=1 if phase == "started" else 2, scope_complete=True,
            processes=[dict(**asdict(p), status="running" if phase == "started"
                            else "exited-and-reaped") for p in self.processes],
            observed_at=self.wall.isoformat(), observed_monotonic=self.mono)
        value.update(changes)
        return canonical(value)

    def start(self, owner, raw=None, digest=None):
        raw = self.observation() if raw is None else raw
        owner.observe_start_once(raw, authenticated_observation_sha256=(
            hashlib.sha256(raw).hexdigest() if digest is None else digest))

    def cleanup(self, owner, raw=None, digest=None):
        raw = self.observation("cleaned") if raw is None else raw
        return owner.observe_cleanup_once(raw, authenticated_observation_sha256=(
            hashlib.sha256(raw).hexdigest() if digest is None else digest))

    def assert_failed(self, owner):
        with self.assertRaises(SigningRefused):
            self.start(owner)
        with self.assertRaises(SigningRefused):
            self.cleanup(owner)

    def test_exact_complete_scope_emits_nonqualifying_bound_record(self):
        owner = self.owner()
        started = self.observation()
        self.start(owner, started)
        self.wall += timedelta(seconds=1)
        self.mono += 1
        cleaned = self.observation("cleaned")
        result = self.cleanup(owner, cleaned)
        record = json.loads(result)
        self.assertEqual(canonical(record), result)
        self.assertEqual(record["binding"], asdict(self.binding))
        self.assertEqual(record["processes"], [asdict(p) for p in self.processes])
        self.assertEqual(record["original_monotonic_deadline"], 50)
        self.assertEqual(record["start_observation_sha256"], hashlib.sha256(started).hexdigest())
        self.assertEqual(record["cleanup_observation_sha256"], hashlib.sha256(cleaned).hexdigest())
        for field in ("native_proof", "admission_authorized", "automatic_resend", "restart_authorized"):
            self.assertIs(record[field], False)
        with self.assertRaises(SigningRefused):
            self.cleanup(owner)
        self.assert_failed(owner)

    def test_cleanup_without_start_consumes_attempt(self):
        owner = self.owner()
        with self.assertRaises(SigningRefused):
            self.cleanup(owner)
        self.assert_failed(owner)

    def test_second_start_refuses_without_resend(self):
        owner = self.owner()
        self.start(owner)
        with self.assertRaises(SigningRefused):
            self.start(owner)
        self.assert_failed(owner)

    def test_every_exact_binding_field_is_required(self):
        original = asdict(self.binding)
        variants = []
        for name in original:
            if name != "signing":
                variants.append({**original, name: "a" * 64})
        for name, replacement in dict(
                source_commit="b" * 40, work_order_sha256="c" * 64, run_id="other",
                case_id="other", attempt=2, expires_at="2099-01-01T02:00:00Z").items():
            variants.append({**original, "signing": {**original["signing"], name: replacement}})
        for variant in variants:
            with self.subTest(binding=variant):
                owner = self.owner()
                with self.assertRaises(SigningRefused):
                    self.start(owner, self.observation(binding=variant))
                self.assert_failed(owner)

    def test_schema_sequence_deadline_and_scope_are_exact(self):
        for fields in (
                dict(schema="other"), dict(sequence=True), dict(sequence=2),
                dict(phase="cleaned"), dict(original_monotonic_deadline=51),
                dict(original_monotonic_deadline=True), dict(scope_complete=False),
                dict(scope_complete=None), dict(scope_complete=1), dict(extra=False)):
            with self.subTest(fields=fields):
                owner = self.owner()
                with self.assertRaises(SigningRefused):
                    self.start(owner, self.observation(**fields))
                self.assert_failed(owner)

    def test_authenticated_digest_is_independent_of_returned_bytes(self):
        for phase in ("started", "cleaned"):
            owner = self.owner()
            if phase == "cleaned":
                self.start(owner)
            with self.assertRaises(SigningRefused):
                (self.start if phase == "started" else self.cleanup)(owner, digest="0" * 64)
            self.assert_failed(owner)

    def test_unknown_missing_extra_duplicate_and_pid_reuse_refuse(self):
        for phase in ("started", "cleaned"):
            processes = json.loads(self.observation(phase))["processes"]
            variants = [
                [], processes[:1], processes + [processes[0]],
                [processes[0], {**processes[1], "pid": 102}],
                [processes[0], {**processes[1], "birth_identity_sha256": "a" * 64}],
                [processes[0], {**processes[1], "status": "unknown"}],
                [processes[0], {**processes[1], "status": "exited"}],
                [processes[0], {**processes[1], "status": "running"}],
                [processes[0], {**processes[1], "extra": True}], None,
            ]
            if phase == "started":
                variants.pop(7)  # Running is the required start state.
            for variant in variants:
                with self.subTest(phase=phase, processes=variant):
                    owner = self.owner()
                    if phase == "cleaned":
                        self.start(owner)
                    raw = self.observation(phase, processes=variant)
                    with self.assertRaises(SigningRefused):
                        (self.start if phase == "started" else self.cleanup)(owner, raw)
                    self.assert_failed(owner)

    def test_canonical_json_and_closed_fields_required(self):
        raw = self.observation()
        malformed = [raw + b"\n", raw[:-1] + b',"phase":"started"}',
                     b"[]", b"{}", b"null", b"\xff", b"", raw.decode()]
        for value in malformed:
            with self.subTest(value=value):
                owner = self.owner()
                with self.assertRaises(SigningRefused):
                    self.start(owner, value, digest="0" * 64)
                self.assert_failed(owner)

    def test_no_deadline_rebase_on_delayed_cleanup(self):
        for mono in (50, 60):
            owner = self.owner()
            self.start(owner)
            self.mono = mono
            with self.assertRaises(SigningRefused):
                self.cleanup(owner)
            self.assert_failed(owner)
            self.mono = 10

    def test_original_wall_deadline_including_exact_boundary(self):
        owner = self.owner()
        self.start(owner)
        self.wall += timedelta(hours=1)
        with self.assertRaises(SigningRefused):
            self.cleanup(owner)
        self.assert_failed(owner)

    def test_observation_times_cannot_be_old_future_unknown_or_regress(self):
        variants = [
            dict(observed_monotonic=9), dict(observed_monotonic=11),
            dict(observed_monotonic=True), dict(observed_monotonic=None),
            dict(observed_at="2099-01-01T00:00:00"),  # Offset required.
            dict(observed_at="2098-12-31T23:59:59Z"),
            dict(observed_at="2099-01-01T00:00:01Z"),
        ]
        for fields in variants:
            owner = self.owner()
            with self.assertRaises(SigningRefused):
                self.start(owner, self.observation(**fields))
            self.assert_failed(owner)
        owner = self.owner()
        self.mono = 12
        self.wall += timedelta(seconds=2)
        self.start(owner)
        with self.assertRaises(SigningRefused):
            self.cleanup(owner, self.observation("cleaned", observed_monotonic=11))
        self.assert_failed(owner)

    def test_receiving_clock_regression_and_owner_process_change_refuse(self):
        for change in ("wall", "mono", "pid"):
            owner = self.owner()
            self.start(owner)
            if change == "wall":
                self.wall -= timedelta(seconds=1)
            elif change == "mono":
                self.mono = 9
            with patch("lightyear_execution.mac_owner_lifecycle.os.getpid",
                       return_value=-1 if change == "pid" else owner._pid):
                with self.assertRaises(SigningRefused):
                    self.cleanup(owner)
            self.assert_failed(owner)
            self.wall = datetime(2099, 1, 1, tzinfo=timezone.utc)
            self.mono = 10

    def test_expiry_during_observation_consumes_attempt(self):
        readings = [(self.wall, 10), (self.wall, 11), (self.wall, 50)]
        owner = self.owner(clock=lambda: readings.pop(0))
        with self.assertRaises(SigningRefused):
            self.start(owner)
        self.assert_failed(owner)

    def test_adapter_uncertainty_is_fail_stop(self):
        calls = [0]
        def failing_clock():
            calls[0] += 1
            if calls[0] == 2:
                raise RuntimeError("fixture observation source unavailable")
            return self.clock()
        owner = self.owner(clock=failing_clock)
        with self.assertRaises(RuntimeError):
            self.start(owner)
        self.assert_failed(owner)

    def test_unknown_controller_clock_refuses_before_observation(self):
        for reading in ((None, 10), (self.wall, None), (self.wall, float("nan")),
                        (self.wall, True), (self.wall.replace(tzinfo=None), 10)):
            with self.subTest(reading=reading), self.assertRaises(SigningRefused):
                self.owner(clock=lambda: reading)

    def test_invalid_or_ambiguous_controller_scope_refuses(self):
        for processes in ((), list(self.processes), (self.processes[0],) * 2,
                          (self.processes[0], replace(self.processes[1], pid=100)),
                          (self.processes[0], replace(self.processes[1], birth_identity_sha256="8"*64))):
            with self.subTest(processes=processes), self.assertRaises(SigningRefused):
                self.owner(processes=processes)
        for pid in (True, 0, -1, "100"):
            with self.assertRaises(SigningRefused):
                OwnerProcess(pid, "8" * 64)
        with self.assertRaises(SigningRefused):
            OwnerProcess(100, "not-a-digest")
        with self.assertRaises(SigningRefused):
            replace(self.binding, owner_identity_sha256="not-a-digest")
        with self.assertRaises(SigningRefused):
            self.owner(window=SigningWindow("2099-01-01T02:00:00Z", 50))


if __name__ == "__main__":
    unittest.main()
