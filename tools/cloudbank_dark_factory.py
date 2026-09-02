#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lightyear_common.io import write_json
from lightyear_data.cloudbank_dark_factory import (
    OUTPUT_ROOT,
    build_artifacts,
    execute_dark_factory,
    validate_artifacts,
    validate_factory_receipt,
    validate_source_patch_inputs,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="CloudBank customer first dark factory run")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", type=Path, default=Path("."))
    source = commands.add_parser("verify-source")
    source.add_argument("--source-root", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--project-root", type=Path, default=Path("."))
    run.add_argument("--source-root", type=Path, required=True)
    run.add_argument("--oracle-receipt", type=Path, required=True)
    run.add_argument("--postgresql-receipt", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--signer", required=True)
    run.add_argument("--run-id")
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
            for name, payload in build_artifacts(project_root).items():
                write_json(project_root / OUTPUT_ROOT / name, payload)
        errors = validate_artifacts(project_root)
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    elif args.command == "verify-source":
        errors = validate_source_patch_inputs(args.source_root.resolve())
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    elif args.command == "run":
        project_root = args.project_root.resolve()
        oracle_receipt = json.loads(args.oracle_receipt.read_text(encoding="utf-8"))
        postgres_receipt = json.loads(args.postgresql_receipt.read_text(encoding="utf-8"))
        receipt = execute_dark_factory(
            project_root,
            args.source_root.resolve(),
            oracle_receipt,
            postgres_receipt,
            args.output_root.resolve(),
            key,
            args.signer,
            args.run_id,
        )
        result = {
            "status": "passed",
            "output": str(args.output_root / "cloudbank-customer-dark-factory.receipt.json"),
            "content_sha256": receipt["content_sha256"],
            "run_id": receipt["run_id"],
        }
    else:
        project_root = args.project_root.resolve()
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        errors = validate_factory_receipt(receipt, key, project_root)
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
