from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cics_vsam import (
    attestation_key_from_environment,
    capture_template,
    compare_captures,
    issue_receipt,
    local_capture,
    sign_capture,
    signing_key_from_environment,
    validate_capture,
    validate_receipt,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FactoryDark CICS/VSAM readiness gate")
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
    attest.add_argument("--key-id", default="mainframe-evidence-custodian")
    compare = commands.add_parser("compare")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    issue = commands.add_parser("issue")
    issue.add_argument("--comparison", type=Path, required=True)
    issue.add_argument("--output", type=Path, required=True)
    issue.add_argument("--key-id", default="operator-configured")
    receipt = commands.add_parser("validate-receipt")
    receipt.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "local-capture":
        payload = local_capture(args.project_root.resolve())
        _write(args.output, payload)
        print(json.dumps({"status": "passed", "output": str(args.output), "content_sha256": payload["content_sha256"]}, indent=2))
        return 0
    if args.command == "capture-template":
        _write(args.output, capture_template())
        print(json.dumps({"status": "passed", "output": str(args.output)}, indent=2))
        return 0
    if args.command == "validate-capture":
        errors = validate_capture(_load(args.capture), attestation_key_from_environment())
        print(json.dumps({"status": "passed" if not errors else "failed", "errors": errors}, indent=2))
        return 0 if not errors else 1
    if args.command == "attest-capture":
        key = attestation_key_from_environment()
        if not key:
            raise SystemExit("LIGHTYEAR_MAINFRAME_ATTESTATION_KEY is required")
        payload = sign_capture(_load(args.capture), key, args.key_id)
        errors = validate_capture(payload, key)
        if errors:
            print(json.dumps({"status": "failed", "errors": errors}, indent=2))
            return 1
        _write(args.output, payload)
        print(json.dumps({"status": "passed", "output": str(args.output), "content_sha256": payload["content_sha256"]}, indent=2))
        return 0
    if args.command == "compare":
        payload = compare_captures(
            _load(args.baseline), _load(args.candidate), attestation_key_from_environment()
        )
        _write(args.output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["status"] == "passed" else 1
    if args.command == "issue":
        payload = issue_receipt(_load(args.comparison), signing_key=signing_key_from_environment(), signing_key_id=args.key_id)
        _write(args.output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["development_ready"] else 1
    if args.command == "validate-receipt":
        errors = validate_receipt(_load(args.receipt), signing_key_from_environment())
        print(json.dumps({"status": "passed" if not errors else "failed", "errors": errors}, indent=2))
        return 0 if not errors else 1
    return 2
