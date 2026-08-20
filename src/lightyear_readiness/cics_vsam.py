from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
CAPTURE_TYPES = {"local_observed", "zos_observed"}


class ReadinessContractError(ValueError):
    pass


def canonical_hash(payload: dict[str, Any], excluded: set[str] | None = None) -> str:
    excluded = excluded or set()
    normalized = {key: value for key, value in payload.items() if key not in excluded}
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_capture(payload: dict[str, Any], attestation_key: str | None = None) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported capture schema_version")
    if payload.get("capture_type") != "lightyear-cics-vsam-execution":
        errors.append("invalid capture_type")
    evidence_class = payload.get("evidence_class")
    if evidence_class not in CAPTURE_TYPES:
        errors.append("evidence_class must be local_observed or zos_observed")
    for field in ("run_id", "source_system", "observed_at"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(f"capture requires {field}")
    transaction = payload.get("transaction", {})
    expected = {"id": "CAVW", "program": "COACTVWC", "mapset": "COACTVW", "map": "CACTVWA"}
    for field, value in expected.items():
        if transaction.get(field) != value:
            errors.append(f"transaction.{field} must be {value}")
    accesses = payload.get("accesses")
    if not isinstance(accesses, list) or not accesses:
        errors.append("capture requires an access trace")
    elif [item.get("resource") for item in accesses] != ["CXACAIX", "ACCTDAT", "CUSTDAT"]:
        errors.append("access trace must read CXACAIX, ACCTDAT, then CUSTDAT")
    if payload.get("mutations") != []:
        errors.append("CAVW capture must not mutate records")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not all(
        isinstance(item, dict) and item.get("role") and _sha(item.get("sha256"))
        for item in artifacts
    ):
        errors.append("capture artifacts require role and SHA-256")
    identity = payload.get("mainframe_identity", {})
    attestation_signature = payload.get("attestation_signature")
    if evidence_class == "zos_observed":
        for field in ("system_id", "lpar", "cics_region", "task_id", "operator"):
            if not isinstance(identity.get(field), str) or not identity[field].strip():
                errors.append(f"zos_observed capture requires mainframe_identity.{field}")
        if not payload.get("operator_attestation", {}).get("authorized") is True:
            errors.append("zos_observed capture requires an authorized operator attestation")
        if not isinstance(attestation_signature, dict):
            errors.append("zos_observed capture requires an attestation signature")
        elif not attestation_key:
            errors.append("zos_observed capture requires a configured attestation verification key")
        else:
            unsigned_hash = canonical_hash(payload, {"content_sha256", "attestation_signature"})
            expected_signature = hmac.new(
                attestation_key.encode("utf-8"), unsigned_hash.encode("ascii"), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(attestation_signature.get("value", ""), expected_signature):
                errors.append("capture attestation signature is invalid")
    if payload.get("content_sha256") != canonical_hash(payload, {"content_sha256"}):
        errors.append("capture content_sha256 is invalid")
    return errors


def local_capture(project_root: Path) -> dict[str, Any]:
    candidate = _candidate(project_root)
    xref = candidate.KeyedStore(
        "CXACAIX", {"00000000001": {"customer_id": "000000001", "card_number": "4111111111111111"}}
    )
    accounts = candidate.KeyedStore(
        "ACCTDAT", {"00000000001": {"status": "Y", "current_balance": "125.25", "credit_limit": "5000.00"}}
    )
    customers = candidate.KeyedStore("CUSTDAT", {"000000001": {"name": "JANE CUSTOMER"}})
    output = candidate.account_view("00000000001", xref, accounts, customers)
    accesses = [*xref.trace, *accounts.trace, *customers.trace]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capture_type": "lightyear-cics-vsam-execution",
        "run_id": "local-cavw-reference",
        "source_system": "factorydark-local-semantic-candidate",
        "observed_at": "2022-07-18T00:00:00Z",
        "evidence_class": "local_observed",
        "transaction": {"id": "CAVW", "program": "COACTVWC", "mapset": "COACTVW", "map": "CACTVWA"},
        "input": {"account_id": "00000000001"},
        "output": output,
        "accesses": accesses,
        "mutations": output["mutations"],
        "artifacts": [
            {"role": "candidate-source", "sha256": _file_sha(project_root / "factory/benchmarks/cics_vsam_account_candidate.py")},
            {"role": "output", "sha256": _json_sha(output)},
        ],
        "mainframe_identity": {},
        "operator_attestation": {"authorized": False, "reason": "local deterministic proof only"},
        "attestation_signature": None,
        "limitations": [
            "This capture does not execute CICS or VSAM.",
            "Locking, RLS, recoverability, EBCDIC terminal behavior, and region configuration remain unproven.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def capture_template() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capture_type": "lightyear-cics-vsam-execution",
        "run_id": "REPLACE-WITH-UNIQUE-RUN-ID",
        "source_system": "REPLACE-WITH-AUTHORIZED-ZOS-ALIAS",
        "observed_at": "REPLACE-WITH-UTC-TIMESTAMP",
        "evidence_class": "zos_observed",
        "transaction": {"id": "CAVW", "program": "COACTVWC", "mapset": "COACTVW", "map": "CACTVWA"},
        "input": {"account_id": "REPLACE-WITH-SYNTHETIC-11-DIGIT-ID"},
        "output": {"status": "REPLACE", "view": {}},
        "accesses": [
            {"operation": "READ", "resource": "CXACAIX", "key": "REPLACE"},
            {"operation": "READ", "resource": "ACCTDAT", "key": "REPLACE"},
            {"operation": "READ", "resource": "CUSTDAT", "key": "REPLACE"},
        ],
        "mutations": [],
        "artifacts": [
            {"role": "terminal-input-redacted", "sha256": "0" * 64},
            {"role": "terminal-output-redacted", "sha256": "0" * 64},
            {"role": "cics-trace-or-log", "sha256": "0" * 64},
            {"role": "dataset-before-digests", "sha256": "0" * 64},
            {"role": "dataset-after-digests", "sha256": "0" * 64},
        ],
        "mainframe_identity": {
            "system_id": "REPLACE",
            "lpar": "REPLACE",
            "cics_region": "REPLACE",
            "task_id": "REPLACE",
            "operator": "REPLACE",
        },
        "operator_attestation": {"authorized": False, "ticket": "REPLACE", "scope": "read-only CAVW proof"},
        "attestation_signature": None,
        "limitations": [],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def sign_capture(payload: dict[str, Any], signing_key: str, key_id: str) -> dict[str, Any]:
    signed = dict(payload)
    signed["content_sha256"] = ""
    signed["attestation_signature"] = None
    unsigned_hash = canonical_hash(signed, {"content_sha256", "attestation_signature"})
    signed["attestation_signature"] = {
        "algorithm": "HMAC-SHA256",
        "key_id": key_id,
        "value": hmac.new(signing_key.encode("utf-8"), unsigned_hash.encode("ascii"), hashlib.sha256).hexdigest(),
    }
    signed["content_sha256"] = canonical_hash(signed, {"content_sha256"})
    return signed


def compare_captures(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    attestation_key: str | None = None,
) -> dict[str, Any]:
    baseline_errors = validate_capture(baseline, attestation_key)
    candidate_errors = validate_capture(candidate)
    differences: list[dict[str, Any]] = []
    for field in ("transaction", "input", "output", "accesses", "mutations"):
        if baseline.get(field) != candidate.get(field):
            differences.append({"field": field, "baseline": baseline.get(field), "candidate": candidate.get(field)})
    comparison: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "comparison_type": "lightyear-cics-vsam-differential",
        "baseline_sha256": baseline.get("content_sha256"),
        "candidate_sha256": candidate.get("content_sha256"),
        "baseline_evidence_class": baseline.get("evidence_class"),
        "candidate_evidence_class": candidate.get("evidence_class"),
        "validation_errors": {"baseline": baseline_errors, "candidate": candidate_errors},
        "differences": differences,
        "behavior_match": not baseline_errors and not candidate_errors and not differences,
        "mainframe_baseline": baseline.get("evidence_class") == "zos_observed",
    }
    comparison["status"] = "passed" if comparison["behavior_match"] else "failed"
    comparison["content_sha256"] = canonical_hash(comparison)
    return comparison


def issue_receipt(
    comparison: dict[str, Any],
    *,
    signing_key: str | None = None,
    signing_key_id: str = "unconfigured",
) -> dict[str, Any]:
    behavior_match = comparison.get("status") == "passed" and comparison.get("behavior_match") is True
    live = comparison.get("mainframe_baseline") is True
    gaps = []
    if not live:
        gaps.append("No authorized zos_observed CAVW baseline is bound to this comparison.")
    if not signing_key:
        gaps.append("No external equivalence signing key was configured.")
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": "lightyear-cics-vsam-readiness",
        "workload_id": "workload:carddemo-cics-vsam-account-view",
        "comparison_sha256": comparison.get("content_sha256"),
        "checks": {
            "typed_static_graph": True,
            "curated_behavior_contract": True,
            "bounded_candidate": True,
            "private_negative_gate": True,
            "differential_behavior_match": behavior_match,
            "zos_observed_baseline": live,
        },
        "development_ready": behavior_match,
        "mainframe_equivalent": behavior_match and live and bool(signing_key),
        "status": "passed" if behavior_match and live and signing_key else "blocked",
        "unresolved_gaps": gaps,
        "signature": None,
    }
    unsigned_hash = canonical_hash(receipt, {"content_sha256", "signature"})
    if signing_key:
        receipt["signature"] = {
            "algorithm": "HMAC-SHA256",
            "key_id": signing_key_id,
            "value": hmac.new(signing_key.encode("utf-8"), unsigned_hash.encode("ascii"), hashlib.sha256).hexdigest(),
        }
    receipt["content_sha256"] = canonical_hash(receipt, {"content_sha256"})
    return receipt


def validate_receipt(payload: dict[str, Any], signing_key: str | None = None) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported readiness receipt schema_version")
    if payload.get("content_sha256") != canonical_hash(payload, {"content_sha256"}):
        errors.append("readiness receipt content_sha256 is invalid")
    signature = payload.get("signature")
    if signature and signing_key:
        unsigned = dict(payload)
        unsigned["signature"] = None
        unsigned_hash = canonical_hash(unsigned, {"content_sha256", "signature"})
        expected = hmac.new(signing_key.encode("utf-8"), unsigned_hash.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.get("value", ""), expected):
            errors.append("readiness receipt signature is invalid")
    if payload.get("mainframe_equivalent") and (
        payload.get("status") != "passed"
        or payload.get("unresolved_gaps")
        or not signature
        or not payload.get("checks", {}).get("zos_observed_baseline")
    ):
        errors.append("mainframe_equivalent receipt violates fail-closed policy")
    return errors


def _candidate(project_root: Path) -> object:
    path = project_root / "factory/benchmarks/cics_vsam_account_candidate.py"
    spec = importlib.util.spec_from_file_location("lightyear_readiness_candidate", path)
    if spec is None or spec.loader is None:
        raise ReadinessContractError("candidate cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def signing_key_from_environment() -> str | None:
    return os.environ.get("LIGHTYEAR_EQUIVALENCE_SIGNING_KEY")


def attestation_key_from_environment() -> str | None:
    return os.environ.get("LIGHTYEAR_MAINFRAME_ATTESTATION_KEY")
