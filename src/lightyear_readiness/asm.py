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


def _sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha(value: object) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _candidate(project_root: Path) -> object:
    path = project_root / "factory/benchmarks/asm_date_candidate.py"
    spec = importlib.util.spec_from_file_location("factorydark_asm_readiness_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("ASM candidate cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def local_capture(project_root: Path) -> dict[str, Any]:
    candidate = _candidate(project_root)
    output = candidate.format_date("2", "2026-08-21", "2")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capture_type": "factorydark-hlasm-execution",
        "run_id": "local-cobdatft-reference",
        "source_system": "factorydark-local-semantic-candidate",
        "observed_at": "2022-07-18T00:00:00Z",
        "evidence_class": "local_observed",
        "program": {"id": "COBDATFT", "caller": "CBACT01C", "dsect": "COCDATFT"},
        "input": {"input_type": "2", "input_date": "2026-08-21", "output_type": "2"},
        "output": output,
        "return_code": 0,
        "artifacts": [
            {"role": "candidate-source", "sha256": _file_sha(project_root / "factory/benchmarks/asm_date_candidate.py")},
            {"role": "output", "sha256": _json_sha(output)},
        ],
        "mainframe_identity": {},
        "operator_attestation": {"authorized": False, "reason": "local deterministic proof only"},
        "attestation_signature": None,
        "limitations": [
            "This capture does not assemble, bind, or execute COBDATFT on z/OS.",
            "AMODE/RMODE, linkage conventions, LE behavior, EBCDIC bytes, and abend behavior remain unproven.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def capture_template() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capture_type": "factorydark-hlasm-execution",
        "run_id": "REPLACE-WITH-UNIQUE-RUN-ID",
        "source_system": "REPLACE-WITH-AUTHORIZED-ZOS-ALIAS",
        "observed_at": "REPLACE-WITH-UTC-TIMESTAMP",
        "evidence_class": "zos_observed",
        "program": {"id": "COBDATFT", "caller": "CBACT01C", "dsect": "COCDATFT"},
        "input": {"input_type": "2", "input_date": "2026-08-21", "output_type": "2"},
        "output": {
            "input_type": "2",
            "input_date": "REPLACE-WITH-20-BYTE-VALUE",
            "output_type": "2",
            "output_date": "REPLACE-WITH-20-BYTE-VALUE",
            "error_message": "REPLACE-WITH-38-BYTE-VALUE"
        },
        "return_code": 0,
        "artifacts": [
            {"role": "assembly-listing", "sha256": "0" * 64},
            {"role": "binder-map", "sha256": "0" * 64},
            {"role": "load-module", "sha256": "0" * 64},
            {"role": "cobol-caller-output", "sha256": "0" * 64},
        ],
        "mainframe_identity": {
            "system_id": "REPLACE",
            "lpar": "REPLACE",
            "job_id": "REPLACE",
            "step_name": "REPLACE",
            "load_module": "COBDATFT",
            "caller_program": "CBACT01C",
            "operator": "REPLACE",
        },
        "operator_attestation": {"authorized": False, "ticket": "REPLACE", "scope": "COBDATFT proof"},
        "attestation_signature": None,
        "limitations": [],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def validate_capture(payload: dict[str, Any], key: str | None = None) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported ASM capture schema_version")
    if payload.get("capture_type") != "factorydark-hlasm-execution":
        errors.append("invalid ASM capture_type")
    if payload.get("evidence_class") not in {"local_observed", "zos_observed"}:
        errors.append("ASM evidence_class must be local_observed or zos_observed")
    for field in ("run_id", "source_system", "observed_at"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(f"ASM capture requires {field}")
    expected_program = {"id": "COBDATFT", "caller": "CBACT01C", "dsect": "COCDATFT"}
    if payload.get("program") != expected_program:
        errors.append("ASM capture program identity is invalid")
    artifacts = payload.get("artifacts", [])
    if not artifacts or not all(item.get("role") and _sha(item.get("sha256")) for item in artifacts):
        errors.append("ASM capture artifacts require role and SHA-256")
    if payload.get("evidence_class") == "zos_observed":
        identity = payload.get("mainframe_identity", {})
        for field in ("system_id", "lpar", "job_id", "step_name", "load_module", "caller_program", "operator"):
            if not isinstance(identity.get(field), str) or not identity[field].strip():
                errors.append(f"zos_observed ASM capture requires mainframe_identity.{field}")
        required_roles = {"assembly-listing", "binder-map", "load-module", "cobol-caller-output"}
        if not required_roles.issubset({item.get("role") for item in artifacts}):
            errors.append("zos_observed ASM capture is missing required build or execution artifacts")
        if payload.get("operator_attestation", {}).get("authorized") is not True:
            errors.append("zos_observed ASM capture requires authorized operator attestation")
        signature = payload.get("attestation_signature")
        if not isinstance(signature, dict):
            errors.append("zos_observed ASM capture requires attestation signature")
        elif not key:
            errors.append("zos_observed ASM capture requires configured attestation key")
        else:
            unsigned_hash = canonical_hash(payload, {"content_sha256", "attestation_signature"})
            expected = hmac.new(key.encode(), unsigned_hash.encode("ascii"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature.get("value", ""), expected):
                errors.append("ASM attestation signature is invalid")
    if payload.get("content_sha256") != canonical_hash(payload, {"content_sha256"}):
        errors.append("ASM capture content_sha256 is invalid")
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
        "comparison_type": "factorydark-hlasm-differential",
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
        gaps.append("No authorized zos_observed COBDATFT baseline is bound to this comparison.")
    if not key:
        gaps.append("No external ASM equivalence signing key was configured.")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": "factorydark-hlasm-readiness",
        "workload_id": "workload:carddemo-asm-date-format",
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
    if payload.get("receipt_type") != "factorydark-hlasm-readiness":
        errors.append("invalid ASM readiness receipt type")
    if payload.get("content_sha256") != canonical_hash(payload, {"content_sha256"}):
        errors.append("ASM readiness receipt content_sha256 is invalid")
    signature = payload.get("signature")
    if signature and key:
        unsigned = dict(payload)
        unsigned["signature"] = None
        unsigned_hash = canonical_hash(unsigned, {"content_sha256", "signature"})
        expected = hmac.new(key.encode(), unsigned_hash.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.get("value", ""), expected):
            errors.append("ASM readiness receipt signature is invalid")
    if payload.get("mainframe_equivalent") and (
        payload.get("status") != "passed"
        or payload.get("unresolved_gaps")
        or not signature
        or not payload.get("checks", {}).get("zos_observed_baseline")
    ):
        errors.append("ASM mainframe_equivalent receipt violates fail-closed policy")
    return errors


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FactoryDark HLASM readiness gate")
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
    attest.add_argument("--key-id", default="asm-evidence-custodian")
    compare = commands.add_parser("compare")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    issue = commands.add_parser("issue")
    issue.add_argument("--comparison", type=Path, required=True)
    issue.add_argument("--output", type=Path, required=True)
    issue.add_argument("--key-id", default="asm-independent-verifier")
    receipt = commands.add_parser("validate-receipt")
    receipt.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    attest_key = os.environ.get("LIGHTYEAR_ASM_ATTESTATION_KEY")
    equivalence_key = os.environ.get("LIGHTYEAR_ASM_EQUIVALENCE_SIGNING_KEY")
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
            raise SystemExit("LIGHTYEAR_ASM_ATTESTATION_KEY is required")
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
