#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lightyear_data.cloudbank_transaction_wave import (
    RECEIPT_NAME,
    admit_transaction_wave,
    validate_admission_receipt,
    validate_artifacts,
    validate_source,
    write_artifacts,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Build, verify, or admit the CloudBank whole-application transaction wave"
    )
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", type=Path, default=Path("."))
    source = commands.add_parser("verify-source")
    source.add_argument("--source-root", type=Path, required=True)
    admit = commands.add_parser("admit")
    admit.add_argument("--project-root", type=Path, default=Path("."))
    admit.add_argument("--source-root", type=Path, required=True)
    admit.add_argument("--ms57-receipt", type=Path, required=True)
    admit.add_argument("--output", type=Path, required=True)
    admit.add_argument("--signer", required=True)
    receipt = commands.add_parser("verify-receipt")
    receipt.add_argument("--project-root", type=Path, default=Path("."))
    receipt.add_argument("--receipt", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", "")
    if args.command in {"build", "verify"}:
        project_root = args.project_root.resolve()
        if args.command == "build":
            write_artifacts(project_root)
        errors = validate_artifacts(project_root)
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    elif args.command == "verify-source":
        errors = validate_source(args.source_root.resolve())
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    elif args.command == "admit":
        ms57_receipt = json.loads(args.ms57_receipt.read_text(encoding="utf-8"))
        receipt = admit_transaction_wave(
            args.project_root.resolve(),
            args.source_root.resolve(),
            ms57_receipt,
            args.output.resolve(),
            key,
            args.signer,
        )
        result = {
            "status": "passed",
            "output": str(args.output),
            "receipt": RECEIPT_NAME,
            "content_sha256": receipt["content_sha256"],
        }
    else:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        errors = validate_admission_receipt(receipt, key, args.project_root.resolve())
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
