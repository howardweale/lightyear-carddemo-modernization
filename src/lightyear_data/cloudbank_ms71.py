"""MS71 acceptance composes two real MS66 comparisons without changing their comparator."""
from __future__ import annotations

import re
from pathlib import Path

from .cloudbank_journeys import require, hashed
from .cloudbank_managed_target import PROVIDERS, validate_profile, datasource
from .cloudbank_ms66_dual_lane import validate_shared_journey, build_lane_observation
from .cloudbank_whole_application_equivalence import SERVICES, validate_execution_receipt
from .contracts import sign, verify_signature, content_hash

COMPARISON_TYPE = "lightyear-cloudbank-ms71-managed-comparison"
RECEIPT_TYPE = "lightyear-cloudbank-ms71-two-target-acceptance"
COMPARISON_FILE = "ms71-managed-comparison.json"
RECEIPT_FILE = "ms71-alloydb-second-target.receipt.json"
COMMON_FIELDS = (
    "source_ms61_receipt_sha256", "source_ms64_receipt_sha256",
    "oracle_source_image_lock_sha256", "postgresql_image_lock_sha256",
    "oracle_hardening_contract_sha256", "oracle_hardening_patch_sha256",
    "oracle_image_id_sha256", "postgresql_image_id_sha256", "normalized_observation_sha256",
)


def signed(value: dict, key: str) -> None:
    require(isinstance(value, dict) and isinstance(value.get("signature"), dict)
            and bool(key) and value.get("content_sha256") == content_hash(value)
            and verify_signature(value, key), "ms71-signature-invalid")


def validate_comparison(value: dict, key: str, root: Path) -> None:
    signed(value, key)
    require(set(value) == {
        "schema_version", "receipt_type", "campaign_id", "controller_commit", "profile",
        "before", "after", "probe_sql", "comparison", "oracle_journey", "target_journey",
        "source_images", "target_images", "recovery", "production_ready", "ms71_complete",
        "content_sha256", "signature",
    }, "ms71-comparison-fields-invalid")
    require(value["schema_version"] == "1.0" and value["receipt_type"] == COMPARISON_TYPE
            and re.fullmatch(r"ms71-[a-z0-9-]{1,35}", str(value["campaign_id"]))
            and re.fullmatch(r"[0-9a-f]{40}", str(value["controller_commit"])), "ms71-comparison-identity-invalid")
    validate_profile(value["profile"])
    receipt = value["comparison"]
    require(not validate_execution_receipt(receipt, key, root), "ms71-underlying-comparison-invalid")
    require(value["production_ready"] is False and value["ms71_complete"] is False,
            "ms71-comparison-claims-invalid")
    for name in ("source_images", "target_images"):
        images = value[name]
        require(isinstance(images, dict) and set(images) == set(SERVICES) and all(
            isinstance(image, str) and re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", image)
            for image in images.values()), "ms71-image-set-invalid")
    before, after, profile = value["before"], value["after"], value["profile"]
    require(isinstance(before, dict) and before == after and
            before.get("content_sha256") == content_hash(before), "ms71-target-identity-drift")
    require(before.get("profile_sha256") == profile["content_sha256"]
            and before.get("images_sha256") == hashed(value["target_images"]), "ms71-target-binding-invalid")
    database = before.get("database", {})
    require(database.get("provider") == profile["provider"] and database.get("resource") == profile["resource"]
            and database.get("database_version") == profile["database_version"]
            and isinstance(database.get("created_at"), str) and bool(database["created_at"])
            and database.get("content_sha256") == content_hash(database), "ms71-database-binding-invalid")
    datasource(f"jdbc:postgresql://{database.get('address')}:5432/probe")
    environment = before.get("environment", {})
    require(all(environment.get(f) == profile[f] for f in ("project", "region", "cluster", "namespace"))
            and re.fullmatch(r"[0-9a-f]{64}", str(environment.get("namespace_uid_sha256", ""))),
            "ms71-namespace-binding-invalid")
    connections = before.get("services", {})
    require(set(connections) == set(SERVICES), "ms71-service-connections-incomplete")
    for service in SERVICES:
        connection = connections[service].get("connection")
        auxiliary = connections[service].get("auxiliary_connections")
        require(isinstance(auxiliary, dict) and all(v == connection for v in auxiliary.values()),
                "ms71-auxiliary-database-mismatch")
        db = profile["databases"][service]
        require((db is None and connection is None) or (
            isinstance(connection, dict) and connection.get("address") == database.get("address")
            and connection.get("port") == 5432 and connection.get("database") == db
            and (connection.get("tls") is True or not profile["require_tls"])),
            "ms71-database-connection-invalid")
    require(before.get("probe_connection") == connections["checks"]["connection"], "ms71-probe-binding-invalid")
    probe = value["probe_sql"]
    require(isinstance(probe, dict) and set(probe) == {"database", "server_version_num", "tls"}
            and probe["database"] == profile["databases"]["checks"]
            and type(probe["server_version_num"]) is int
            and probe["server_version_num"] // 10000 == int(profile["database_version"].split("_")[1])
            and (probe["tls"] is True or not profile["require_tls"]), "ms71-probe-sql-invalid")
    for lane, name, images, hash_name in (
        ("oracle", "oracle_journey", "source_images", "oracle_source_image_lock_sha256"),
        ("postgresql", "target_journey", "target_images", "postgresql_image_lock_sha256"),
    ):
        journey = value[name]
        require(not validate_shared_journey(journey, key, lane,
            image_lock_sha256=receipt[hash_name], expected_images=value[images]), "ms71-journey-invalid")
        require(journey["content_sha256"] == receipt[lane + "_journey_sha256"]
                and journey["run_id"] == receipt["comparison_run_id"] + "-" + lane,
                "ms71-journey-receipt-mismatch")
        for row in journey["scenarios"]:
            require(row["evidence_sha256"] == hashed(row.get("evidence")), "ms71-scenario-evidence-hash-invalid")
        reconstructed = build_lane_observation(journey, key, receipt["signer"], lane,
            ms61_sha256=receipt["source_ms61_receipt_sha256"], ms64_sha256=receipt["source_ms64_receipt_sha256"],
            oracle_image_id_sha256=receipt["oracle_image_id_sha256"],
            postgresql_image_id_sha256=receipt["postgresql_image_id_sha256"],
            comparison_run_id=receipt["comparison_run_id"],
            oracle_source_image_lock_sha256=receipt["oracle_source_image_lock_sha256"],
            postgresql_image_lock_sha256=receipt["postgresql_image_lock_sha256"],
            oracle_journey_sha256=receipt["oracle_journey_sha256"],
            postgresql_journey_sha256=receipt["postgresql_journey_sha256"],
            expected_images=value[images], recovery={"status": "restored", "errors": []})
        require(reconstructed["content_sha256"] == receipt[lane + "_observation_sha256"],
                "ms71-comparator-observation-mismatch")
    bindings = value["target_journey"]["bindings"]
    require(bindings.get("ms71_campaign_id") == value["campaign_id"]
            and bindings.get("managed_target_sha256") == before["content_sha256"]
            and bindings.get("environment") == environment
            and bindings.get("managed_probe_sql") == probe, "ms71-live-journey-binding-invalid")
    recovery = value["recovery"]
    require(isinstance(recovery, dict) and set(recovery) == {"oracle", "target"}
            and all(row.get("status") == "restored" and row.get("errors") == []
                    for row in recovery.values()), "ms71-recovery-incomplete")
    require(recovery["oracle"].get("remaining_isolated_namespace") is None
            and recovery["oracle"].get("remaining_model_policy") is None
            and recovery["target"].get("remaining_stopped_services", []) == [], "ms71-recovery-incomplete")


def comparison_receipt(*, campaign_id, controller_commit, profile, before, after, probe_sql,
                       comparison, oracle_journey, target_journey, source_images, target_images,
                       recovery, key, signer, root):
    value = sign({"schema_version": "1.0", "receipt_type": COMPARISON_TYPE,
        "campaign_id": campaign_id, "controller_commit": controller_commit, "profile": profile,
        "before": before, "after": after, "probe_sql": probe_sql, "comparison": comparison,
        "oracle_journey": oracle_journey, "target_journey": target_journey,
        "source_images": source_images, "target_images": target_images, "recovery": recovery,
        "production_ready": False, "ms71_complete": False}, key, signer)
    validate_comparison(value, key, root)
    return value


def admit(comparisons: list[dict], key: str, signer: str, root: Path) -> dict:
    require(isinstance(comparisons, list) and len(comparisons) == 2, "ms71-two-comparisons-required")
    for value in comparisons:
        validate_comparison(value, key, root)
    rows = {value["profile"]["provider"]: value for value in comparisons}
    require(set(rows) == set(PROVIDERS), "ms71-both-target-providers-required")
    a, b = [rows[p] for p in PROVIDERS]
    require(a["campaign_id"] == b["campaign_id"] and a["controller_commit"] == b["controller_commit"]
            and a["source_images"] == b["source_images"] and a["target_images"] == b["target_images"]
            and a["profile"]["databases"] == b["profile"]["databases"]
            and a["profile"]["database_version"] == b["profile"]["database_version"]
            and all(a["comparison"][f] == b["comparison"][f] for f in COMMON_FIELDS),
            "ms71-common-inputs-differ")
    require(a["comparison"]["comparison_run_id"] != b["comparison"]["comparison_run_id"]
            and a["oracle_journey"]["content_sha256"] != b["oracle_journey"]["content_sha256"]
            and a["before"]["environment"]["namespace_uid_sha256"] != b["before"]["environment"]["namespace_uid_sha256"]
            and a["before"]["database"]["address"] != b["before"]["database"]["address"]
            and a["profile"]["resource"] != b["profile"]["resource"], "ms71-target-isolation-invalid")
    require(bool(signer.strip()), "ms71-signer-required")
    return sign({"schema_version": "1.0", "receipt_type": RECEIPT_TYPE,
        "campaign_id": a["campaign_id"], "controller_commit": a["controller_commit"],
        "status": "passed-two-target-equivalence", "comparisons": [rows[p] for p in PROVIDERS],
        "services": list(SERVICES), "scenarios_per_comparison": 18,
        "ms71_complete": True, "production_ready": False,
        "alloydb_platform_qualified": False, "synthetic_data_only": True}, key, signer)


def verify_receipt(value: dict, key: str, root: Path) -> None:
    signed(value, key)
    expected = admit(value.get("comparisons"), key, value["signature"].get("signer", ""), root)
    require(value == expected, "ms71-acceptance-receipt-invalid")
