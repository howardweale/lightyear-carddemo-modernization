"""Scope-aware wording derived from receipt counts, never from milestone names."""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import seal


def coverage_statement(counts: Mapping[str, Any]) -> str:
    names = ("catalogued_behavior_count", "bounded_model_verified_behavior_count",
             "native_oracle_verified_behavior_count")
    values = [counts[name] for name in names]
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("Coverage counts must be explicit nonnegative integers")
    catalogued, bounded, native = values
    if bounded > catalogued or native > catalogued:
        raise ValueError("Verified behavior counts cannot exceed the catalog")
    return (
        f"This catalog receipt covers {catalogued:,} catalogued behaviours: "
        f"{bounded:,}/{catalogued:,} bounded-model verified and "
        f"{native:,}/{catalogued:,} native-Oracle verified. "
        "These counts exclude separate application-level evidence such as CloudBank runs; "
        "they do not establish target equivalence or production readiness."
    )


def seal_coverage(payload: dict[str, Any]) -> dict[str, Any]:
    # The foundation receipt predates the common catalogued count name.
    if "catalogued_behavior_count" not in payload:
        payload["catalogued_behavior_count"] = payload["behavior_contract_count"]
    payload["coverage_statement"] = coverage_statement(payload)
    return seal(payload)
