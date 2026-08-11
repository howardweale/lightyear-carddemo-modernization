from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import AuditContractError, ExceptionGrant, canonical_hash, safe_identifier


class AuditPolicyEngine:
    """Deterministic policy evaluator; agents may explain results but cannot decide them."""

    def __init__(self, payload: dict[str, Any]) -> None:
        if payload.get("schema_version") != "1.0":
            raise AuditContractError("Unsupported audit policy schema")
        policies = payload.get("policies")
        if not isinstance(policies, list) or not policies:
            raise AuditContractError("Audit policy set requires policies")
        self.payload = payload
        self.by_id = {item["id"]: item for item in policies}
        if len(self.by_id) != len(policies):
            raise AuditContractError("Audit policy ids must be unique")

    @classmethod
    def load(cls, path: Path) -> "AuditPolicyEngine":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @property
    def content_sha256(self) -> str:
        return canonical_hash(self.payload)

    def runtime_decision(
        self,
        run: dict[str, Any],
        policy_name: str,
        evaluated_at: str,
    ) -> dict[str, Any]:
        source = run["policies"][policy_name]
        policy_id = f"runtime.{policy_name}"
        policy = self.by_id[policy_id]
        status = source["status"]
        gaps = list(source.get("gaps", []))
        return self._decision(
            decision_id=f"decision:{run['run_id']}:{policy_name}",
            policy=policy,
            subject_id=f"runtime-run:{run['run_id']}",
            status=status,
            evaluated_at=evaluated_at,
            gaps=gaps,
            rationale=(
                f"{policy['name']} passed with all required evidence."
                if status == "passed"
                else f"{policy['name']} blocked because {len(gaps)} required evidence item(s) are absent."
            ),
            inputs={
                "adapter_id": run["adapter_id"],
                "evidence_classes": sorted({event["evidence_class"] for event in run["events"]}),
                "run_receipt_sha256": run["content_sha256"],
            },
        )

    def promotion_decision(
        self,
        release_id: str,
        runtime_decisions: list[dict[str, Any]],
        graph_sha256: str,
        evidence_sha256: str,
        evaluated_at: str,
        exception_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        policy = self.by_id["release.promotion"]
        development = [
            item for item in runtime_decisions
            if item["policy_id"] == "runtime.development_readiness"
        ]
        mainframe = [
            item for item in runtime_decisions
            if item["policy_id"] == "runtime.mainframe_equivalence"
        ]
        gaps = []
        if not development or any(item["status"] != "passed" for item in development):
            gaps.append("development-readiness")
        if not mainframe or not any(item["status"] == "passed" for item in mainframe):
            gaps.append("mainframe-equivalence")
        status = "passed" if not gaps else "blocked"
        exception = None
        if exception_payload is not None:
            exception = ExceptionGrant.from_dict(exception_payload, now=evaluated_at)
            if exception.policy_id != policy["id"] or exception.subject_id != release_id:
                raise AuditContractError("Exception does not target this policy decision")
            if not policy.get("override_allowed", False):
                raise AuditContractError(f"Policy {policy['id']} cannot be overridden")
            status = "overridden"
        return self._decision(
            decision_id=f"decision:{release_id}:promotion",
            policy=policy,
            subject_id=release_id,
            status=status,
            evaluated_at=evaluated_at,
            gaps=gaps,
            rationale=(
                "Release satisfies graph, source-evidence, development, and mainframe gates."
                if status == "passed"
                else "Release is blocked until independently observed z/OS equivalence evidence exists."
                if status == "blocked"
                else f"Release policy was overridden by approved exception {exception.exception_id}."
            ),
            inputs={
                "graph_content_sha256": graph_sha256,
                "source_evidence_content_sha256": evidence_sha256,
                "runtime_decision_ids": [item["id"] for item in runtime_decisions],
            },
            exception=exception.to_dict() if exception else None,
        )

    @staticmethod
    def _decision(
        decision_id: str,
        policy: dict[str, Any],
        subject_id: str,
        status: str,
        evaluated_at: str,
        gaps: list[str],
        rationale: str,
        inputs: dict[str, Any],
        exception: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in {"passed", "blocked", "overridden"}:
            raise AuditContractError(f"Invalid decision status: {status}")
        decision = {
            "id": safe_identifier(decision_id, "decision id"),
            "policy_id": safe_identifier(policy["id"], "policy id"),
            "policy_version": str(policy["version"]),
            "subject_id": safe_identifier(subject_id, "decision subject id"),
            "status": status,
            "evaluated_at": evaluated_at,
            "rationale": rationale,
            "gaps": sorted(gaps),
            "inputs": inputs,
            "override_allowed": bool(policy.get("override_allowed", False)),
            "exception": exception,
        }
        decision["content_sha256"] = canonical_hash(decision)
        return decision
