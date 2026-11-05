"""One-attempt public observations of an isolated Mac owner's lifecycle.

This records injected observations, never starts, kills, reaps, signs, decrypts,
authenticates, admits or retries anything. The admitted owner supplies the exact
binding and a CLOSED all-process scope (including descendants and helpers).
A native adapter must independently establish that scope and authenticate each
observation before supplying its retained digest. A digest alone is not
authentication. Fixture success is not native ownership or cleanup proof.

There is no persistence or recovery API: reconstructing this object must never
authorize a second attempt. The controller's durable attempt journal remains
responsible for single-owner admission across object/process restarts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import math
import os
from threading import RLock
import time

from lightyear_control_tower.decisions import canonical
from .external_signing import SigningBinding, SigningRefused, SigningWindow, _hex, _json, _time


@dataclass(frozen=True, order=True)
class OwnerProcess:
    """Public PID plus independently established birth identity; PID alone is insufficient."""

    pid: int
    birth_identity_sha256: str

    def __post_init__(self):
        if type(self.pid) is not int or not 1 <= self.pid <= 2147483647:
            raise SigningRefused("invalid-owner-process")
        _hex(self.birth_identity_sha256, 64)


@dataclass(frozen=True)
class OwnerLifecycleBinding:
    signing: SigningBinding
    execution_identity_sha256: str
    attempt_identity_sha256: str
    owner_identity_sha256: str
    process_scope_sha256: str
    clock_identity_sha256: str

    def __post_init__(self):
        if type(self.signing) is not SigningBinding:
            raise SigningRefused("exact-signing-binding-required")
        for name in ("execution_identity_sha256", "attempt_identity_sha256",
                     "owner_identity_sha256", "process_scope_sha256", "clock_identity_sha256"):
            _hex(getattr(self, name), 64)


def _clock():
    return datetime.now(timezone.utc), time.monotonic()


class MacOwnerLifecycle:
    """Consume one start and one complete cleanup observation, fail-stop on uncertainty.

    The optional clock is an injectable CI seam, not an alternative production
    clock authority. Observation monotonic timestamps must use the SAME original
    domain named by clock_identity_sha256. All deadline values come from original
    admission; the class cannot extend them. Cleanup is still physically required
    after expiry, but late evidence cannot complete this in-window record.
    """

    def __init__(self, *, binding: OwnerLifecycleBinding, window: SigningWindow,
                 processes: tuple[OwnerProcess, ...], clock=None):
        if type(binding) is not OwnerLifecycleBinding or type(window) is not SigningWindow:
            raise SigningRefused("exact-lifecycle-binding-and-window-required")
        if (type(processes) is not tuple or not 0 < len(processes) <= 1024
                or any(type(p) is not OwnerProcess for p in processes)
                or len({p.pid for p in processes}) != len(processes)
                or len({p.birth_identity_sha256 for p in processes}) != len(processes)):
            raise SigningRefused("closed-distinct-process-scope-required")
        if clock is not None and not callable(clock):
            raise SigningRefused("invalid-lifecycle-clock")
        self._binding, self._window = binding, window
        self._processes = tuple(sorted(processes))
        self._clock = _clock if clock is None else clock
        self._pid, self._lock = os.getpid(), RLock()
        self._state = "new"
        self._last_wall = self._last_monotonic = None
        self._last_observation_wall = self._last_observation_monotonic = None
        self._start_sha256 = None
        wall, mono = self._now()
        self._opened_wall, self._opened_monotonic = wall, mono

    def _now(self):
        if os.getpid() != self._pid:
            raise SigningRefused("owner-process-changed")
        wall, mono = self._clock()
        if wall is None or mono is None:
            raise SigningRefused("owner-clock-unknown")
        self._window.check(self._binding.signing, wall=wall, monotonic=mono)
        if (self._last_monotonic is not None
                and (mono < self._last_monotonic or wall < self._last_wall)):
            raise SigningRefused("owner-clock-regressed")
        self._last_wall, self._last_monotonic = wall, mono
        return wall, mono

    def _consume(self, raw: bytes, digest: str, *, phase: str, state: str, sequence: int):
        if self._state != state:
            raise SigningRefused("lifecycle-order-or-replay")
        # Consume before parsing so a malformed/ambiguous observation cannot be retried.
        self._state = "consumed"
        wall, mono = self._now()
        value = _json(raw)
        if hashlib.sha256(raw).hexdigest() != _hex(digest, 64):
            raise SigningRefused("authenticated-observation-digest-mismatch")
        expected_fields = {"schema", "binding", "original_monotonic_deadline", "phase",
                           "sequence", "scope_complete", "processes", "observed_at",
                           "observed_monotonic"}
        if set(value) != expected_fields:
            raise SigningRefused("lifecycle-observation-fields")
        if (value["schema"] != "mac-owner-lifecycle-observation/1"
                or canonical(value["binding"]) != canonical(asdict(self._binding))
                or type(value["original_monotonic_deadline"]) not in (int, float)
                or value["original_monotonic_deadline"] != self._window.monotonic_deadline
                or value["phase"] != phase
                or type(value["sequence"]) is not int or value["sequence"] != sequence
                or value["scope_complete"] is not True):
            raise SigningRefused("lifecycle-binding-or-incomplete-scope")
        observed_wall = _time(value["observed_at"])
        observed_mono = value["observed_monotonic"]
        if (type(observed_mono) not in (int, float) or not math.isfinite(observed_mono)
                or not self._opened_monotonic <= observed_mono <= mono
                or not self._opened_wall <= observed_wall <= wall
                or (self._last_observation_monotonic is not None
                    and (observed_mono < self._last_observation_monotonic
                         or observed_wall < self._last_observation_wall))):
            raise SigningRefused("lifecycle-observation-time")
        # Exact inventory includes every expected child/helper birth identity, once.
        # Missing, extra, duplicate, PID-reused or unknown-status entries all refuse.
        status = "running" if phase == "started" else "exited-and-reaped"
        expected_processes = [dict(**asdict(p), status=status) for p in self._processes]
        if canonical(value["processes"]) != canonical(expected_processes):
            raise SigningRefused("all-process-lifecycle-observation-required")
        self._now()
        self._last_observation_wall = observed_wall
        self._last_observation_monotonic = observed_mono
        return digest

    def observe_start_once(self, observation: bytes, *, authenticated_observation_sha256: str):
        """Caller first authenticates the source and retains exact bytes independently."""
        with self._lock:
            try:
                self._start_sha256 = self._consume(
                    observation, authenticated_observation_sha256,
                    phase="started", state="new", sequence=1)
                self._state = "started"
            except BaseException:
                self._state = "failed"
                raise

    def observe_cleanup_once(self, observation: bytes, *,
                             authenticated_observation_sha256: str) -> bytes:
        """Return a public consistency record only after every scoped process is reported reaped."""
        with self._lock:
            try:
                cleanup_sha = self._consume(
                    observation, authenticated_observation_sha256,
                    phase="cleaned", state="started", sequence=2)
                result = canonical(dict(
                    schema="mac-owner-lifecycle-record/1",
                    binding=asdict(self._binding),
                    original_monotonic_deadline=self._window.monotonic_deadline,
                    processes=[asdict(p) for p in self._processes],
                    start_observation_sha256=self._start_sha256,
                    cleanup_observation_sha256=cleanup_sha,
                    automatic_resend=False, restart_authorized=False,
                    native_proof=False, admission_authorized=False))
                self._now()
                self._state = "complete"
                return result
            except BaseException:
                self._state = "failed"
                raise
