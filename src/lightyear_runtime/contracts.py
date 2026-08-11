from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


RUNTIME_SCHEMA_VERSION = "1.0"
EVIDENCE_CLASSES = {"simulated", "local_observed", "zos_observed"}
ASSERTIONS = {"observed", "contradicted"}
ENTITY_KINDS = {"node", "edge"}


class RuntimeContractError(ValueError):
    """Raised when runtime evidence crosses a contract boundary incorrectly."""


def canonical_hash(payload: dict[str, Any], excluded: set[str] | None = None) -> str:
    excluded = excluded or set()
    normalized = {key: value for key, value in payload.items() if key not in excluded}
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class RuntimeObservation:
    entity_kind: str
    entity_id: str
    assertion: str
    operation: str
    evidence_class: str
    details: dict[str, Any]

    @classmethod
    def from_dict(
        cls, payload: dict[str, Any], default_evidence_class: str = "simulated"
    ) -> "RuntimeObservation":
        entity_kind = str(payload.get("entity_kind", "")).strip()
        entity_id = str(payload.get("entity_id", "")).strip()
        assertion = str(payload.get("assertion", "observed")).strip()
        operation = str(payload.get("operation", "observed")).strip()
        evidence_class = str(
            payload.get("evidence_class", default_evidence_class)
        ).strip()
        details = payload.get("details", {})
        if entity_kind not in ENTITY_KINDS:
            raise RuntimeContractError(f"Invalid runtime entity kind: {entity_kind}")
        if not entity_id or any(character.isspace() for character in entity_id):
            raise RuntimeContractError("Runtime entity_id must be a non-empty graph identifier")
        if assertion not in ASSERTIONS:
            raise RuntimeContractError(f"Invalid runtime assertion: {assertion}")
        if evidence_class not in EVIDENCE_CLASSES:
            raise RuntimeContractError(f"Invalid runtime evidence class: {evidence_class}")
        if not operation or len(operation) > 120:
            raise RuntimeContractError("Runtime operation must contain 1 to 120 characters")
        if not isinstance(details, dict):
            raise RuntimeContractError("Runtime observation details must be an object")
        encoded = json.dumps(details, sort_keys=True)
        if len(encoded.encode("utf-8")) > 32768:
            raise RuntimeContractError("Runtime observation details exceed 32 KiB")
        return cls(entity_kind, entity_id, assertion, operation, evidence_class, details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion": self.assertion,
            "details": self.details,
            "entity_id": self.entity_id,
            "entity_kind": self.entity_kind,
            "evidence_class": self.evidence_class,
            "operation": self.operation,
        }


@dataclass(frozen=True)
class CaptureBundle:
    run_id: str
    adapter_id: str
    source_system: str
    captured_at: str
    observations: tuple[RuntimeObservation, ...]
    required_nodes: tuple[str, ...]
    required_edges: tuple[str, ...]
    artifacts: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CaptureBundle":
        run_id = str(payload.get("run_id", "")).strip()
        adapter_id = str(payload.get("adapter_id", "")).strip()
        source_system = str(payload.get("source_system", "")).strip()
        captured_at = str(payload.get("captured_at", "")).strip()
        evidence_class = str(payload.get("evidence_class", "simulated")).strip()
        if not run_id or not adapter_id or not source_system or not captured_at:
            raise RuntimeContractError(
                "Capture bundle requires run_id, adapter_id, source_system, and captured_at"
            )
        observations_payload = payload.get("observations")
        if not isinstance(observations_payload, list) or not observations_payload:
            raise RuntimeContractError("Capture bundle requires at least one observation")
        observations = tuple(
            RuntimeObservation.from_dict(item, evidence_class) for item in observations_payload
        )
        required_nodes = _identifiers(payload.get("required_nodes", []), "required_nodes")
        required_edges = _identifiers(payload.get("required_edges", []), "required_edges")
        artifacts = payload.get("artifacts", [])
        limitations = payload.get("limitations", [])
        if not isinstance(artifacts, list) or not all(isinstance(item, dict) for item in artifacts):
            raise RuntimeContractError("Capture artifacts must be an array of objects")
        if not isinstance(limitations, list) or not all(
            isinstance(item, str) and item.strip() for item in limitations
        ):
            raise RuntimeContractError("Capture limitations must be an array of strings")
        return cls(
            run_id,
            adapter_id,
            source_system,
            captured_at,
            observations,
            required_nodes,
            required_edges,
            tuple(artifacts),
            tuple(limitations),
        )


def _identifiers(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item and not any(character.isspace() for character in item)
        for item in value
    ):
        raise RuntimeContractError(f"{field} must be an array of graph identifiers")
    if len(set(value)) != len(value):
        raise RuntimeContractError(f"{field} must not contain duplicates")
    return tuple(value)
