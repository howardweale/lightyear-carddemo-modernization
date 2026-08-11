from __future__ import annotations

from typing import Any

from .backend import OCIContainerBackend
from .contracts import ExecutionContractError, ExecutionPolicy, canonical_hash
from .identity import IdentityAuthority
from .secrets import SecretBroker


class HardenedExecutionContext:
    """Binds one admitted work order to scoped identities and an OCI backend."""

    def __init__(
        self,
        policy: ExecutionPolicy,
        backend: OCIContainerBackend,
        admission_receipt: dict[str, Any],
        identity_key: bytes,
        secret_values: dict[str, str] | None = None,
    ) -> None:
        if admission_receipt.get("status") != "passed":
            raise ExecutionContractError("Hardened execution requires successful admission")
        self.policy = policy
        self.backend = backend
        self.admission_receipt = admission_receipt
        self.authority = IdentityAuthority(policy, identity_key)
        self.secret_broker = SecretBroker(policy, self.authority, secret_values or {})
        self.work_order_sha256: str | None = None
        self.tokens: dict[str, str] = {}
        self.identity_receipts: list[dict[str, Any]] = []
        self.authorization_receipts: list[dict[str, Any]] = []
        self.execution_evidence: list[dict[str, Any]] = []
        self.secret_receipts: list[dict[str, Any]] = []

    def bind(self, work_order_sha256: str, issued_at: str) -> dict[str, Any]:
        if self.admission_receipt.get("work_order_sha256") != work_order_sha256:
            raise ExecutionContractError("Admission receipt targets a different work order")
        if self.work_order_sha256 and self.work_order_sha256 != work_order_sha256:
            raise ExecutionContractError("Execution context is already bound to another work order")
        if not self.work_order_sha256:
            self.work_order_sha256 = work_order_sha256
            for role in sorted(self.policy.role_actions):
                token, receipt = self.authority.issue(
                    role, work_order_sha256, issued_at, f"credential:{role}:{work_order_sha256[:16]}"
                )
                self.tokens[role] = token
                self.identity_receipts.append(receipt)
        payload = {
            "admission_receipt_sha256": self.admission_receipt["content_sha256"],
            "execution_policy_sha256": self.policy.content_sha256,
            "identity_receipts": self.identity_receipts,
        }
        payload["content_sha256"] = canonical_hash(payload)
        return payload

    def lease_secret(self, role: str, name: str, now: str) -> str:
        if self.work_order_sha256 is None or role not in self.tokens:
            raise ExecutionContractError("Execution context has not issued agent identities")
        lease, receipt = self.secret_broker.lease(
            self.tokens[role], name, self.work_order_sha256, now
        )
        self.secret_receipts.append(receipt)
        return lease.consume()

    def authorize(self, role: str, action: str, now: str) -> dict[str, Any]:
        if self.work_order_sha256 is None or role not in self.tokens:
            raise ExecutionContractError("Execution context has not issued agent identities")
        claims = self.authority.verify(
            self.tokens[role], action, self.work_order_sha256, now
        )
        receipt = {
            "role": role,
            "action": action,
            "credential_id": claims["credential_id"],
            "work_order_sha256": self.work_order_sha256,
            "execution_policy_sha256": self.policy.content_sha256,
        }
        receipt["content_sha256"] = canonical_hash(receipt)
        if not any(
            item["role"] == role and item["action"] == action
            for item in self.authorization_receipts
        ):
            self.authorization_receipts.append(receipt)
        return claims

    def record_verification(self, report: dict[str, Any]) -> None:
        self.execution_evidence.extend(
            item["execution"] for item in report.get("gates", []) if "execution" in item
        )

    def summary(self, required_actions: set[tuple[str, str]] | None = None) -> dict[str, Any]:
        required_actions = required_actions or {
            ("planner", "factory:plan"),
            ("verifier", "factory:verify"),
        }
        authorized_actions = {
            (item["role"], item["action"]) for item in self.authorization_receipts
        }
        gates_enforced = bool(self.execution_evidence) and all(
            item.get("enforced") is True for item in self.execution_evidence
        )
        actions_authorized = required_actions.issubset(authorized_actions)
        enforced = gates_enforced and actions_authorized
        gaps = []
        if not gates_enforced:
            gaps.append("container-runtime-enforcement-not-observed")
        if not actions_authorized:
            gaps.append("required-agent-actions-not-authorized")
        payload = {
            "evidence_class": "signed-admitted-oci-factory-run",
            "status": "enforced" if enforced else "simulated",
            "production_ready": enforced,
            "backend": self.backend.backend_id,
            "work_order_sha256": self.work_order_sha256,
            "execution_policy_sha256": self.policy.content_sha256,
            "admission_receipt_sha256": self.admission_receipt["content_sha256"],
            "identity_receipt_sha256": [item["content_sha256"] for item in self.identity_receipts],
            "authorization_receipt_sha256": [
                item["content_sha256"] for item in self.authorization_receipts
            ],
            "required_agent_actions": sorted(
                f"{role}:{action}" for role, action in required_actions
            ),
            "authorized_agent_actions": sorted(
                f"{role}:{action}" for role, action in authorized_actions
            ),
            "gate_execution_sha256": [item["content_sha256"] for item in self.execution_evidence],
            "secret_lease_sha256": [item["content_sha256"] for item in self.secret_receipts],
            "secrets_persisted": False,
            "gaps": gaps,
        }
        payload["content_sha256"] = canonical_hash(payload)
        return payload
