#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lightyear_common.io import write_json
from lightyear_data.cloudbank_platform_qualification import (
    FAILURE_NAME,
    PREFLIGHT_NAME,
    RECEIPT_NAME,
    execute_qualification,
    preflight_platform,
    render_gke_addons,
    validate_artifacts,
    validate_execution_receipt,
    write_artifacts,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Build, preflight, admit, or verify CloudBank real-platform qualification evidence"
    )
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", type=Path, default=Path("."))
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--profile", type=Path, required=True)
    preflight.add_argument("--output-root", type=Path, required=True)
    render = commands.add_parser("render-gke-addons")
    render.add_argument("--project-id", required=True)
    render.add_argument("--region", required=True)
    render.add_argument("--cluster-name", required=True)
    render.add_argument("--namespace", required=True)
    render.add_argument("--hostname", required=True)
    render.add_argument("--letsencrypt-email", required=True)
    render.add_argument("--otel-collector-image", required=True)
    render.add_argument("--model-namespace", required=True)
    render.add_argument("--ollama-model-image", required=True)
    render.add_argument("--ollama-model-name", required=True)
    render.add_argument("--ollama-model-manifest-sha256", required=True)
    render.add_argument("--google-apis-cidr", required=True)
    render.add_argument("--output", type=Path, required=True)
    admit = commands.add_parser("admit")
    admit.add_argument("--project-root", type=Path, default=Path("."))
    admit.add_argument("--ms65-receipt", type=Path, required=True)
    admit.add_argument("--ms66-receipt", type=Path, required=True)
    admit.add_argument("--profile", type=Path, required=True)
    admit.add_argument("--observation", type=Path, required=True)
    admit.add_argument("--output-root", type=Path, required=True)
    admit.add_argument("--signer", required=True)
    admit.add_argument("--run-id")
    receipt = commands.add_parser("verify-receipt")
    receipt.add_argument("--project-root", type=Path, default=Path("."))
    receipt.add_argument("--receipt", type=Path, required=True)
    return root


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", "")
    if args.command in {"build", "verify"}:
        project_root = args.project_root.resolve()
        if args.command == "build":
            write_artifacts(project_root)
        errors = validate_artifacts(project_root)
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    elif args.command == "preflight":
        try:
            observation = preflight_platform(_load(args.profile), key)
            args.output_root.mkdir(parents=True, exist_ok=True)
            path = args.output_root / PREFLIGHT_NAME
            write_json(path, observation)
            result = {"status": "passed", "output": str(path),
                      "content_sha256": observation["content_sha256"]}
        except ValueError as exception:
            result = {"status": "failed", "error": str(exception)}
    elif args.command == "render-gke-addons":
        try:
            rendered = render_gke_addons(
                args.project_id, args.region, args.cluster_name, args.namespace,
                args.hostname, args.letsencrypt_email,
                args.otel_collector_image,
                args.model_namespace, args.ollama_model_image, args.ollama_model_name,
                args.ollama_model_manifest_sha256,
                args.google_apis_cidr,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            result = {"status": "passed", "output": str(args.output)}
        except ValueError as exception:
            result = {"status": "failed", "error": str(exception)}
    elif args.command == "admit":
        try:
            receipt = execute_qualification(
                args.project_root.resolve(), _load(args.ms65_receipt), _load(args.ms66_receipt),
                _load(args.profile), _load(args.observation), args.output_root.resolve(), key,
                args.signer, args.run_id,
            )
            result = {"status": "passed", "output": str(args.output_root / RECEIPT_NAME),
                      "run_id": receipt["run_id"], "content_sha256": receipt["content_sha256"]}
        except ValueError as exception:
            result = {"status": "failed", "error": str(exception),
                      "diagnostics": str(args.output_root / FAILURE_NAME)}
    else:
        errors = validate_execution_receipt(_load(args.receipt), key, args.project_root.resolve())
        result = {"status": "passed" if not errors else "failed", "errors": errors}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
