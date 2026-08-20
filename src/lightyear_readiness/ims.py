from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

from lightyear_common.io import write_json

from .cics_vsam import canonical_hash


SCHEMA_VERSION = "1.0"
PROGRAM = {
    "id": "CBPAUP0C",
    "mode": "BMP",
    "psb": "PSBPAUTB",
    "database": "DBPAUTP0",
    "pcb": "PAUTBPCB",
    "root_segment": "PAUTSUM0",
    "detail_segment": "PAUTDTL1",
}


def _sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha(value: object) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _candidate(project_root: Path) -> object:
    path = project_root / "factory/benchmarks/ims_expiry_candidate.py"
    spec = importlib.util.spec_from_file_location("factorydark_ims_readiness_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("IMS candidate cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fixture() -> list[dict[str, Any]]:
    return [
        {
            "account_id": "00000000001",
            "approved_count": 1,
            "declined_count": 1,
            "approved_amount": "40.00",
            "declined_amount": "25.00",
            "details": [
                {
                    "authorization_id": "APPROVED-OLD",
                    "inverted_auth_date": 79823,
                    "response_code": "00",
                    "approved_amount": "40.00",
                    "transaction_amount": "40.00",
                },
                {
                    "authorization_id": "DECLINED-NEW",
                    "inverted_auth_date": 79820,
                    "response_code": "05",
                    "approved_amount": "0.00",
                    "transaction_amount": "25.00",
                },
            ],
        },
        {
            "account_id": "00000000002",
            "approved_count": 1,
            "declined_count": 1,
            "approved_amount": "10.00",
            "declined_amount": "12.00",
            "details": [
                {
                    "authorization_id": "DECLINED-OLD",
                    "inverted_auth_date": 79824,
                    "response_code": "05",
                    "approved_amount": "0.00",
                    "transaction_amount": "12.00",
                }
            ],
        },
    ]


def local_capture(project_root: Path) -> dict[str, Any]:
    candidate = _candidate(project_root)
    input_payload = {
        "current_yyddd": 20181,
        "expiry_days": "05",
        "checkpoint_frequency": 1,
        "summaries": _fixture(),
    }
    output = candidate.purge_expired_authorizations(
        input_payload["summaries"],
        current_yyddd=input_payload["current_yyddd"],
        expiry_days=input_payload["expiry_days"],
        checkpoint_frequency=input_payload["checkpoint_frequency"],
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capture_type": "factorydark-ims-bmp-execution",
        "run_id": "local-cbpaup0c-reference",
        "source_system": "factorydark-local-semantic-candidate",
        "observed_at": "2022-07-18T00:00:00Z",
        "evidence_class": "local_observed",
        "program": PROGRAM,
        "input": input_payload,
        "output": output,
        "return_code": 0,
        "artifacts": [
            {"role": "candidate-source", "sha256": _file_sha(project_root / "factory/benchmarks/ims_expiry_candidate.py")},
            {"role": "input-fixture", "sha256": _json_sha(input_payload)},
            {"role": "output", "sha256": _json_sha(output)},
        ],
        "mainframe_identity": {},
        "operator_attestation": {"authorized": False, "reason": "local deterministic logical proof only"},
        "attestation_signature": None,
        "limitations": [
            "This capture does not schedule PSBPAUTB or execute CBPAUP0C in an IMS BMP region.",
            "IMS status handling, locking, logging, checkpoints, restart, EBCDIC and packed-decimal bytes remain unproven.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def capture_template() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capture_type": "factorydark-ims-bmp-execution",
        "run_id": "REPLACE-WITH-UNIQUE-RUN-ID",
        "source_system": "REPLACE-WITH-AUTHORIZED-ZOS-ALIAS",
        "observed_at": "REPLACE-WITH-UTC-TIMESTAMP",
        "evidence_class": "zos_observed",
        "program": PROGRAM,
        "input": {
            "current_yyddd": 20181,
            "expiry_days": "05",
            "checkpoint_frequency": 1,
            "summaries": "REPLACE-WITH-REDACTED-SYNTHETIC-FIXTURE-MANIFEST",
        },
        "output": {
            "normalized_result": "REPLACE-WITH-NORMALIZED-SEGMENT-AND-TRACE-RESULT",
            "before_digest": "0" * 64,
            "after_digest": "0" * 64,
        },
        "return_code": 0,
        "artifacts": [
            {"role": "jcl", "sha256": "0" * 64},
            {"role": "load-module", "sha256": "0" * 64},
            {"role": "psb", "sha256": "0" * 64},
            {"role": "dbd", "sha256": "0" * 64},
            {"role": "synthetic-before-image", "sha256": "0" * 64},
            {"role": "synthetic-after-image", "sha256": "0" * 64},
            {"role": "job-output", "sha256": "0" * 64},
            {"role": "ims-log-or-trace", "sha256": "0" * 64},
        ],
        "mainframe_identity": {
            "system_id": "REPLACE",
            "lpar": "REPLACE",
            "ims_region": "REPLACE",
            "job_id": "REPLACE",
            "step_name": "STEP01",
            "program": "CBPAUP0C",
            "psb": "PSBPAUTB",
            "database": "DBPAUTP0",
            "operator": "REPLACE",
        },
        "operator_attestation": {"authorized": False, "ticket": "REPLACE", "scope": "synthetic CBPAUP0C BMP proof"},
        "attestation_signature": None,
        "limitations": [],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def validate_capture(payload: dict[str, Any], key: str | None = None) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported IMS capture schema_version")
    if payload.get("capture_type") != "factorydark-ims-bmp-execution":
        errors.append("invalid IMS capture_type")
    if payload.get("evidence_class") not in {"local_observed", "zos_observed"}:
        errors.append("IMS evidence_class must be local_observed or zos_observed")
    for field in ("run_id", "source_system", "observed_at"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(f"IMS capture requires {field}")
    if payload.get("program") != PROGRAM:
        errors.append("IMS capture program identity is invalid")
    artifacts = payload.get("artifacts", [])
    if not artifacts or not all(item.get("role") and _sha(item.get("sha256")) for item in artifacts):
        errors.append("IMS capture artifacts require role and SHA-256")
    if payload.get("evidence_class") == "zos_observed":
        identity = payload.get("mainframe_identity", {})
        expected_identity = {
            "program": "CBPAUP0C",
            "psb": "PSBPAUTB",
            "database": "DBPAUTP0",
        }
        for field in ("system_id", "lpar", "ims_region", "job_id", "step_name", "operator"):
            if not isinstance(identity.get(field), str) or not identity[field].strip():
                errors.append(f"zos_observed IMS capture requires mainframe_identity.{field}")
        for field, value in expected_identity.items():
            if identity.get(field) != value:
                errors.append(f"zos_observed IMS capture mainframe_identity.{field} must be {value}")
        required_roles = {
            "jcl", "load-module", "psb", "dbd", "synthetic-before-image",
            "synthetic-after-image", "job-output", "ims-log-or-trace",
        }
        if not required_roles.issubset({item.get("role") for item in artifacts}):
            errors.append("zos_observed IMS capture is missing required build, data, or execution artifacts")
        if payload.get("operator_attestation", {}).get("authorized") is not True:
            errors.append("zos_observed IMS capture requires authorized operator attestation")
        signature = payload.get("attestation_signature")
        if not isinstance(signature, dict):
            errors.append("zos_observed IMS capture requires attestation signature")
        elif not key:
            errors.append("zos_observed IMS capture requires configured attestation key")
        else:
            unsigned_hash = canonical_hash(payload, {"content_sha256", "attestation_signature"})
            expected = hmac.new(key.encode(), unsigned_hash.encode("ascii"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature.get("value", ""), expected):
                errors.append("IMS attestation signature is invalid")
    if payload.get("content_sha256") != canonical_hash(payload, {"content_sha256"}):
        errors.append("IMS capture content_sha256 is invalid")
    return errors


def sign_capture(payload: dict[str, Any], key: str, key_id: str) -> dict[str, Any]:
    signed = dict(payload)
    signed["attestation_signature"] = None
    signed["content_sha256"] = ""
    unsigned_hash = canonical_hash(signed, {"content_sha256", "attestation_signature"})
    signed["attestation_signature"] = {
        "algorithm": "HMAC-SHA256",
        "key_id": key_id,
        "value": hmac.new(key.encode(), unsigned_hash.encode("ascii"), hashlib.sha256).hexdigest(),
    }
    signed["content_sha256"] = canonical_hash(signed, {"content_sha256"})
    return signed


def compare_captures(baseline: dict[str, Any], candidate: dict[str, Any], key: str | None = None) -> dict[str, Any]:
    baseline_errors = validate_capture(baseline, key)
    candidate_errors = validate_capture(candidate)
    differences = [
        {"field": field, "baseline": baseline.get(field), "candidate": candidate.get(field)}
        for field in ("program", "input", "output", "return_code")
        if baseline.get(field) != candidate.get(field)
    ]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "comparison_type": "factorydark-ims-bmp-differential",
        "baseline_sha256": baseline.get("content_sha256"),
        "candidate_sha256": candidate.get("content_sha256"),
        "baseline_evidence_class": baseline.get("evidence_class"),
        "candidate_evidence_class": candidate.get("evidence_class"),
        "validation_errors": {"baseline": baseline_errors, "candidate": candidate_errors},
        "differences": differences,
        "behavior_match": not baseline_errors and not candidate_errors and not differences,
        "mainframe_baseline": baseline.get("evidence_class") == "zos_observed",
    }
    payload["status"] = "passed" if payload["behavior_match"] else "failed"
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def issue_receipt(comparison: dict[str, Any], key: str | None = None, key_id: str = "unconfigured") -> dict[str, Any]:
    behavior_match = comparison.get("status") == "passed" and comparison.get("behavior_match") is True
    live = comparison.get("mainframe_baseline") is True
    gaps = []
    if not live:
        gaps.append("No authorized zos_observed CBPAUP0C BMP baseline is bound to this comparison.")
    if not key:
        gaps.append("No external IMS equivalence signing key was configured.")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": "factorydark-ims-readiness",
        "workload_id": "workload:carddemo-ims-expired-authorization-purge",
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
        "mainframe_equivalent": behavior_match and live and bool(key),
        "status": "passed" if behavior_match and live and key else "blocked",
        "unresolved_gaps": gaps,
        "signature": None,
    }
    unsigned_hash = canonical_hash(payload, {"content_sha256", "signature"})
    if key:
        payload["signature"] = {
            "algorithm": "HMAC-SHA256",
            "key_id": key_id,
            "value": hmac.new(key.encode(), unsigned_hash.encode("ascii"), hashlib.sha256).hexdigest(),
        }
    payload["content_sha256"] = canonical_hash(payload, {"content_sha256"})
    return payload


def validate_receipt(payload: dict[str, Any], key: str | None = None) -> list[str]:
    errors: list[str] = []
    if payload.get("receipt_type") != "factorydark-ims-readiness":
        errors.append("invalid IMS readiness receipt type")
    if payload.get("content_sha256") != canonical_hash(payload, {"content_sha256"}):
        errors.append("IMS readiness receipt content_sha256 is invalid")
    signature = payload.get("signature")
    if signature and key:
        unsigned = dict(payload)
        unsigned["signature"] = None
        unsigned_hash = canonical_hash(unsigned, {"content_sha256", "signature"})
        expected = hmac.new(key.encode(), unsigned_hash.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.get("value", ""), expected):
            errors.append("IMS readiness receipt signature is invalid")
    if payload.get("mainframe_equivalent") and (
        payload.get("status") != "passed"
        or payload.get("unresolved_gaps")
        or not signature
        or not payload.get("checks", {}).get("zos_observed_baseline")
    ):
        errors.append("IMS mainframe_equivalent receipt violates fail-closed policy")
    return errors


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FactoryDark IMS BMP readiness gate")
    commands = parser.add_subparsers(dest="command", required=True)
    local = commands.add_parser("local-capture")
    local.add_argument("--project-root", type=Path, default=Path("."))
    local.add_argument("--output", type=Path, required=True)
    template = commands.add_parser("capture-template")
    template.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate-capture")
    validate.add_argument("--capture", type=Path, required=True)
    attest = commands.add_parser("attest-capture")
    attest.add_argument("--capture", type=Path, required=True)
    attest.add_argument("--output", type=Path, required=True)
    attest.add_argument("--key-id", default="ims-evidence-custodian")
    compare = commands.add_parser("compare")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    issue = commands.add_parser("issue")
    issue.add_argument("--comparison", type=Path, required=True)
    issue.add_argument("--output", type=Path, required=True)
    issue.add_argument("--key-id", default="ims-independent-verifier")
    receipt = commands.add_parser("validate-receipt")
    receipt.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    attest_key = os.environ.get("LIGHTYEAR_IMS_ATTESTATION_KEY")
    equivalence_key = os.environ.get("LIGHTYEAR_IMS_EQUIVALENCE_SIGNING_KEY")
    if args.command == "local-capture":
        payload = local_capture(args.project_root.resolve())
    elif args.command == "capture-template":
        payload = capture_template()
    elif args.command == "validate-capture":
        errors = validate_capture(_load(args.capture), attest_key)
        print(json.dumps({"errors": errors, "status": "passed" if not errors else "failed"}, indent=2))
        return 0 if not errors else 1
    elif args.command == "attest-capture":
        if not attest_key:
            raise SystemExit("LIGHTYEAR_IMS_ATTESTATION_KEY is required")
        payload = sign_capture(_load(args.capture), attest_key, args.key_id)
    elif args.command == "compare":
        payload = compare_captures(_load(args.baseline), _load(args.candidate), attest_key)
    elif args.command == "issue":
        payload = issue_receipt(_load(args.comparison), equivalence_key, args.key_id)
    elif args.command == "validate-receipt":
        errors = validate_receipt(_load(args.receipt), equivalence_key)
        print(json.dumps({"errors": errors, "status": "passed" if not errors else "failed"}, indent=2))
        return 0 if not errors else 1
    else:
        return 2
    _write(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.command == "compare":
        return 0 if payload["status"] == "passed" else 1
    if args.command == "issue":
        return 0 if payload["development_ready"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
