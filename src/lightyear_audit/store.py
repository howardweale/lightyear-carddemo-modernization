from __future__ import annotations

from typing import Any

from .dossier import build_dossier


class AuditStore:
    """Read-only, audience-filtered projection used by the Evidence Control Tower."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.decision_by_id = {item["id"]: item for item in snapshot.get("decisions", [])}

    def summary(self) -> dict[str, Any]:
        promotion = [
            item for item in self.snapshot["decisions"] if item["policy_id"] == "release.promotion"
        ]
        execution = [
            item for item in self.snapshot["decisions"]
            if item["policy_id"] == "execution.hardened_readiness"
        ]
        return {
            "content_sha256": self.snapshot["content_sha256"],
            "graph_content_sha256": self.snapshot["graph_content_sha256"],
            "checkpoint": self.snapshot["checkpoint"],
            "statistics": self.snapshot["statistics"],
            "promotion_decisions": promotion,
            "execution_decisions": execution,
            "trust_posture": {
                "promotion_status": promotion[-1]["status"] if promotion else "not_evaluated",
                "unresolved_gaps": promotion[-1]["gaps"] if promotion else [],
                "signed_checkpoint": bool(self.snapshot["checkpoint"].get("signature")),
                "execution_status": execution[-1]["status"] if execution else "not_evaluated",
            },
        }

    def events(self, audience: str = "implementer", limit: int = 100) -> dict[str, Any]:
        if audience not in {"implementer", "verifier", "auditor"}:
            raise ValueError("audience must be implementer, verifier, or auditor")
        visible = [
            item for item in self.snapshot["events"]
            if item["visibility"] == "shared" or audience in {"verifier", "auditor"}
        ]
        return {"events": visible[-max(1, min(limit, 1000)):], "total": len(visible)}

    def decision(self, decision_id: str) -> dict[str, Any]:
        return self.decision_by_id[decision_id]

    def dossier(self, release_id: str) -> dict[str, Any]:
        return build_dossier(self.snapshot, release_id)
