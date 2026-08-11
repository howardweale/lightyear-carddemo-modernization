from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lightyear_factory.contracts import WorkOrder, write_json

from .admission import AdmissionNonceStore, sign_work_order, verify_work_order
from .conformance import build_conformance_receipt
from .backend import OCIContainerBackend
from .contracts import ExecutionPolicy, canonical_hash
from .evidence import normalize_execution_evidence


DEFAULT_POLICY = Path("factory/execution/policy.json")
DEFAULT_RECEIPT = Path("factory/execution/conformance.receipt.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR hardened execution plane")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Build deterministic policy conformance receipt")
    build.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    build.add_argument("--output", type=Path, default=DEFAULT_RECEIPT)
    validate = commands.add_parser("validate", help="Validate canonical conformance receipt")
    validate.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    validate.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    validate_evidence = commands.add_parser(
        "validate-evidence", help="Validate and classify conformance, probe, or factory evidence"
    )
    validate_evidence.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    validate_evidence.add_argument("--receipt", type=Path, required=True)
    sign = commands.add_parser("sign-work-order", help="Sign a bounded work order for admission")
    sign.add_argument("--work-order", type=Path, required=True)
    sign.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    sign.add_argument("--output", type=Path, required=True)
    sign.add_argument("--issuer", required=True)
    sign.add_argument("--key-id", required=True)
    sign.add_argument("--ttl-seconds", type=int, default=900)
    verify = commands.add_parser("verify-work-order", help="Verify and consume a signed work order")
    verify.add_argument("--envelope", type=Path, required=True)
    verify.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    verify.add_argument("--nonce-ledger", type=Path, required=True)
    probe = commands.add_parser("probe", help="Run a live Docker or Podman isolation probe")
    probe.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    probe.add_argument("--runtime", choices=["docker", "podman"], required=True)
    probe.add_argument("--workspace", type=Path, default=Path("."))
    probe.add_argument("--output", type=Path, default=Path("work/hardened-execution-probe/receipt.json"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    policy = ExecutionPolicy.load(args.policy)
    if args.command == "build":
        receipt = build_conformance_receipt(policy)
        write_json(receipt, args.output)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if receipt["status"] == "passed" else 1
    if args.command == "validate":
        expected = build_conformance_receipt(policy)
        actual = json.loads(args.receipt.read_text(encoding="utf-8"))
        matches = actual == expected
        print(json.dumps({
            "status": "passed" if matches else "failed",
            "expected_content_sha256": expected["content_sha256"],
            "actual_content_sha256": actual.get("content_sha256"),
        }, indent=2, sort_keys=True))
        return 0 if matches else 1
    if args.command == "validate-evidence":
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        normalized = normalize_execution_evidence(receipt)
        print(json.dumps(normalized, indent=2, sort_keys=True))
        return 0
    if args.command == "probe":
        marker = "LIGHTYEAR_HARDENED_PROBE_OK"
        result = OCIContainerBackend(policy, args.runtime, execute=True).execute(
            ("python3", "-c", f"print('{marker}')"),
            args.workspace,
            {"LIGHTYEAR_NETWORK_POLICY": "deny"},
            120,
        )
        runtime_ready = (
            result.exit_code == 0
            and not result.timed_out
            and result.evidence.get("enforced") is True
            and marker.encode("ascii") in result.stdout
        )
        receipt = {
            "schema_version": "1.0",
            "receipt_type": "lightyear-live-execution-probe",
            "status": "passed" if runtime_ready else "failed",
            "assurance": "enforced" if runtime_ready else "failed",
            "runtime_ready": runtime_ready,
            "production_ready": False,
            "execution_policy_sha256": policy.content_sha256,
            "runtime": args.runtime,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "output_sha256": hashlib.sha256(result.stdout + b"\0" + result.stderr).hexdigest(),
            "execution": result.evidence,
            "gaps": (
                ["signed-factory-work-order-not-observed"]
                if runtime_ready
                else [
                    "container-runtime-enforcement-probe-failed",
                    "signed-factory-work-order-not-observed",
                ]
            ),
            "limitations": [
                "This probe proves the OCI boundary, not signed factory-work-order execution."
            ],
        }
        receipt["content_sha256"] = canonical_hash(receipt)
        write_json(receipt, args.output)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if runtime_ready else 1
    key = os.environ.get("LIGHTYEAR_WORK_ORDER_SIGNING_KEY", "").encode("utf-8")
    if args.command == "sign-work-order":
        issued = datetime.now(timezone.utc)
        expires = issued + timedelta(seconds=args.ttl_seconds)
        envelope = sign_work_order(
            WorkOrder.load(args.work_order), policy, args.issuer, args.key_id, key,
            issued.isoformat().replace("+00:00", "Z"),
            expires.isoformat().replace("+00:00", "Z"),
            "nonce-" + os.urandom(16).hex(),
        )
        write_json(envelope, args.output)
        print(json.dumps({
            "status": "passed", "output": str(args.output),
            "content_sha256": envelope["content_sha256"],
            "expires_at": envelope["expires_at"],
        }, indent=2, sort_keys=True))
        return 0
    envelope = json.loads(args.envelope.read_text(encoding="utf-8"))
    key_id = envelope.get("signature", {}).get("key_id", "")
    _, receipt = verify_work_order(
        envelope, policy, {key_id: key},
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        AdmissionNonceStore(args.nonce_ledger),
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
