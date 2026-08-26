from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .contracts import ExtensionContractError, finalize_envelope, validate_envelope


class EvidenceAdapter(Protocol):
    descriptor: "AdapterDescriptor"

    def capture(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AdapterDescriptor:
    adapter_id: str
    version: str
    capabilities: tuple[str, ...]
    evidence_classes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.adapter_id,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "evidence_classes": list(self.evidence_classes),
        }


class AdapterRegistry:
    def __init__(self) -> None:
        self._descriptors: dict[str, AdapterDescriptor] = {}

    def register(self, descriptor: AdapterDescriptor) -> None:
        if descriptor.adapter_id in self._descriptors:
            raise ExtensionContractError(f"Duplicate adapter id: {descriptor.adapter_id}")
        self._descriptors[descriptor.adapter_id] = descriptor

    def catalog(self) -> list[dict[str, Any]]:
        return [self._descriptors[key].to_dict() for key in sorted(self._descriptors)]


class FixtureAdapter:
    descriptor = AdapterDescriptor(
        "lightyear.fixture",
        "1.0",
        ("bounded-fixture-capture",),
        ("simulated", "inferred"),
    )

    def __init__(self, path: Path, graph: Mapping[str, Any]) -> None:
        self.path = path
        self.graph = graph

    def capture(self) -> dict[str, Any]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["graph_binding"] = {
            "graph_id": self.graph["graph_id"],
            "content_sha256": self.graph["content_sha256"],
        }
        envelope = finalize_envelope(payload)
        errors = validate_envelope(envelope, graph=self.graph)
        if errors:
            raise ExtensionContractError("; ".join(errors))
        if envelope["evidence_class"] not in self.descriptor.evidence_classes:
            raise ExtensionContractError("Fixture adapters cannot claim live or recorded evidence")
        return envelope


class RecordedReplayAdapter:
    descriptor = AdapterDescriptor(
        "lightyear.recorded-replay",
        "1.0",
        ("content-addressed-replay", "classification-downgrade"),
        ("recorded", "simulated", "inferred"),
    )

    def __init__(
        self,
        capture: Mapping[str, Any],
        graph: Mapping[str, Any],
        trusted_keys: Mapping[str, bytes] | None = None,
    ) -> None:
        self.capture_payload = copy.deepcopy(dict(capture))
        self.graph = graph
        self.trusted_keys = trusted_keys

    def capture(self) -> dict[str, Any]:
        errors = validate_envelope(
            self.capture_payload,
            graph=self.graph,
            trusted_keys=self.trusted_keys,
        )
        if errors:
            raise ExtensionContractError("; ".join(errors))
        source_class = self.capture_payload["evidence_class"]
        replay_class = "recorded" if source_class in {"live", "recorded"} else source_class
        original_sha = self.capture_payload["content_sha256"]
        limitations = list(self.capture_payload["limitations"])
        limitation = "Replay preserves a captured observation; it is not a live system observation."
        if limitation not in limitations:
            limitations.append(limitation)
        payload = {
            "schema_version": "1.0",
            "envelope_type": "lightyear-adapter-evidence",
            "envelope_id": f"replay:{original_sha[:24]}",
            "adapter": {
                "id": self.descriptor.adapter_id,
                "version": self.descriptor.version,
            },
            "source": {
                "system": self.capture_payload["source"]["system"],
                "kind": "recorded-capture",
                "attestation": "content-addressed-replay",
            },
            "collected_at": self.capture_payload["collected_at"],
            "evidence_class": replay_class,
            "graph_binding": copy.deepcopy(self.capture_payload["graph_binding"]),
            "scope": {
                **copy.deepcopy(self.capture_payload["scope"]),
                "read_only": True,
                "mode": "replay",
            },
            "claims": copy.deepcopy(self.capture_payload["claims"]),
            "artifacts": copy.deepcopy(self.capture_payload["artifacts"]),
            "limitations": limitations,
            "recorded_from_sha256": original_sha,
        }
        envelope = finalize_envelope(payload)
        replay_errors = validate_envelope(envelope, graph=self.graph)
        if replay_errors:
            raise ExtensionContractError("; ".join(replay_errors))
        return envelope


def default_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(FixtureAdapter.descriptor)
    registry.register(RecordedReplayAdapter.descriptor)
    registry.register(AdapterDescriptor(
        "lightyear.zosmf-jobs",
        "1.1",
        (
            "jes-job-status", "bounded-spool-metadata", "graph-addressed-observations",
            "credential-safe-live-capture",
        ),
        ("live", "simulated"),
    ))
    registry.register(AdapterDescriptor(
        "lightyear.db2-zos-catalog",
        "1.0",
        (
            "tables", "columns", "constraints", "indexes", "packages",
            "credential-safe-live-capture",
        ),
        ("live", "recorded", "simulated"),
    ))
    registry.register(AdapterDescriptor(
        "lightyear.cics-cmci",
        "1.0",
        (
            "installed-resources", "definitional-resources", "region-identity",
            "credential-safe-live-capture",
        ),
        ("live", "recorded", "simulated"),
    ))
    return registry
