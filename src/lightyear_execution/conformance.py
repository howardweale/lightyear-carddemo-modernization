from __future__ import annotations

from pathlib import Path
from typing import Any

from .backend import OCIContainerBackend
from .contracts import ExecutionPolicy, canonical_hash


def build_conformance_receipt(policy: ExecutionPolicy) -> dict[str, Any]:
    backend = OCIContainerBackend(policy, policy.runtimes[0], execute=False)
    _, plan = backend.build_invocation(
        ("python3", "-m", "lightyear_factory.private_benchmark"),
        Path("."),
        {
            "PYTHONPATH": "ignored-host-value",
            "LIGHTYEAR_FACTORY_WORKSPACE": "ignored-host-value",
            "LIGHTYEAR_NETWORK_POLICY": "deny",
            "OPENAI_API_KEY": "must-not-cross-gate-boundary",
        },
    )
    plan.pop("content_sha256", None)
    checks = {
        "digest_pinned_image": "@sha256:" in plan["image"],
        "network_disabled": plan["network_mode"] == "none",
        "root_filesystem_read_only": plan["read_only_root"] is True,
        "workspace_read_only": plan["workspace_read_only"] is True,
        "non_root_identity": not plan["run_as_user"].startswith("0:"),
        "capabilities_dropped": plan["cap_drop_all"] is True,
        "privilege_escalation_denied": plan["no_new_privileges"] is True,
        "resource_limits_present": all(plan[item] for item in ("pids_limit", "memory_mb", "cpus", "tmpfs_mb")),
        "protected_value_not_forwarded": "OPENAI_API_KEY" not in plan["environment_names"],
    }
    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "receipt_type": "lightyear-execution-policy-conformance",
        "status": "passed" if all(checks.values()) else "failed",
        "assurance": "simulated",
        "production_ready": False,
        "execution_policy_id": policy.policy_id,
        "execution_policy_sha256": policy.content_sha256,
        "backend_plan": plan,
        "checks": checks,
        "gaps": [
            "container-runtime-enforcement-not-observed",
            "live-signed-work-order-admission-not-observed",
        ],
        "limitations": [
            "This receipt proves deterministic policy and invocation construction, not OS enforcement.",
            "Run a live Docker or Podman probe before claiming hardened execution readiness.",
        ],
    }
    receipt["content_sha256"] = canonical_hash(receipt)
    return receipt
