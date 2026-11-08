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
        self._launch = launch_identity_sha256
        self._backend, self._clock = backend, clock
        self._lifecycle = MacOwnerLifecycle(binding=binding, window=window, processes=expected_processes, clock=clock)
        # Validate first in the lifecycle; sorting must never deduplicate scope.
        self._processes = tuple(sorted(expected_processes))
        self._pid, self._lock = os.getpid(), RLock()
        self._state, self._cleanup_consumed = "new", False
        self._fault_cleanup = None

    def _live(self):
        if os.getpid() != self._pid:
            raise SigningRefused("native-owner-process-changed")
        wall, mono = self._clock()
        self._window.check(self._binding.signing, wall=wall, monotonic=mono)

    def _scope_matches(self, observed, *, cleaned):
        return (type(observed) is ProcessScopeObservation
                and observed.binding == self._binding
                and observed.launch_identity_sha256 == self._launch
                and type(observed.processes) is tuple
                and all(type(p) is OwnerProcess for p in observed.processes)
                and tuple(sorted(observed.processes)) == self._processes
                and observed.complete is True and observed.escaped is False
                and observed.exited_and_reaped is cleaned)

    def _checked(self, observed, *, cleaned):
        if not self._scope_matches(observed, cleaned=cleaned):
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
        outcome = "not-attempted-process-changed"
        if not self._cleanup_consumed and os.getpid() == self._pid:
            self._cleanup_consumed = True
            try:
                observed = self._backend.stop_and_reap_once(
                    self._binding, self._launch, self._window.monotonic_deadline)
                outcome = ("scope-reaped-reported" if self._scope_matches(observed, cleaned=True)
                           else "scope-unknown-or-incomplete")
            except BaseException:
                # No raw exception text/class supplied by a backend in public data.
                outcome = "cleanup-exception"
        elif self._cleanup_consumed:
            outcome = "cleanup-already-consumed"
        self._fault_cleanup = canonical(dict(
            schema="mac-owner-fault-cleanup-diagnostic/1", binding=asdict(self._binding),
            launch_identity_sha256=self._launch,
            original_monotonic_deadline=self._window.monotonic_deadline,
            cleanup_attempted=self._cleanup_consumed, outcome=outcome,
            native_proof=False, completion_authorized=False, restart_authorized=False))

    @property
    def fault_cleanup_diagnostic(self):
        """Immutable public bytes, or None; caller must persist, not a receipt.

        Includes late cleanup reports without blessing them as in-window proof.
        The initial failure remains the raised exception and state stays failed.
        This memory alone cannot attest retention across owner-process death.
        """
        with self._lock:
            return self._fault_cleanup

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
