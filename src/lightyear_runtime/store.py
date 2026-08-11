from __future__ import annotations

from typing import Any


class RuntimeEvidenceStore:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.run_by_id = {item["run_id"]: item for item in snapshot.get("runs", [])}

    def summary(self) -> dict[str, Any]:
        return {
            "content_sha256": self.snapshot["content_sha256"],
            "graph_content_sha256": self.snapshot["graph_content_sha256"],
            "statistics": self.snapshot["statistics"],
            "runs": [self._run_summary(item) for item in reversed(self.snapshot["runs"])],
        }

    def run(self, run_id: str) -> dict[str, Any]:
        return self.run_by_id[run_id]

    def projection(self, entity_kind: str, entity_id: str) -> dict[str, Any]:
        plural = "nodes" if entity_kind == "node" else "edges"
        return self.snapshot.get("projections", {}).get(plural, {}).get(
            entity_id,
            {
                "state": "static_only",
                "confidence": 0.35,
                "evidence_classes": [],
                "observation_count": 0,
                "runs": [],
                "operations": [],
                "events": [],
            },
        )

    @staticmethod
    def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": run["run_id"],
            "adapter_id": run["adapter_id"],
            "source_system": run["source_system"],
            "captured_at": run["captured_at"],
            "event_count": run["event_count"],
            "development_status": run["policies"]["development_readiness"]["status"],
            "mainframe_status": run["policies"]["mainframe_equivalence"]["status"],
            "content_sha256": run["content_sha256"],
        }
