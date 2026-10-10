"""Describe authenticated available evidence without inventing absent stages.

Authentication remains the adapter's responsibility. This module never signs,
loads keys, executes a workload or upgrades partial evidence to a complete run.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Completeness:
    required: tuple[str, ...]
    available: frozenset[str]

    @property
    def missing(self):
        return [name for name in self.required if name not in self.available]

    @property
    def complete(self):
        return not self.missing


def cleanup_error(error, complete):
    """Cleanup success cannot erase an earlier failure; failure overrides it."""
    if not complete:
        return {"kind": "equipment-failure", "exception_type": "CleanupIncomplete"}
    return error


def partial_equipment_summary(prefixes, required, available):
    """Called only after the adapter authenticates its signed available prefix."""
    return {"partial_evidence": True, "equipment_failure_audited": True,
            "collector_prefixes": prefixes,
            "missing_artifacts": Completeness(tuple(required), frozenset(available)).missing,
            "audit_scope": "authenticated preserved evidence only; no completed-stage or provenance claim"}
