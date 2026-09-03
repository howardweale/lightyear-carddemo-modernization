from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from lightyear_common.io import write_json

from .cloudbank_edge_ai import (
    RECEIPT_TYPE as MS64_RECEIPT_TYPE,
    materialize_target as materialize_ms64_target,
    validate_edge_source,
    validate_execution_receipt as validate_ms64_receipt,
)
from .cloudbank_oracle_equivalence import (
    RECEIPT_TYPE as MS61_RECEIPT_TYPE,
    validate_execution_receipt as validate_ms61_receipt,
)
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.66.0"
OUTPUT_ROOT = Path("factory/cloudbank/whole-application-equivalence")
RECEIPT_TYPE = "lightyear-cloudbank-whole-application-equivalence-execution"
RECEIPT_NAME = "cloudbank-whole-application-equivalence.receipt.json"
FAILURE_NAME = "cloudbank-whole-application-equivalence.failure.json"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")

SERVICES = (
    "azn-server", "customer", "account", "transfer", "checks", "testrunner",
    "creditscore", "chatbot",
)

SCENARIOS = (
    ("eight-services-ready", "all-ready"),
    ("authorization-token-issued", "token-issued"),
    ("unauthenticated-request-rejected", "401"),
    ("customer-owner-read", "owner-visible"),
    ("account-balance-read", "balance-visible"),
    ("transfer-success-conserves-value", "conserved"),
    ("transfer-invalid-no-mutation", "400-no-mutation"),
    ("transfer-insufficient-funds-no-mutation", "rejected-no-mutation"),
    ("check-deposit-applied-once", "deposit-once"),
    ("check-clearance-applied-once", "clearance-once"),
    ("duplicate-message-suppressed", "duplicate-suppressed"),
    ("credit-score-contract-served", "score-in-declared-range"),
    ("chatbot-boundary-served", "bounded-response"),
    ("account-restart-preserves-state", "state-preserved"),
    ("checks-restart-redelivers-inflight", "redelivered-once"),
    ("transfer-dependency-failure-recovers", "restored"),
    ("concurrent-opposite-transfers-conserve-value", "conserved"),
    ("full-stack-restart-restores-journey", "journey-restored"),
)
SCENARIO_IDS = [identifier for identifier, _ in SCENARIOS]
NORMALIZED_MARKER = ";".join(f"{identifier}:{result}" for identifier, result in SCENARIOS)
OBSERVATION_SHA256 = hashlib.sha256(NORMALIZED_MARKER.encode()).hexdigest()

MINIMUM_START_COUNTS = {
    "azn-server": 2,
    "customer": 2,
    "account": 3,
    "transfer": 3,
    "checks": 3,
    "testrunner": 2,
    "creditscore": 2,
    "chatbot": 2,
}


def lane_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-whole-application-lanes",
        "release": RELEASE,
        "services": list(SERVICES),
        "lanes": {
            "oracle": {
                "application": "exact-pinned-cloudbank-source",
                "database": "native-oracle",
                "messaging": "oracle-transactional-event-queue",
                "transactions": "microtx-lra",
            },
            "postgresql": {
                "application": "exact-ms64-generated-target",
                "database": "native-postgresql",
                "messaging": "postgresql-durable-work-queue",
                "transactions": "postgresql-atomic-transaction",
            },
        },
        "required_service_state": {
            service: {"final_status": "ready", "minimum_start_count": MINIMUM_START_COUNTS[service]}
            for service in SERVICES
        },
        "comparison": "exact-normalized-business-observations",
        "same_internal_implementation_required": False,
        "synthetic_data_only": True,
    })


def journey_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-whole-application-journeys",
        "release": RELEASE,
        "scenario_count": len(SCENARIOS),
        "scenarios": [
            {"id": identifier, "normalized_result": result}
            for identifier, result in SCENARIOS
        ],
        "normalized_marker": NORMALIZED_MARKER,
        "normalized_observation_sha256": OBSERVATION_SHA256,
        "coverage": {
            "business_journeys": True,
            "negative_paths": True,
            "targeted_restarts": True,
            "concurrency": True,
            "full_stack_restart": True,
        },
        "credit_score_comparison": "declared-range-contract-not-exact-value",
        "chatbot_comparison": "bounded-response-contract-not-model-answer",
    })


def execution_plan() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "plan_type": "lightyear-cloudbank-whole-application-dual-lane-equivalence",
        "release": RELEASE,
        "requires": [
            "signed-ms61-oracle-postgresql-core-equivalence-receipt",
            "signed-ms64-eight-service-target-receipt",
            "same-evidence-key",
            "same-postgresql-image",
            "operator-signed-oracle-and-postgresql-observations",
        ],
        "services": list(SERVICES),
        "runtime_order": "isolated-sequential-lanes",
        "stages": [
            "validate-contracts-pinned-source-and-signed-ms61-ms64",
            "materialize-fresh-ms64-eight-service-target",
            "start-all-eight-pinned-source-services-on-native-oracle",
            "run-shared-business-failure-concurrency-and-recovery-harness",
            "restart-and-recover-all-eight-source-services",
            "start-all-eight-generated-target-services-on-native-postgresql",
            "run-identical-business-failure-concurrency-and-recovery-harness",
            "restart-and-recover-all-eight-target-services",
            "compare-exact-normalized-observations",
            "sign-bounded-whole-application-equivalence-receipt",
        ],
        "required_scenarios": SCENARIO_IDS,
        "fresh_output_required": True,
        "source_checkout_mutated": False,
        "production_data": False,
        "production_environment": False,
        "production_ready": False,
    })


def compatibility_ledger() -> dict[str, Any]:
    rows = [
        ("eight-service-startup", "dual-lane-qualified", "all-ready-and-restarted"),
        ("identity-boundary", "normalized-equivalent", "token-and-401-journeys"),
        ("customer-and-account-reads", "normalized-equivalent", "owner-and-balance"),
        ("money-transfer", "normalized-equivalent", "success-negative-recovery-concurrency"),
        ("checks-messaging", "normalized-equivalent", "once-only-and-redelivery"),
        ("oracle-aq-versus-postgresql-queue", "intentional-change", "same-business-outcome"),
        ("microtx-lra-versus-atomic-transaction", "intentional-change", "same-recovery-outcome"),
        ("credit-score", "contract-equivalent", "range-not-exact-value"),
        ("real-credit-decision", "not-qualified", "approved-provider-required"),
        ("chatbot", "contract-equivalent", "boundary-not-answer-quality"),
        ("model-answer-quality", "not-qualified", "approved-model-evaluation-required"),
        ("production-data", "not-qualified", "customer-authorization-required"),
        ("production-platform", "not-qualified", "ms67-platform-qualification"),
        ("production-readiness", "not-qualified", "ms68-customer-certification"),
    ]
    return seal({
        "schema_version": "1.0",
        "ledger_type": "lightyear-cloudbank-whole-application-equivalence-compatibility",
        "release": RELEASE,
        "entries": [
            {"capability": capability, "classification": classification, "evidence": evidence}
            for capability, classification, evidence in rows
        ],
        "whole_application_equivalence_eligible": True,
        "exact_internal_implementation_equivalent": False,
        "migration_complete": False,
        "production_ready": False,
    })


def acceptance_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-whole-application-equivalence-acceptance",
        "release": RELEASE,
        "bindings": {
            "lane_contract_sha256": lane_contract()["content_sha256"],
            "journey_contract_sha256": journey_contract()["content_sha256"],
            "execution_plan_sha256": execution_plan()["content_sha256"],
            "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
        },
        "required_receipts": [MS61_RECEIPT_TYPE, MS64_RECEIPT_TYPE],
        "required_services": list(SERVICES),
        "required_scenarios": SCENARIO_IDS,
        "required_normalized_observation_sha256": OBSERVATION_SHA256,
        "eligible_claim": {
            "all_eight_services_observed_in_both_lanes": True,
            "bounded_whole_application_equivalent": True,
            "whole_application_equivalent": True,
            "exact_internal_implementation_equivalent": False,
            "real_credit_decision_equivalent": False,
            "model_quality_qualified": False,
            "migration_complete": False,
            "production_deployed": False,
            "production_ready": False,
        },
    })


def readiness_receipt() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-cloudbank-whole-application-equivalence-readiness",
        "release": RELEASE,
        "bindings": acceptance_contract()["bindings"],
        "acceptance_contract_sha256": acceptance_contract()["content_sha256"],
        "gate_status": "ready-for-signed-ms61-ms64-and-dual-lane-observations",
        "all_eight_services_observed_in_both_lanes": False,
        "bounded_whole_application_equivalent": False,
        "whole_application_equivalent": False,
        "exact_internal_implementation_equivalent": False,
        "migration_complete": False,
        "production_deployed": False,
        "production_ready": False,
    })


def build_artifacts() -> dict[str, dict[str, Any]]:
    return {
        "lane-contract.json": lane_contract(),
        "journey-contract.json": journey_contract(),
        "execution-plan.json": execution_plan(),
        "compatibility-ledger.json": compatibility_ledger(),
        "acceptance-contract.json": acceptance_contract(),
        "readiness.receipt.json": readiness_receipt(),
    }


def write_artifacts(project_root: Path) -> None:
    root = project_root / OUTPUT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    for name, payload in build_artifacts().items():
        write_json(root / name, payload)


def validate_artifacts(project_root: Path) -> list[str]:
    errors: list[str] = []
    root = project_root / OUTPUT_ROOT
    for name, expected in build_artifacts().items():
        try:
            actual = json.loads((root / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"cloudbank-whole-application-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-whole-application-artifact-drift:{name}")
    if len(SCENARIOS) != 18 or len(set(SCENARIO_IDS)) != 18:
        errors.append("cloudbank-whole-application-scenarios-invalid")
    ready = readiness_receipt()
    if ready["bounded_whole_application_equivalent"] \
            or ready["whole_application_equivalent"] or ready["production_ready"]:
        errors.append("cloudbank-whole-application-readiness-overclaims")
    return sorted(set(errors))


def _observation_bindings(
    ms61_sha256: str, ms64_sha256: str, oracle_image: str, postgres_image: str,
    comparison_run_id: str,
) -> dict[str, str]:
    return {
        "source_ms61_receipt_sha256": ms61_sha256,
        "source_ms64_receipt_sha256": ms64_sha256,
        "oracle_image_id_sha256": oracle_image,
        "postgresql_image_id_sha256": postgres_image,
        "lane_contract_sha256": lane_contract()["content_sha256"],
        "journey_contract_sha256": journey_contract()["content_sha256"],
        "comparison_run_id": comparison_run_id,
    }


def validate_lane_observation(
    observation: Mapping[str, Any], key: str, lane: str, *, ms61_sha256: str,
    ms64_sha256: str, oracle_image: str, postgres_image: str, comparison_run_id: str,
) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "schema_version", "observation_type", "release", "lane", "bindings",
        "database_engine", "services", "scenarios", "normalized_marker",
        "normalized_observation_sha256", "synthetic_data_only", "production_environment",
        "credentials_persisted", "raw_output_persisted", "content_sha256", "signature",
    }
    if set(observation) != expected_fields:
        errors.append(f"cloudbank-whole-application-{lane}-observation-fields-invalid")
    if observation.get("observation_type") != "lightyear-cloudbank-ms66-lane-observation" \
            or observation.get("release") != RELEASE or observation.get("lane") != lane:
        errors.append(f"cloudbank-whole-application-{lane}-observation-identity-invalid")
    if observation.get("content_sha256") != content_hash(dict(observation)) \
            or not key or not verify_signature(dict(observation), key):
        errors.append(f"cloudbank-whole-application-{lane}-observation-signature-invalid")
    expected_bindings = _observation_bindings(
        ms61_sha256, ms64_sha256, oracle_image, postgres_image, comparison_run_id,
    )
    if observation.get("bindings") != expected_bindings:
        errors.append(f"cloudbank-whole-application-{lane}-observation-binding-invalid")
    expected_engine = "oracle" if lane == "oracle" else "postgresql"
    if observation.get("database_engine") != expected_engine:
        errors.append(f"cloudbank-whole-application-{lane}-database-invalid")
    services = observation.get("services") or []
    if not isinstance(services, list) or any(not isinstance(item, Mapping) for item in services):
        services = []
    service_ids = [item.get("service") for item in services]
    service_rows_invalid = service_ids != list(SERVICES)
    if not service_rows_invalid:
        service_rows_invalid = any(
            set(item) != {"service", "executable_sha256", "start_count", "final_status"}
            or not HEX_64.fullmatch(str(item.get("executable_sha256", "")))
            or not isinstance(item.get("start_count"), int)
            or item.get("start_count", 0) < MINIMUM_START_COUNTS[str(item.get("service"))]
            or item.get("final_status") != "ready"
            for item in services
        )
    if service_rows_invalid:
        errors.append(f"cloudbank-whole-application-{lane}-services-invalid")
    scenarios = observation.get("scenarios") or []
    if not isinstance(scenarios, list) or any(not isinstance(item, Mapping) for item in scenarios):
        scenarios = []
    expected_results = dict(SCENARIOS)
    if [item.get("id") for item in scenarios] != SCENARIO_IDS or any(
        set(item) != {"id", "normalized_result", "evidence_sha256"}
        or item.get("normalized_result") != expected_results.get(item.get("id"))
        or not HEX_64.fullmatch(str(item.get("evidence_sha256", "")))
        for item in scenarios
    ):
        errors.append(f"cloudbank-whole-application-{lane}-scenarios-invalid")
    if observation.get("normalized_marker") != NORMALIZED_MARKER \
            or observation.get("normalized_observation_sha256") != OBSERVATION_SHA256:
        errors.append(f"cloudbank-whole-application-{lane}-normalization-invalid")
    safety = {
        "synthetic_data_only": True,
        "production_environment": False,
        "credentials_persisted": False,
        "raw_output_persisted": False,
    }
    if any(observation.get(name) is not value for name, value in safety.items()):
        errors.append(f"cloudbank-whole-application-{lane}-safety-invalid")
    return sorted(set(errors))


def execute_equivalence(
    project_root: Path, source_root: Path, ms61_receipt: Mapping[str, Any],
    ms64_receipt: Mapping[str, Any], oracle_observation: Mapping[str, Any],
    postgres_observation: Mapping[str, Any], output_root: Path, key: str, signer: str,
    run_id: str | None = None,
    *, materializer: Callable[[Path, Path, Path], Path] = materialize_ms64_target,
) -> dict[str, Any]:
    if not key:
        raise ValueError("cloudbank-whole-application-evidence-key-required")
    if not signer.strip():
        raise ValueError("cloudbank-whole-application-signer-required")
    errors = validate_artifacts(project_root) + validate_edge_source(source_root)
    errors += validate_ms61_receipt(ms61_receipt, key, project_root)
    errors += validate_ms64_receipt(ms64_receipt, key, project_root)
    if ms61_receipt.get("receipt_type") != MS61_RECEIPT_TYPE \
            or ms64_receipt.get("receipt_type") != MS64_RECEIPT_TYPE:
        errors.append("cloudbank-whole-application-prior-receipts-required")
    if errors:
        raise ValueError(",".join(sorted(set(errors))))
    oracle_image = str(ms61_receipt.get("oracle_image_id_sha256", ""))
    postgres_image = str(ms61_receipt.get("postgresql_image_id_sha256", ""))
    if not HEX_64.fullmatch(oracle_image) or not HEX_64.fullmatch(postgres_image):
        raise ValueError("cloudbank-whole-application-image-identity-invalid")
    if ms64_receipt.get("postgresql_image_id_sha256") != postgres_image:
        raise ValueError("cloudbank-whole-application-postgresql-image-chain-invalid")
    resolved_source, resolved_output = source_root.resolve(), output_root.resolve()
    if resolved_output == resolved_source or resolved_source in resolved_output.parents:
        raise ValueError("cloudbank-whole-application-output-inside-source")
    if resolved_output.exists() and any(resolved_output.iterdir()):
        raise ValueError("cloudbank-whole-application-fresh-output-required")
    resolved_output.mkdir(parents=True, exist_ok=True)
    workspace = materializer(project_root, source_root, resolved_output / "target-workspace")
    if any(not (workspace / service / "pom.xml").is_file() for service in SERVICES):
        raise ValueError("cloudbank-whole-application-eight-service-target-invalid")
    comparison_id = str((oracle_observation.get("bindings") or {}).get("comparison_run_id", ""))
    observation_errors = validate_lane_observation(
        oracle_observation, key, "oracle",
        ms61_sha256=str(ms61_receipt["content_sha256"]),
        ms64_sha256=str(ms64_receipt["content_sha256"]), oracle_image=oracle_image,
        postgres_image=postgres_image, comparison_run_id=comparison_id,
    ) + validate_lane_observation(
        postgres_observation, key, "postgresql",
        ms61_sha256=str(ms61_receipt["content_sha256"]),
        ms64_sha256=str(ms64_receipt["content_sha256"]), oracle_image=oracle_image,
        postgres_image=postgres_image, comparison_run_id=comparison_id,
    )
    if not comparison_id.strip():
        observation_errors.append("cloudbank-whole-application-comparison-run-id-invalid")
    if oracle_observation.get("normalized_marker") != postgres_observation.get("normalized_marker") \
            or oracle_observation.get("normalized_observation_sha256") != \
            postgres_observation.get("normalized_observation_sha256"):
        observation_errors.append("cloudbank-whole-application-lanes-differ")
    if observation_errors:
        write_json(resolved_output / FAILURE_NAME, {
            "schema_version": "1.0", "status": "failed-bounded-whole-application-equivalence",
            "reason_codes": sorted(set(observation_errors)), "synthetic_data_only": True,
            "credentials_persisted": False, "raw_output_persisted": False,
        })
        raise ValueError("cloudbank-whole-application-acceptance-failed")
    receipt = sign({
        "schema_version": "1.0", "receipt_type": RECEIPT_TYPE, "release": RELEASE,
        "run_id": run_id or f"cloudbank-whole-application-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}",
        "comparison_run_id": comparison_id, "signer": signer,
        "bindings": readiness_receipt()["bindings"],
        "source_ms61_receipt_sha256": ms61_receipt["content_sha256"],
        "source_ms64_receipt_sha256": ms64_receipt["content_sha256"],
        "oracle_image_id_sha256": oracle_image,
        "postgresql_image_id_sha256": postgres_image,
        "oracle_observation_sha256": oracle_observation["content_sha256"],
        "postgresql_observation_sha256": postgres_observation["content_sha256"],
        "normalized_observation_sha256": OBSERVATION_SHA256,
        "services": list(SERVICES), "scenario_count": len(SCENARIOS),
        "status": "passed-bounded-whole-application-equivalence",
        "all_eight_services_observed_in_both_lanes": True,
        "bounded_whole_application_equivalent": True,
        "whole_application_equivalent": True,
        "exact_internal_implementation_equivalent": False,
        "real_credit_decision_equivalent": False, "model_quality_qualified": False,
        "migration_complete": False, "production_deployed": False, "production_ready": False,
        "security": {"synthetic_data_only": True, "production_environment": False,
                     "credentials_persisted": False, "raw_output_persisted": False,
                     "source_checkout_mutated": False},
    }, key, signer)
    write_json(resolved_output / RECEIPT_NAME, receipt)
    return receipt


def validate_execution_receipt(
    receipt: Mapping[str, Any], key: str, project_root: Path,
) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "schema_version", "receipt_type", "release", "run_id", "comparison_run_id",
        "signer", "bindings", "source_ms61_receipt_sha256", "source_ms64_receipt_sha256",
        "oracle_image_id_sha256", "postgresql_image_id_sha256",
        "oracle_observation_sha256", "postgresql_observation_sha256",
        "normalized_observation_sha256", "services", "scenario_count", "status",
        "all_eight_services_observed_in_both_lanes",
        "bounded_whole_application_equivalent", "exact_internal_implementation_equivalent",
        "whole_application_equivalent",
        "real_credit_decision_equivalent", "model_quality_qualified", "migration_complete",
        "production_deployed", "production_ready", "security", "content_sha256", "signature",
    }
    if set(receipt) != expected_fields:
        errors.append("cloudbank-whole-application-receipt-fields-invalid")
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("release") != RELEASE:
        errors.append("cloudbank-whole-application-receipt-identity-invalid")
    if receipt.get("status") != "passed-bounded-whole-application-equivalence":
        errors.append("cloudbank-whole-application-receipt-status-invalid")
    if receipt.get("content_sha256") != content_hash(dict(receipt)) \
            or not key or not verify_signature(dict(receipt), key):
        errors.append("cloudbank-whole-application-receipt-signature-invalid")
    if receipt.get("bindings") != readiness_receipt()["bindings"]:
        errors.append("cloudbank-whole-application-receipt-binding-invalid")
    for name in (
        "source_ms61_receipt_sha256", "source_ms64_receipt_sha256",
        "oracle_image_id_sha256", "postgresql_image_id_sha256",
        "oracle_observation_sha256", "postgresql_observation_sha256",
        "normalized_observation_sha256",
    ):
        if not HEX_64.fullmatch(str(receipt.get(name, ""))):
            errors.append(f"cloudbank-whole-application-receipt-{name}-invalid")
    if receipt.get("normalized_observation_sha256") != OBSERVATION_SHA256 \
            or receipt.get("services") != list(SERVICES) \
            or receipt.get("scenario_count") != len(SCENARIOS):
        errors.append("cloudbank-whole-application-receipt-coverage-invalid")
    expected = {
        "all_eight_services_observed_in_both_lanes": True,
        "bounded_whole_application_equivalent": True,
        "whole_application_equivalent": True,
        "exact_internal_implementation_equivalent": False,
        "real_credit_decision_equivalent": False,
        "model_quality_qualified": False,
        "migration_complete": False,
        "production_deployed": False,
        "production_ready": False,
    }
    if any(receipt.get(name) is not value for name, value in expected.items()):
        errors.append("cloudbank-whole-application-receipt-claims-invalid")
    security = receipt.get("security") or {}
    expected_security = {"synthetic_data_only": True, "production_environment": False,
                         "credentials_persisted": False, "raw_output_persisted": False,
                         "source_checkout_mutated": False}
    if security != expected_security:
        errors.append("cloudbank-whole-application-receipt-security-invalid")
    if not str(receipt.get("comparison_run_id", "")).strip() \
            or not str(receipt.get("signer", "")).strip():
        errors.append("cloudbank-whole-application-receipt-provenance-invalid")
    signature = receipt.get("signature") or {}
    if not isinstance(signature, Mapping) or signature.get("signer") != receipt.get("signer"):
        errors.append("cloudbank-whole-application-receipt-provenance-invalid")
    if validate_artifacts(project_root):
        errors.append("cloudbank-whole-application-repository-artifacts-invalid")
    return sorted(set(errors))
