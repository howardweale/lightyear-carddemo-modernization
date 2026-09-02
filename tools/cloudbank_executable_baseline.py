#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lightyear_common.io import write_json
from lightyear_data.cloudbank_baseline import (
    OUTPUT_ROOT,
    build_artifacts,
    execute_oracle_runtime,
    execute_source_build,
    validate_artifacts,
    validate_execution_receipt,
    validate_source_checkout,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="CloudBank executable source baseline")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", type=Path, default=Path("."))
    source = commands.add_parser("verify-source")
    source.add_argument("--source-root", type=Path, required=True)
    build = commands.add_parser("source-build")
    build.add_argument("--source-root", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--signer", required=True)
    native = commands.add_parser("oracle-runtime")
    native.add_argument("--source-root", type=Path, required=True)
    native.add_argument("--build-receipt", type=Path, required=True)
    native.add_argument("--oracle-image-id-sha256", required=True)
    native.add_argument("--output", type=Path, required=True)
    native.add_argument("--signer", required=True)
    receipt = commands.add_parser("verify-receipt")
    receipt.add_argument("--receipt", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result: dict[str, object]
    if args.command in {"build", "verify"}:
        project_root = args.project_root.resolve()
        if args.command == "build":
            output = project_root / OUTPUT_ROOT
            for name, payload in build_artifacts().items():
                write_json(output / name, payload)
        errors = validate_artifacts(project_root)
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    elif args.command == "verify-source":
        errors = validate_source_checkout(args.source_root.resolve())
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    elif args.command == "source-build":
        receipt = execute_source_build(
            args.source_root.resolve(),
            os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", ""),
            args.signer,
        )
        write_json(args.output, receipt)
        result = {"status": "passed", "output": str(args.output), "content_sha256": receipt["content_sha256"]}
    elif args.command == "oracle-runtime":
        build_receipt = json.loads(args.build_receipt.read_text(encoding="utf-8"))
        receipt = execute_oracle_runtime(
            args.source_root.resolve(),
            build_receipt,
            args.oracle_image_id_sha256,
            os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", ""),
            args.signer,
        )
        write_json(args.output, receipt)
        result = {"status": "passed", "output": str(args.output), "content_sha256": receipt["content_sha256"]}
    else:
        payload = json.loads(args.receipt.read_text(encoding="utf-8"))
        errors = validate_execution_receipt(
            payload, os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", "")
        )
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
