#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lightyear_data.cloudbank_checks_messaging import (
    FAILURE_NAME,
    RECEIPT_NAME,
    execute_checks_messaging,
    materialize_target,
    validate_artifacts,
    validate_checks_source,
    validate_execution_receipt,
    write_artifacts,
)
def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Build, verify, materialize, or run CloudBank Checks messaging")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", type=Path, default=Path("."))
    source = commands.add_parser("verify-source")
    source.add_argument("--source-root", type=Path, required=True)
    materialize = commands.add_parser("materialize")
    materialize.add_argument("--project-root", type=Path, default=Path("."))
    materialize.add_argument("--source-root", type=Path, required=True)
    materialize.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--project-root", type=Path, default=Path("."))
    execute.add_argument("--source-root", type=Path, required=True)
    execute.add_argument("--ms62-receipt", type=Path, required=True)
    execute.add_argument("--output-root", type=Path, required=True)
    execute.add_argument("--signer", required=True)
    execute.add_argument("--run-id")
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
        errors = validate_checks_source(args.source_root.resolve())
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    elif args.command == "materialize":
        workspace = materialize_target(args.project_root.resolve(), args.source_root.resolve(), args.output.resolve())
        result = {"status": "passed", "workspace": str(workspace)}
    elif args.command == "run":
        receipt = json.loads(args.ms62_receipt.read_text(encoding="utf-8"))
        try:
            output = execute_checks_messaging(
                args.project_root.resolve(), args.source_root.resolve(), receipt,
                args.output_root.resolve(), key, args.signer, args.run_id,
                progress=lambda message: print(f"[MS63] {message}", flush=True),
            )
            result = {"status": "passed", "output": str(args.output_root / RECEIPT_NAME),
                      "run_id": output["run_id"], "content_sha256": output["content_sha256"]}
        except ValueError as exception:
            result = {"status": "failed", "error": str(exception),
                      "diagnostics": str(args.output_root / FAILURE_NAME)}
    else:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        errors = validate_execution_receipt(receipt, key, args.project_root.resolve())
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
