"""Read the published MS54–67 execution record without cloud access or admission.

The owner exported these original bytes after HMAC verification. Public readers
can check hashes and bindings; this module never claims to reverify a secret HMAC
key and never turns a deterministic readiness fixture into execution evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = "ms67-final-635689566db6425aadf6fb1fc6cf3de7"
BUNDLE = Path("docs/receipts") / RUN_ID
EXPORT_SHA256 = "6f622d50ac114964c705ab9021a7edd26ecb1ef2ae3bb05af98851557da46a7b"
RECEIPT_SHA256 = "9ab88762bbe1b3ab37f966fa17eb20164e6c8a068376a889f2548e1e449f29a0"
SCOPES = {
    54: "Source build and bounded Oracle runtime",
    55: "Customer PostgreSQL database mapping",
    56: "Customer application dark factory run",
    57: "Bounded Customer qualification",
    58: "Transaction wave plan admission",
    59: "PostgreSQL transaction core",
    60: "Native Account and Transfer wave",
    61: "Normalized Customer, Account and Transfer equivalence",
    62: "OAuth application boundary",
    63: "Checks durable messaging",
    64: "Eight-service target and edge controls",
    65: "Nonproduction deployment, cutover and rollback rehearsal",
    66: "Bounded eight-service Oracle/PostgreSQL equivalence",
    67: "Real nonproduction platform qualification",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"publication evidence: {message}")


def _digest(value: dict[str, Any]) -> str:
    body = {k: v for k, v in value.items() if k not in ("signature", "content_sha256")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def load_publication(root: Path = ROOT) -> dict[str, Any]:
    """Validate original export bytes and closure, then derive display facts.

    The checked-in manifest digest anchors this particular authorized upload.
    This is an archival result for its bound run, not a current health check.
    """
    base = root / BUNDLE
    raw = (base / "publication-export.json").read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == EXPORT_SHA256, "export manifest changed")
    manifest = json.loads(raw)
    documents, files = {}, {}
    for entry in manifest["files"]:
        role, path = entry["role"], Path(entry["path"])
        _require(path.parts == ("receipts", role + ".json"), "unsafe receipt path")
        data = (base / path).read_bytes()
        _require(len(data) == entry["bytes"] and hashlib.sha256(data).hexdigest() == entry["file_sha256"], f"{role} bytes changed")
        value = json.loads(data)
        _require(_digest(value) == value["content_sha256"] == entry["content_sha256"], f"{role} content changed")
        documents[role] = value
        files[role] = {**entry, "path": (BUNDLE / path).as_posix()}
    _require(len(documents) == 31, "incomplete bundle")
    index = documents["ms67-evidence-index"]
    receipt = documents["ms67-platform-receipt"]

    def bind(role: str, ref: dict[str, Any]) -> None:
        _require(documents[role]["content_sha256"] == ref["sha256"], f"{role} binding mismatch")
        _require(files[role]["source_uri"] == ref["uri"], f"{role} source mismatch")

    bind("ms67-platform-receipt", index["receipt"])
    bind("platform-observation", index["observation"])
    for group, prefix in (("retained", "retained-"), ("phases", "phase-")):
        for name, ref in index[group].items():
            bind(prefix + name, ref)
    _require(receipt["content_sha256"] == RECEIPT_SHA256, "unexpected final receipt")
    _require(receipt["run_id"] == index["run_id"] == RUN_ID and index["ms67_complete"] is True, "closeout incomplete")
    _require(receipt["status"] == "passed-real-non-production-platform-qualification" and receipt["non_production_platform_qualified"] is True, "platform not qualified")
    for flag in ("production_ready", "production_deployed", "customer_approval_complete", "customer_idp_qualified", "representative_data_volume_qualified", "migration_complete"):
        _require(receipt[flag] is False, f"unsupported {flag}")

    observation = documents["platform-observation"]
    for field, role in (("source_ms65_receipt_sha256", "retained-ms65"), ("source_ms66_receipt_sha256", "retained-ms66-receipt"), ("profile_sha256", "retained-platform-profile"), ("observation_sha256", "platform-observation")):
        _require(receipt[field] == documents[role]["content_sha256"], field)
        if field != "observation_sha256":
            _require(observation["bindings"][field] == receipt[field], f"observation {field}")
    for field in ("deployment_bundle_sha256", "cluster_identity_sha256"):
        _require(observation["bindings"][field] == receipt[field] == documents["retained-ms65"][field], field)
    hashes = {v["content_sha256"] for v in documents.values()}
    scenarios = observation["scenarios"]
    _require(len(scenarios) == receipt["scenario_count"] == 28 and len({s["id"] for s in scenarios}) == 28, "scenario coverage")
    _require(all(s["status"] == "passed" and s["evidence_sha256"] in hashes for s in scenarios), "scenario proof missing")
    ms65, ms66 = documents["retained-ms65"], documents["retained-ms66-receipt"]
    _require(ms65["rehearsal"]["status"] == "passed" and all(ms65[f] is True for f in ("production_like_rehearsal_complete", "cutover_rehearsal_complete", "rollback_rehearsal_complete")), "MS65 not passed")
    _require(ms66["status"] == "passed-bounded-whole-application-equivalence" and ms66["whole_application_equivalent"] is True, "MS66 not passed")
    for value in (ms65, ms66):
        _require(value["source_ms64_receipt_sha256"] == documents["retained-ms64-receipt"]["content_sha256"], "MS64 binding")
    lock_sha = documents["retained-image-lock"]["content_sha256"]
    _require(ms65["image_lock_sha256"] == ms66["postgresql_image_lock_sha256"] == lock_sha, "image lock binding")
    load = documents["retained-load"]
    for field, role in (("image_lock_sha256", "retained-image-lock"), ("ms64_receipt_sha256", "retained-ms64-receipt"), ("ms66_receipt_sha256", "retained-ms66-receipt"), ("platform_profile_sha256", "retained-platform-profile")):
        _require(load["bindings"][field] == documents[role]["content_sha256"], f"load {field}")
    _require(load["bindings"]["journeys_sha256"] == ms66["postgresql_journey_sha256"], "load journey binding")
    _require(load["status"] == "passed-bounded-sustained-business-load", "load not passed")
    summary, sql = load["summary"], documents["retained-sql"]
    _require(sql["status"] == "passed-isolated-database-recovery", "SQL not accepted")
    _require(sql["reassessment"]["measurements_changed"] is False and sql["reassessment"]["new_recovery_run"] is False, "SQL reassessment scope")
    policy = sql["acceptance_policy"]
    _require(sql["pitr"]["database_rto_seconds"] <= policy["maximum_pitr_rto_seconds"] == 630, "PITR acceptance")
    _require(sql["backup_restore"]["state_matches"] and sql["pitr"]["state_matches"], "SQL state mismatch")
    for key in ("requests", "errors", "p95_ms"):
        _require(summary[key] == observation["load"][key], f"load {key} differs")

    milestones: dict[int, dict[str, Any]] = {}
    for row in documents["ms54-ms64-chain"]["receipts"]:
        role = "prerequisite-" + row["file"].removesuffix(".json")
        value = documents[role]
        _require(value["content_sha256"] == row["content_sha256"] and value["status"] == row["status"] and value["status"].startswith("passed"), f"prerequisite {role}")
        number = int(row["release"].split(".")[1])
        milestones.setdefault(number, {"number": number, "scope": SCOPES[number], "status": "Passed", "receipts": []})["receipts"].append(files[role])
    _require(documents["prerequisite-ms64-edge-ai.receipt"]["content_sha256"] == documents["retained-ms64-receipt"]["content_sha256"], "prerequisite MS64 mismatch")
    _require(ms66["source_ms61_receipt_sha256"] == documents["prerequisite-ms61-equivalence.receipt"]["content_sha256"], "prerequisite MS61 mismatch")
    for number, role in ((65, "retained-ms65"), (66, "retained-ms66-receipt"), (67, "ms67-platform-receipt")):
        milestones[number] = {"number": number, "scope": SCOPES[number], "status": "Passed", "receipts": [files[role]]}
    milestones[58]["status"] = "Plan admitted"
    _require(set(milestones) == set(range(54, 68)), "milestone coverage")
    return {
        "schema_version": "1.0", "run_id": RUN_ID, "ms67_complete": True,
        "production_ready": False, "production_deployed": False,
        "scope": "Bounded CloudBank synthetic nonproduction qualification",
        "published_on": "2026-09-11", "receipt_path": files["ms67-platform-receipt"]["path"],
        "receipt_uri": manifest["receipt_uri"], "receipt_content_sha256": RECEIPT_SHA256,
        "verification": {"public_checks": "original-file-hashes, content-hashes and evidence bindings", "hmac_verification": "performed by operator exporter before upload; not independently repeated by public publisher", "export_manifest_sha256": EXPORT_SHA256, "export_manifest_path": (BUNDLE / "publication-export.json").as_posix()},
        "summary": {"services": len(receipt["services"]), "ready_replicas": sum(r["ready_replicas"] for r in observation["service_rollouts"]), "platform_scenarios": len(scenarios), "business_journeys": ms66["scenario_count"], "load_duration_seconds": summary["configured_duration_seconds"], "load_vus": summary["configured_vus"], "load_requests": summary["requests"], "load_errors": summary["errors"], "load_p95_ms": summary["p95_ms"], "chat_p95_ms": summary["operations"]["chat"]["p95_ms"], "pitr_rto_seconds": sql["pitr"]["database_rto_seconds"], "pitr_limit_seconds": policy["maximum_pitr_rto_seconds"], "backup_restore_rto_seconds": sql["backup_restore"]["database_rto_seconds"], "rpo_seconds": sql["pitr"]["recovery_point_age_seconds"], "sql_policy_id": policy["policy_id"], "measurements_changed": False},
        "milestones": [milestones[n] for n in sorted(milestones)],
        "files": [files[k] for k in sorted(files)],
        "scenarios": scenarios,
    }


def workload_publication(workload_id: str, publication: dict[str, Any]) -> dict[str, Any]:
    """Project only the five CloudBank reference workloads, never customer gates."""
    numbers = {"customer-account-management": 61, "money-transfer": 62, "check-deposit-clearance": 63, "identity-service-authorization": 62, "credit-score-service": 64}
    prefix = "cloudbank-reference:workload:"
    if not workload_id.startswith(prefix) or workload_id[len(prefix):] not in numbers:
        return {}
    rows = {r["number"]: r for r in publication["milestones"]}
    result: dict[str, Any] = {"publication_run_id": publication["run_id"], "publication_scope": publication["scope"], "production_ready": False}
    for number, status_key, artifact_key in ((numbers[workload_id[len(prefix):]], "target_status", "factory_artifact"), (65, "production_readiness_status", "production_readiness_artifact"), (66, "whole_application_status", "whole_application_artifact"), (67, "platform_qualification_status", "platform_qualification_artifact")):
        result[status_key] = f"MS #{number} passed · {rows[number]['scope']}"
        result[artifact_key] = rows[number]["receipts"][0]["path"]
    return result
