"""Fail-closed contracts for the durable MS66 dual-lane execution.

This module contains the pure validation and evidence conversion logic.  The
GKE adapter lives in :mod:`cloudbank_ms66_dual_lane_gke`; keeping Kubernetes
I/O out of this module makes the evidence boundary independently testable.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from .cloudbank_journeys import OBSERVATION_TYPE as JOURNEY_OBSERVATION_TYPE
from .cloudbank_ms66_hardening import (
    HARDENING_CONTRACT_SHA256,
    PATCH_SHA256,
    SOURCE_IMAGE_LOCK_TYPE,
    validate_source_image_lock,
)
from .cloudbank_whole_application_equivalence import (
    MINIMUM_START_COUNTS,
    NORMALIZED_MARKER,
    OBSERVATION_SHA256,
    RELEASE,
    SCENARIOS,
    SCENARIO_IDS,
    SERVICES,
    journey_contract,
    lane_contract,
)
from .contracts import content_hash, sign, verify_signature


LANE_OBSERVATION_TYPE = "lightyear-cloudbank-ms66-lane-observation"
RECOVERY_STATE_TYPE = "lightyear-cloudbank-ms66-isolated-lane-recovery"
FAILURE_TYPE = "lightyear-cloudbank-ms66-dual-lane-failure"
IMMUTABLE_IMAGE = re.compile(
    r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+@sha256:[0-9a-f]{64}$"
)
HEX_64 = re.compile(r"^[0-9a-f]{64}$")

APPLICATION_IDENTITIES = {
    "oracle": "pinned-source-plus-governed-hardening",
    "postgresql": "exact-ms64-generated-target",
}
NATIVE_RUNTIMES = {
    "oracle": {
        "database": "oracle-free",
        "messaging": "oracle-aq-jms",
        "transactions": "oracle-microtx-lra",
    },
    "postgresql": {
        "database": "postgresql",
        "messaging": "postgresql-durable-work-queue",
        "transactions": "postgresql-atomic-transaction",
    },
}
RECOVERY_PHASES = {
    "planned",
    "namespace-create-pending",
    "namespace-created",
    "model-policy-create-pending",
    "model-policy-created",
    "native-runtime-ready",
    "eight-source-services-ready",
    "journeys-complete",
    "cleanup-pending",
    "restored",
}


def _recovery_identity_is_valid(
    phase: Any, namespace_uid: Any, model_policy_uid: Any,
) -> bool:
    if phase in {"planned", "namespace-create-pending", "restored"}:
        return namespace_uid is None and model_policy_uid is None
    if phase in {"namespace-created", "model-policy-create-pending"}:
        return isinstance(namespace_uid, str) and bool(namespace_uid.strip()) \
            and model_policy_uid is None
    if phase in {
        "model-policy-created", "native-runtime-ready",
        "eight-source-services-ready", "journeys-complete",
    }:
        return isinstance(namespace_uid, str) and bool(namespace_uid.strip()) \
            and isinstance(model_policy_uid, str) and bool(model_policy_uid.strip())
    if phase == "cleanup-pending":
        return (namespace_uid is None or (
            isinstance(namespace_uid, str) and bool(namespace_uid.strip())
        )) and (model_policy_uid is None or (
            isinstance(model_policy_uid, str) and bool(model_policy_uid.strip())
        ))
    return False


def image_rows(lock: Mapping[str, Any]) -> dict[str, str]:
    """Return the exact eight-service map from an already validated lock."""
    rows = lock.get("images") if isinstance(lock.get("images"), list) else []
    result = {
        str(row.get("service")): str(row.get("reference"))
        for row in rows
        if isinstance(row, Mapping)
    }
    if set(result) != set(SERVICES) or any(
        not IMMUTABLE_IMAGE.fullmatch(result[service]) for service in SERVICES
    ):
        raise ValueError("cloudbank-ms66-eight-immutable-images-required")
    return result


def _journey_binding_errors(
    journey: Mapping[str, Any], lane: str, image_lock_sha256: str,
) -> list[str]:
    bindings = journey.get("bindings") or {}
    if not isinstance(bindings, Mapping):
        return [f"cloudbank-ms66-{lane}-journey-binding-invalid"]
    expected_lane = "gke-oracle-governed-source" if lane == "oracle" else "gke-postgresql-target"
    lock_key = "source_image_lock_sha256" if lane == "oracle" else "image_lock_sha256"
    errors: list[str] = []
    if bindings.get("lane") != expected_lane \
            or bindings.get(lock_key) != image_lock_sha256 \
            or bindings.get("journey_contract_sha256") != journey_contract()["content_sha256"]:
        errors.append(f"cloudbank-ms66-{lane}-journey-binding-invalid")
    if lane == "oracle" and (
        bindings.get("hardening_contract_sha256") != HARDENING_CONTRACT_SHA256
        or bindings.get("hardening_patch_sha256") != PATCH_SHA256
    ):
        errors.append("cloudbank-ms66-oracle-journey-hardening-binding-invalid")
    return errors


def validate_shared_journey(
    journey: Mapping[str, Any], key: str, lane: str, *, image_lock_sha256: str,
    expected_images: Mapping[str, str],
) -> list[str]:
    """Validate a shared journey before it can be converted into MS66 evidence."""
    if lane not in APPLICATION_IDENTITIES:
        return ["cloudbank-ms66-lane-invalid"]
    prefix = f"cloudbank-ms66-{lane}-journey"
    errors: list[str] = []
    if journey.get("observation_type") != JOURNEY_OBSERVATION_TYPE \
            or journey.get("status") != "passed-shared-journeys" \
            or journey.get("scenario_count") != len(SCENARIOS):
        errors.append(prefix + "-identity-invalid")
    if journey.get("content_sha256") != content_hash(dict(journey)) \
            or not key or not verify_signature(dict(journey), key):
        errors.append(prefix + "-signature-invalid")
    errors.extend(_journey_binding_errors(journey, lane, image_lock_sha256))

    scenarios = journey.get("scenarios") if isinstance(journey.get("scenarios"), list) else []
    expected = dict(SCENARIOS)
    if [row.get("id") for row in scenarios if isinstance(row, Mapping)] != SCENARIO_IDS \
            or len(scenarios) != len(SCENARIOS) or any(
                not isinstance(row, Mapping)
                or row.get("status") != "passed"
                or row.get("normalized_result") != expected.get(row.get("id"))
                or not HEX_64.fullmatch(str(row.get("evidence_sha256", "")))
                for row in scenarios
            ):
        errors.append(prefix + "-scenarios-invalid")

    final = scenarios[-1] if scenarios and isinstance(scenarios[-1], Mapping) else {}
    evidence = final.get("evidence") if isinstance(final.get("evidence"), Mapping) else {}
    services = evidence.get("services") if isinstance(evidence.get("services"), Mapping) else {}
    if set(services) != set(SERVICES) or set(expected_images) != set(SERVICES):
        errors.append(prefix + "-services-invalid")
    else:
        for service in SERVICES:
            row = services.get(service) if isinstance(services.get(service), Mapping) else {}
            if row.get("image") != expected_images[service] \
                    or row.get("ready_replicas") != 2 \
                    or row.get("http_readiness") != 200 \
                    or type(row.get("observed_start_count")) is not int \
                    or row.get("observed_start_count", 0) < MINIMUM_START_COUNTS[service]:
                errors.append(prefix + "-services-invalid")
                break

    recovery = journey.get("recovery") or {}
    if not isinstance(recovery, Mapping) or recovery.get("status") != "restored" \
            or recovery.get("errors") != [] \
            or recovery.get("remaining_stopped_services", []) != []:
        errors.append(prefix + "-recovery-invalid")
    safety = {
        "synthetic_data_only": True,
        "production_environment": False,
        "credentials_persisted": False,
        "raw_output_persisted": False,
        "whole_application_equivalent": False,
        "ms65_complete": False,
        "ms66_complete": False,
        "ms67_complete": False,
        "fixture_records_retained": True,
    }
    if any(journey.get(field) is not expected_value for field, expected_value in safety.items()):
        errors.append(prefix + "-safety-invalid")
    return sorted(set(errors))


def build_lane_observation(
    journey: Mapping[str, Any], key: str, signer: str, lane: str, *,
    ms61_sha256: str, ms64_sha256: str, oracle_image_id_sha256: str,
    postgresql_image_id_sha256: str, comparison_run_id: str,
    oracle_source_image_lock_sha256: str, postgresql_image_lock_sha256: str,
    oracle_journey_sha256: str, postgresql_journey_sha256: str,
    expected_images: Mapping[str, str],
    recovery: Mapping[str, Any],
) -> dict[str, Any]:
    errors = validate_shared_journey(
        journey, key, lane,
        image_lock_sha256=(
            oracle_source_image_lock_sha256 if lane == "oracle"
            else postgresql_image_lock_sha256
        ),
        expected_images=expected_images,
    )
    if errors:
        raise ValueError(",".join(errors))
    if not signer.strip() or not comparison_run_id.strip() \
            or any(not HEX_64.fullmatch(value) for value in (
                ms61_sha256, ms64_sha256, oracle_image_id_sha256,
                postgresql_image_id_sha256, oracle_source_image_lock_sha256,
                postgresql_image_lock_sha256, oracle_journey_sha256,
                postgresql_journey_sha256,
            )):
        raise ValueError("cloudbank-ms66-lane-observation-provenance-invalid")
    if not isinstance(recovery, Mapping) \
            or recovery.get("status") != "restored" or recovery.get("errors") != []:
        raise ValueError("cloudbank-ms66-lane-observation-recovery-invalid")
    scenarios = journey["scenarios"]
    final_services = scenarios[-1]["evidence"]["services"]
    bindings = {
        "source_ms61_receipt_sha256": ms61_sha256,
        "source_ms64_receipt_sha256": ms64_sha256,
        "oracle_image_id_sha256": oracle_image_id_sha256,
        "postgresql_image_id_sha256": postgresql_image_id_sha256,
        "lane_contract_sha256": lane_contract()["content_sha256"],
        "journey_contract_sha256": journey_contract()["content_sha256"],
        "oracle_hardening_contract_sha256": HARDENING_CONTRACT_SHA256,
        "oracle_hardening_patch_sha256": PATCH_SHA256,
        "oracle_source_image_lock_sha256": oracle_source_image_lock_sha256,
        "postgresql_image_lock_sha256": postgresql_image_lock_sha256,
        "oracle_journey_sha256": oracle_journey_sha256,
        "postgresql_journey_sha256": postgresql_journey_sha256,
        "comparison_run_id": comparison_run_id,
    }
    return sign({
        "schema_version": "1.0",
        "observation_type": LANE_OBSERVATION_TYPE,
        "release": RELEASE,
        "lane": lane,
        "bindings": bindings,
        "database_engine": lane,
        "application_identity": APPLICATION_IDENTITIES[lane],
        "native_runtime": NATIVE_RUNTIMES[lane],
        "source_checkout_mutated": False,
        "services": [
            {
                "service": service,
                "executable_sha256": expected_images[service].rsplit("@sha256:", 1)[1],
                "start_count": final_services[service]["observed_start_count"],
                "final_status": "ready",
            }
            for service in SERVICES
        ],
        "scenarios": [
            {
                "id": row["id"],
                "normalized_result": row["normalized_result"],
                "evidence_sha256": row["evidence_sha256"],
            }
            for row in scenarios
        ],
        "normalized_marker": NORMALIZED_MARKER,
        "normalized_observation_sha256": OBSERVATION_SHA256,
        "synthetic_data_only": True,
        "production_environment": False,
        "credentials_persisted": False,
        "raw_output_persisted": False,
        "recovery": dict(recovery),
    }, key, signer)


def recovery_state(
    *, run_id: str, context: str, namespace: str, source_image_lock_sha256: str,
    phase: str, namespace_uid: str | None, model_namespace: str,
    model_policy_name: str, model_policy_uid: str | None, cleanup_required: bool,
    key: str, signer: str,
) -> dict[str, Any]:
    if not key or not signer.strip() \
            or not re.fullmatch(r"ms66-[a-z0-9-]{1,54}", run_id) \
            or not re.fullmatch(r"gke_[a-z0-9-]+_[a-z0-9-]+_[a-z0-9-]+", context) \
            or any(not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", value)
                   for value in (namespace, model_namespace, model_policy_name)) \
            or not HEX_64.fullmatch(source_image_lock_sha256) \
            or any(len(value) > 63 for value in (namespace, model_namespace, model_policy_name)) \
            or phase not in RECOVERY_PHASES \
            or cleanup_required is not (phase not in {"planned", "restored"}) \
            or not _recovery_identity_is_valid(phase, namespace_uid, model_policy_uid):
        raise ValueError("cloudbank-ms66-recovery-state-input-invalid")
    return sign({
        "schema_version": "1.0",
        "state_type": RECOVERY_STATE_TYPE,
        "release": RELEASE,
        "run_id": run_id,
        "context": context,
        "namespace": namespace,
        "namespace_uid": namespace_uid,
        "expected_namespace_labels": {
            "environment": "non-production",
            "lightyear.ai/ms66-run": run_id,
        },
        "source_image_lock_sha256": source_image_lock_sha256,
        "model_namespace": model_namespace,
        "model_policy_name": model_policy_name,
        "model_policy_uid": model_policy_uid,
        "phase": phase,
        "cleanup_required": cleanup_required,
        "credentials_persisted": False,
        "production_environment": False,
    }, key, signer)


def validate_recovery_state(state: Mapping[str, Any], key: str) -> list[str]:
    expected = {
        "schema_version", "state_type", "release", "run_id", "context", "namespace",
        "namespace_uid", "expected_namespace_labels", "source_image_lock_sha256",
        "model_namespace", "model_policy_name", "model_policy_uid", "phase",
        "cleanup_required", "credentials_persisted", "production_environment",
        "content_sha256", "signature",
    }
    errors: list[str] = []
    if set(state) != expected:
        errors.append("cloudbank-ms66-recovery-state-fields-invalid")
    if state.get("state_type") != RECOVERY_STATE_TYPE or state.get("release") != RELEASE \
            or not re.fullmatch(r"ms66-[a-z0-9-]{1,54}", str(state.get("run_id", ""))) \
            or not re.fullmatch(
                r"gke_[a-z0-9-]+_[a-z0-9-]+_[a-z0-9-]+", str(state.get("context", "")),
            ) \
            or any(not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", str(value))
                   for value in (
                       state.get("namespace", ""), state.get("model_namespace", ""),
                       state.get("model_policy_name", ""),
                   )) \
            or any(len(str(value)) > 63 for value in (
                state.get("namespace", ""), state.get("model_namespace", ""),
                state.get("model_policy_name", ""),
            )):
        errors.append("cloudbank-ms66-recovery-state-identity-invalid")
    if state.get("content_sha256") != content_hash(dict(state)) \
            or not key or not verify_signature(dict(state), key):
        errors.append("cloudbank-ms66-recovery-state-signature-invalid")
    signature = state.get("signature")
    if not isinstance(signature, Mapping) or set(signature) != {"algorithm", "signer", "value"} \
            or not str(signature.get("signer", "")).strip():
        errors.append("cloudbank-ms66-recovery-state-signature-invalid")
    labels = state.get("expected_namespace_labels") or {}
    if labels != {"environment": "non-production", "lightyear.ai/ms66-run": state.get("run_id")}:
        errors.append("cloudbank-ms66-recovery-state-labels-invalid")
    if not HEX_64.fullmatch(str(state.get("source_image_lock_sha256", ""))) \
            or state.get("credentials_persisted") is not False \
            or state.get("production_environment") is not False:
        errors.append("cloudbank-ms66-recovery-state-boundary-invalid")
    cleanup = state.get("cleanup_required")
    phase = state.get("phase")
    namespace_uid = state.get("namespace_uid")
    if phase not in RECOVERY_PHASES or type(cleanup) is not bool \
            or cleanup is not (phase not in {"planned", "restored"}) \
            or not _recovery_identity_is_valid(
                phase, namespace_uid, state.get("model_policy_uid"),
            ):
        errors.append("cloudbank-ms66-recovery-state-mutation-invalid")
    return sorted(set(errors))


def validate_governed_source_lock(lock: Mapping[str, Any], key: str) -> list[str]:
    errors = validate_source_image_lock(lock, key)
    if lock.get("lock_type") != SOURCE_IMAGE_LOCK_TYPE:
        errors.append("cloudbank-ms66-governed-source-lock-type-invalid")
    return sorted(set(errors))
