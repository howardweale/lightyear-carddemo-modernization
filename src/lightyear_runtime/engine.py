from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .contracts import CaptureBundle, RuntimeContractError, canonical_hash


TRUST_SCORES = {"simulated": 0.45, "local_observed": 0.70, "zos_observed": 0.95}


class RuntimeEvidenceEngine:
    """Validates, chains, reconciles, and projects runtime evidence onto a static graph."""

    def __init__(self, graph: dict[str, Any]) -> None:
        self.graph = graph
        self.node_ids = {item["id"] for item in graph["nodes"]}
        self.edge_ids = {item["id"] for item in graph["edges"]}

    def build(self, bundles: Iterable[CaptureBundle]) -> dict[str, Any]:
        runs = [self._run(bundle) for bundle in bundles]
        if not runs:
            raise RuntimeContractError("At least one runtime capture is required")
        projections = self._projections(runs)
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "snapshot_type": "lightyear-runtime-evidence",
            "graph_content_sha256": self.graph["content_sha256"],
            "runs": sorted(runs, key=lambda item: item["run_id"]),
            "projections": projections,
            "statistics": {
                "run_count": len(runs),
                "event_count": sum(item["event_count"] for item in runs),
                "observed_nodes": len(projections["nodes"]),
                "observed_edges": sum(
                    1 for item in projections["edges"].values()
                    if item["state"] == "runtime_observed"
                ),
                "contradicted_edges": sum(
                    1 for item in projections["edges"].values()
                    if item["state"] == "runtime_contradicted"
                ),
                "evidence_classes": dict(sorted(Counter(
                    event["evidence_class"] for run in runs for event in run["events"]
                ).items())),
            },
        }
        payload["content_sha256"] = canonical_hash(payload)
        return payload

    def _run(self, bundle: CaptureBundle) -> dict[str, Any]:
        self._validate_bundle(bundle)
        previous: str | None = None
        events = []
        for sequence, observation in enumerate(bundle.observations, start=1):
            event: dict[str, Any] = {
                "schema_version": "1.0",
                "run_id": bundle.run_id,
                "sequence": sequence,
                "captured_at": bundle.captured_at,
                "adapter_id": bundle.adapter_id,
                "source_system": bundle.source_system,
                "entity_kind": observation.entity_kind,
                "entity_id": observation.entity_id,
                "assertion": observation.assertion,
                "operation": observation.operation,
                "evidence_class": observation.evidence_class,
                "details": observation.details,
                "previous_sha256": previous,
            }
            event["content_sha256"] = canonical_hash(event)
            previous = event["content_sha256"]
            events.append(event)
        observed = {
            event["entity_id"] for event in events if event["assertion"] == "observed"
        }
        contradicted = {
            event["entity_id"] for event in events if event["assertion"] == "contradicted"
        }
        required = set(bundle.required_nodes) | set(bundle.required_edges)
        development_gaps = sorted(required - observed)
        zos_gaps = sorted(
            entity_id for entity_id in required
            if not any(
                event["entity_id"] == entity_id
                and event["assertion"] == "observed"
                and event["evidence_class"] == "zos_observed"
                for event in events
            )
        )
        development_status = "passed" if not development_gaps and not contradicted else "blocked"
        mainframe_status = "passed" if not zos_gaps and not contradicted else "blocked"
        receipt: dict[str, Any] = {
            "schema_version": "1.0",
            "receipt_type": "lightyear-runtime-evidence-run",
            "run_id": bundle.run_id,
            "adapter_id": bundle.adapter_id,
            "source_system": bundle.source_system,
            "captured_at": bundle.captured_at,
            "event_count": len(events),
            "ledger_head_sha256": previous,
            "required_nodes": list(bundle.required_nodes),
            "required_edges": list(bundle.required_edges),
            "artifacts": list(bundle.artifacts),
            "limitations": list(bundle.limitations),
            "policies": {
                "development_readiness": {
                    "status": development_status,
                    "gaps": development_gaps,
                },
                "mainframe_equivalence": {
                    "status": mainframe_status,
                    "gaps": zos_gaps,
                    "requirement": "Every required entity must be observed by a z/OS adapter.",
                },
            },
            "events": events,
        }
        receipt["content_sha256"] = canonical_hash(receipt)
        return receipt

    def _validate_bundle(self, bundle: CaptureBundle) -> None:
        for entity_id in bundle.required_nodes:
            if entity_id not in self.node_ids:
                raise RuntimeContractError(f"Required runtime node is absent from graph: {entity_id}")
        for entity_id in bundle.required_edges:
            if entity_id not in self.edge_ids:
                raise RuntimeContractError(f"Required runtime edge is absent from graph: {entity_id}")
        for observation in bundle.observations:
            valid = self.node_ids if observation.entity_kind == "node" else self.edge_ids
            if observation.entity_id not in valid:
                raise RuntimeContractError(
                    f"Runtime observation references absent {observation.entity_kind}: "
                    f"{observation.entity_id}"
                )

    @staticmethod
    def _projections(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
            "node": defaultdict(list),
            "edge": defaultdict(list),
        }
        for run in runs:
            for event in run["events"]:
                grouped[event["entity_kind"]][event["entity_id"]].append(event)
        return {
            "nodes": {
                entity_id: _projection(events)
                for entity_id, events in sorted(grouped["node"].items())
            },
            "edges": {
                entity_id: _projection(events)
                for entity_id, events in sorted(grouped["edge"].items())
            },
        }


def _projection(events: list[dict[str, Any]]) -> dict[str, Any]:
    contradicted = any(event["assertion"] == "contradicted" for event in events)
    classes = sorted({event["evidence_class"] for event in events})
    score = 0.0 if contradicted else max(TRUST_SCORES[item] for item in classes)
    return {
        "state": "runtime_contradicted" if contradicted else "runtime_observed",
        "confidence": score,
        "evidence_classes": classes,
        "observation_count": len(events),
        "runs": sorted({event["run_id"] for event in events}),
        "operations": sorted({event["operation"] for event in events}),
        "events": [
            {
                "run_id": event["run_id"],
                "sequence": event["sequence"],
                "assertion": event["assertion"],
                "operation": event["operation"],
                "evidence_class": event["evidence_class"],
                "details": event["details"],
                "content_sha256": event["content_sha256"],
            }
            for event in events
        ],
    }


def write_snapshot(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if path.suffix == ".gz":
        path.write_bytes(gzip.compress(serialized, compresslevel=9, mtime=0))
    else:
        path.write_bytes(serialized)


def load_snapshot(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw).decode("utf-8")) if path.suffix == ".gz" else json.loads(raw)


def validate_snapshot(payload: dict[str, Any], graph: dict[str, Any]) -> list[str]:
    errors = []
    if payload.get("schema_version") != "1.0":
        errors.append("unsupported runtime snapshot schema_version")
    if payload.get("graph_content_sha256") != graph.get("content_sha256"):
        errors.append("runtime snapshot targets a different graph identity")
    if payload.get("content_sha256") != canonical_hash(payload, {"content_sha256"}):
        errors.append("runtime snapshot content hash is invalid")
    previous_run_ids: set[str] = set()
    for run in payload.get("runs", []):
        run_id = run.get("run_id")
        if run_id in previous_run_ids:
            errors.append(f"duplicate runtime run_id: {run_id}")
        previous_run_ids.add(run_id)
        previous = None
        for expected_sequence, event in enumerate(run.get("events", []), start=1):
            if event.get("sequence") != expected_sequence:
                errors.append(f"{run_id} runtime sequence is not contiguous")
            if event.get("previous_sha256") != previous:
                errors.append(f"{run_id} runtime ledger chain is broken")
            if event.get("content_sha256") != canonical_hash(event, {"content_sha256"}):
                errors.append(f"{run_id} runtime event hash is invalid")
            previous = event.get("content_sha256")
        if run.get("ledger_head_sha256") != previous:
            errors.append(f"{run_id} runtime ledger head is stale")
        if run.get("content_sha256") != canonical_hash(run, {"content_sha256"}):
            errors.append(f"{run_id} runtime receipt hash is invalid")
    return errors
