"""Evidence strength within an explicitly declared, compatible class family.

An observed location is not a universal ranking of platforms. Keep lane labels
alongside the combined class; do not compare unrelated class vocabularies.
"""
from __future__ import annotations

RUNTIME_EVIDENCE_LEVELS = ("simulated", "local_observed", "zos_observed")


def evidence_floor(*classes: str | None, levels: tuple[str, ...] = RUNTIME_EVIDENCE_LEVELS) -> str:
    if not levels or levels[0] != "simulated" or len(set(levels)) != len(levels):
        raise ValueError("Evidence levels must start with simulated and contain no duplicates")
    values = tuple("simulated" if value is None else value for value in classes) or ("simulated",)
    if any(value not in levels for value in values):
        raise ValueError("Unsupported evidence class in combined evidence")
    return min(values, key=levels.index)
