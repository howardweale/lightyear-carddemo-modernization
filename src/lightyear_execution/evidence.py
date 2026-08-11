from __future__ import annotations

import re
from typing import Any

from .contracts import ExecutionContractError, canonical_hash


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def normalize_execution_evidence(receipt: dict[str, Any]) -> dict[str, Any]:
    """Validate an execution receipt and derive its actual assurance class.

    A live container probe proves the runtime boundary only. Hardened factory
    readiness additionally requires a passed, signed work order with scoped
    agent authorization and one or more enforced acceptance gates.
    """

    if receipt.get("content_sha256") != canonical_hash(receipt, {"content_sha256"}):
        raise ExecutionContractError("Execution evidence receipt hash is invalid")
    receipt_type = receipt.get("receipt_type")
    if receipt_type == "lightyear-execution-policy-conformance":
        return _policy_conformance(receipt)
    if receipt_type == "lightyear-live-execution-probe":
        return _live_probe(receipt)
    if receipt_type == "lightyear-autonomous-factory-run":
        return _signed_factory_run(receipt)
    raise ExecutionContractError(f"Unsupported execution evidence type: {receipt_type!r}")


def _policy_conformance(receipt: dict[str, Any]) -> dict[str, Any]:
    policy_sha = _sha(receipt.get("execution_policy_sha256"), "execution policy")
    checks = dict(receipt.get("checks", {}))
    if not checks or any(not isinstance(value, bool) for value in checks.values()):
        raise ExecutionContractError("Policy conformance checks are missing or invalid")
    derived = {
        "policy_construction_passed": receipt.get("status") == "passed" and all(checks.values()),
        "runtime_enforced": False,
        "signed_admission_bound": False,
        "agent_actions_authorized": False,
        "acceptance_gates_passed": False,
        "protected_values_not_persisted": True,
    }
    return _normalized(
        receipt,
        "policy-conformance-simulation",
        "simulated",
        policy_sha,
        derived,
        _merge_gaps(
            receipt.get("gaps", []),
            ["live-container-runtime-not-observed", "signed-factory-work-order-not-observed"],
        ),
        {},
    )


def _live_probe(receipt: dict[str, Any]) -> dict[str, Any]:
    policy_sha = _sha(receipt.get("execution_policy_sha256"), "execution policy")
    execution = receipt.get("execution", {})
    if not isinstance(execution, dict):
        raise ExecutionContractError("Live execution evidence is missing")
    if execution.get("content_sha256") != canonical_hash(execution, {"content_sha256"}):
        raise ExecutionContractError("Live execution evidence hash is invalid")
    runtime_enforced = (
        receipt.get("status") == "passed"
        and receipt.get("assurance") == "enforced"
        and receipt.get("exit_code") == 0
        and receipt.get("timed_out") is False
        and execution.get("enforced") is True
        and execution.get("execution_policy_sha256", policy_sha) == policy_sha
    )
    derived = {
        "policy_construction_passed": True,
        "runtime_enforced": runtime_enforced,
        "signed_admission_bound": False,
        "agent_actions_authorized": False,
        "acceptance_gates_passed": False,
        "protected_values_not_persisted": True,
    }
    gaps = list(receipt.get("gaps", []))
    if not runtime_enforced:
        gaps.append("live-container-runtime-enforcement-failed")
    gaps.append("signed-factory-work-order-not-observed")
    return _normalized(
        receipt,
        "live-container-runtime-probe",
        "enforced" if runtime_enforced else "failed",
        policy_sha,
        derived,
        _merge_gaps(gaps),
        {
            "runtime": receipt.get("runtime"),
            "runtime_execution_sha256": execution.get("content_sha256"),
        },
    )


def _signed_factory_run(receipt: dict[str, Any]) -> dict[str, Any]:
    security = receipt.get("execution_security", {})
    if not isinstance(security, dict):
        raise ExecutionContractError("Factory receipt has no execution security evidence")
    if security.get("content_sha256") != canonical_hash(security, {"content_sha256"}):
        raise ExecutionContractError("Factory execution security evidence hash is invalid")
    policy_sha = _sha(security.get("execution_policy_sha256"), "execution policy")
    work_order_sha = _sha(receipt.get("work_order_sha256"), "work order")
    if security.get("work_order_sha256") != work_order_sha:
        raise ExecutionContractError("Factory execution evidence targets another work order")
    admission_sha = _optional_sha(
        security.get("admission_receipt_sha256"), "admission receipt"
    )
    identity_hashes = _sha_list(
        security.get("identity_receipt_sha256", []), "identity receipt"
    )
    authorization_hashes = _sha_list(
        security.get("authorization_receipt_sha256", []), "authorization receipt"
    )
    gate_hashes = _sha_list(
        security.get("gate_execution_sha256", []), "gate execution"
    )
    required_actions = set(security.get("required_agent_actions", []))
    authorized_actions = set(security.get("authorized_agent_actions", []))
    if any(not isinstance(item, str) or ":" not in item for item in required_actions):
        raise ExecutionContractError("Factory required agent actions are invalid")
    derived = {
        "policy_construction_passed": True,
        "runtime_enforced": (
            security.get("status") == "enforced"
            and security.get("backend", "").startswith("oci-")
            and bool(gate_hashes)
        ),
        "signed_admission_bound": bool(admission_sha),
        "agent_actions_authorized": (
            bool(identity_hashes)
            and bool(authorization_hashes)
            and bool(required_actions)
            and required_actions.issubset(authorized_actions)
        ),
        "acceptance_gates_passed": (
            receipt.get("status") == "passed"
            and receipt.get("verification", {}).get("status") == "passed"
            and bool(gate_hashes)
        ),
        "protected_values_not_persisted": security.get("secrets_persisted") is False,
    }
    gap_by_check = {
        "runtime_enforced": "live-container-runtime-not-observed",
        "signed_admission_bound": "signed-work-order-admission-not-bound",
        "agent_actions_authorized": "required-agent-actions-not-authorized",
        "acceptance_gates_passed": "acceptance-gates-not-passed",
        "protected_values_not_persisted": "protected-value-persistence-not-denied",
    }
    gaps = list(security.get("gaps", []))
    gaps.extend(gap for check, gap in gap_by_check.items() if not derived[check])
    return _normalized(
        receipt,
        "signed-admitted-oci-factory-run",
        "enforced" if derived["runtime_enforced"] else "failed",
        policy_sha,
        derived,
        _merge_gaps(gaps),
        {
            "run_id": receipt.get("run_id"),
            "work_order_sha256": work_order_sha,
            "admission_receipt_sha256": admission_sha,
            "identity_receipt_sha256": identity_hashes,
            "action_attestation_sha256": authorization_hashes,
            "gate_execution_sha256": gate_hashes,
            "required_agent_actions": sorted(required_actions),
            "authorized_agent_actions": sorted(authorized_actions),
        },
    )


def _normalized(
    receipt: dict[str, Any],
    evidence_class: str,
    assurance: str,
    policy_sha: str,
    checks: dict[str, bool],
    gaps: list[str],
    bindings: dict[str, Any],
) -> dict[str, Any]:
    hardened_ready = evidence_class == "signed-admitted-oci-factory-run" and all(checks.values())
    payload = {
        "schema_version": "1.0",
        "evidence_class": evidence_class,
        "source_receipt_type": receipt["receipt_type"],
        "source_receipt_sha256": receipt["content_sha256"],
        "assurance": assurance,
        "hardened_execution_ready": hardened_ready,
        "execution_policy_sha256": policy_sha,
        "checks": checks,
        "gaps": [] if hardened_ready else gaps,
        "bindings": bindings,
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def _sha(value: Any, field: str) -> str:
    result = str(value or "")
    if not _SHA256.fullmatch(result):
        raise ExecutionContractError(f"Invalid {field} SHA-256")
    return result


def _optional_sha(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    return _sha(value, field)


def _sha_list(values: Any, field: str) -> list[str]:
    if not isinstance(values, list):
        raise ExecutionContractError(f"Invalid {field} SHA-256 list")
    return [_sha(item, field) for item in values]


def _merge_gaps(*groups: Any) -> list[str]:
    values: set[str] = set()
    for group in groups:
        if group is None:
            continue
        for value in group:
            text = str(value).strip()
            if text:
                values.add(text)
    return sorted(values)
