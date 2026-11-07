"""Inactive native-owner integration seam; no OS backend or launch entry point.

Only a trusted owner backend may supply typed observations. The seam never
accepts JSON as evidence of cleanup. Backend assertions and CI fixtures are not
native qualification; a separately reviewed supervised OS backend is required.
"""
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
import hashlib
import os
from threading import RLock

from lightyear_control_tower.decisions import canonical
from .external_signing import SigningRefused
from .mac_owner_lifecycle import MacOwnerLifecycle, OwnerLifecycleBinding, OwnerProcess


@dataclass(frozen=True)
class ProcessScopeObservation:
    binding: OwnerLifecycleBinding
    launch_identity_sha256: str
    processes: tuple[OwnerProcess, ...]
    complete: bool
    escaped: bool
    exited_and_reaped: bool


class NativeProcessOwner(ABC):
    """Trusted host seam; methods must honor the supplied ORIGINAL deadline.

    No implementation ships here. Enumerate the entire owned process scope,
    including descendants that leave the group; unknown identities and missing
    reap confirmation must never become complete observations.
    """

    @abstractmethod
    def launch_once(self, binding, original_deadline): ...

    @abstractmethod
    def enumerate_scope(self, binding, launch_identity, original_deadline): ...

    @abstractmethod
    def stop_and_reap_once(self, binding, launch_identity, original_deadline): ...


class MacOwnerNativeAdapter:
    def __init__(self, *, binding, window, launch_identity_sha256,
                 expected_processes, backend, clock):
        if not isinstance(backend, NativeProcessOwner):
            raise SigningRefused("native-owner-typed-backend-required")
        from .external_signing import _hex
        _hex(launch_identity_sha256, 64)
        self._binding, self._window = binding, window
        self._launch, self._processes = launch_identity_sha256, expected_processes
        self._backend, self._clock = backend, clock
        self._lifecycle = MacOwnerLifecycle(binding=binding, window=window, processes=expected_processes, clock=clock)
        self._pid, self._lock = os.getpid(), RLock()
        self._state, self._cleanup_consumed = "new", False

    def _live(self):
        if os.getpid() != self._pid:
            raise SigningRefused("native-owner-process-changed")
        wall, mono = self._clock()
        self._window.check(self._binding.signing, wall=wall, monotonic=mono)

    def _checked(self, observed, *, cleaned):
        if (type(observed) is not ProcessScopeObservation
                or observed.binding != self._binding
                or observed.launch_identity_sha256 != self._launch
                or type(observed.processes) is not tuple
                or any(type(p) is not OwnerProcess for p in observed.processes)
                or observed.processes != self._processes
                or observed.complete is not True or observed.escaped is not False
                or observed.exited_and_reaped is not cleaned):
            raise SigningRefused("native-scope-unknown-incomplete-or-mixed")
        self._live()

    def _observation(self, cleaned):
        wall, mono = self._clock()
        return canonical(dict(
            schema="mac-owner-lifecycle-observation/1",
            binding=asdict(self._binding),
            original_monotonic_deadline=self._window.monotonic_deadline,
            phase="cleaned" if cleaned else "started", sequence=2 if cleaned else 1,
            scope_complete=True, processes=[
                dict(**asdict(p), status="exited-and-reaped" if cleaned else "running")
                for p in self._processes],
            observed_at=wall.isoformat(), observed_monotonic=mono))

    def start_once(self):
        with self._lock:
            if self._state != "new":
                raise SigningRefused("native-start-consumed-no-resend")
            self._state = "consumed"
            try:
                self._live()
                observed = self._backend.launch_once(
                    self._binding, self._window.monotonic_deadline)
                self._checked(observed, cleaned=False)
                enumerated = self._backend.enumerate_scope(
                    self._binding, self._launch, self._window.monotonic_deadline)
                self._checked(enumerated, cleaned=False)
                raw = self._observation(False)
                self._lifecycle.observe_start_once(
                    raw, authenticated_observation_sha256=hashlib.sha256(raw).hexdigest())
                self._state = "started"
            except BaseException:
                self._state = "failed"
                # Launch uncertainty is never success. The owner still gets one
                # bounded cleanup request; errors cannot erase the first fault.
                self._cleanup_on_fault()
                raise

    def _cleanup_on_fault(self):
        if not self._cleanup_consumed and os.getpid() == self._pid:
            self._cleanup_consumed = True
            try:
                self._backend.stop_and_reap_once(
                    self._binding, self._launch, self._window.monotonic_deadline)
            except BaseException:
                pass

    def cleanup_once(self):
        with self._lock:
            if self._state != "started" or self._cleanup_consumed:
                raise SigningRefused("native-cleanup-unavailable-no-resume")
            self._cleanup_consumed, self._state = True, "consumed"
            try:
                if os.getpid() != self._pid:
                    raise SigningRefused("native-owner-process-changed")
                # Even after expiry request cleanup with the old deadline; an
                # expired window can never produce a successful record.
                observed = self._backend.stop_and_reap_once(
                    self._binding, self._launch, self._window.monotonic_deadline)
                self._checked(observed, cleaned=True)
                raw = self._observation(True)
                result = self._lifecycle.observe_cleanup_once(
                    raw, authenticated_observation_sha256=hashlib.sha256(raw).hexdigest())
                self._state = "complete"
                return result
            except BaseException:
                self._state = "failed"
                raise
