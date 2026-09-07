#!/usr/bin/env python3
"""Build and execute the durable governed MS66 dual-lane workflow."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal

from lightyear_data.cloudbank_journeys import ACK, JourneyFailure, require
from lightyear_data.cloudbank_ms66_dual_lane_gke import (
    cleanup_from_recovery_state,
    execute_dual_lane,
)
from lightyear_data.cloudbank_ms66_hardening import (
    MATERIALIZATION_RECEIPT,
    build_source_image_lock,
    materialize_hardened_source,
    validate_hardening,
    validate_source_image_lock,
)
from lightyear_data.contracts import sign


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict:
    require(path.is_file() and path.stat().st_size <= 4 * 1024 * 1024,
            "ms66-input-file-invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise JourneyFailure("ms66-input-json-invalid") from None
    require(isinstance(value, dict), "ms66-input-object-required")
    return value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    verify = commands.add_parser("verify-hardening")
    verify.add_argument("--project-root", type=Path, default=PROJECT_ROOT)

    materialize = commands.add_parser("materialize")
    materialize.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    materialize.add_argument("--source-root", type=Path, required=True)
    materialize.add_argument("--output-root", type=Path, required=True)

    lock = commands.add_parser("source-lock")
    lock.add_argument("--images", type=Path, required=True,
                      help="JSON object mapping the eight service names to immutable references")
    lock.add_argument("--materialization", type=Path, required=True)
    lock.add_argument("--controller-commit", required=True)
    lock.add_argument("--cloud-build-id", required=True)
    lock.add_argument("--java-base-image", required=True)
    lock.add_argument("--oracle-runtime-image", required=True)
    lock.add_argument("--microtx-runtime-image", required=True)
    lock.add_argument("--signer", required=True)
    lock.add_argument("--output", type=Path, required=True)

    run = commands.add_parser("run")
    run.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    run.add_argument("--source-root", type=Path, required=True)
    run.add_argument("--ms61-receipt", type=Path, required=True)
    run.add_argument("--ms64-receipt", type=Path, required=True)
    run.add_argument("--source-image-lock", type=Path, required=True)
    run.add_argument("--target-image-lock", type=Path, required=True)
    run.add_argument("--project", required=True)
    run.add_argument("--region", required=True)
    run.add_argument("--cluster", required=True)
    run.add_argument("--target-namespace", required=True)
    run.add_argument("--isolated-namespace", required=True)
    run.add_argument("--model-namespace", required=True)
    run.add_argument("--model-name", required=True)
    run.add_argument("--postgresql-probe-image", required=True)
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--evidence-prefix")
    run.add_argument("--signer", required=True)
    run.add_argument("--run-id", required=True)

    recover = commands.add_parser("recover")
    recover.add_argument("--recovery-state", type=Path, required=True)
    recover.add_argument("--output", type=Path, required=True)
    recover.add_argument("--signer", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    previous_term = signal.signal(
        signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt())
    )
    key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", "")
    try:
        if args.command == "verify-hardening":
            errors = validate_hardening(args.project_root.resolve())
            result = {"status": "passed" if not errors else "failed", "errors": errors}
        elif args.command == "materialize":
            workspace, receipt = materialize_hardened_source(
                args.project_root.resolve(), args.source_root.resolve(), args.output_root.resolve(),
            )
            result = {"status": "passed", "workspace": str(workspace),
                      "materialization": str(args.output_root / MATERIALIZATION_RECEIPT),
                      "content_sha256": receipt["content_sha256"]}
        elif args.command == "source-lock":
            require(bool(key), "ms66-evidence-key-required")
            images = _load(args.images)
            materialization = _load(args.materialization)
            lock = build_source_image_lock(
                images, materialization, controller_commit=args.controller_commit,
                cloud_build_id=args.cloud_build_id, java_base_image=args.java_base_image,
                oracle_runtime_image=args.oracle_runtime_image,
                microtx_runtime_image=args.microtx_runtime_image,
                key=key, signer=args.signer,
            )
            errors = validate_source_image_lock(lock, key)
            require(not errors, "ms66-generated-source-lock-invalid")
            _write(args.output, lock)
            result = {"status": "passed", "output": str(args.output),
                      "content_sha256": lock["content_sha256"]}
        elif args.command == "recover":
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK,
                    "non-production-mutation-ack-required")
            require(bool(key), "ms66-evidence-key-required")
            state = _load(args.recovery_state)
            recovery = cleanup_from_recovery_state(state, key)
            recovery_receipt = sign({
                "schema_version": "1.0",
                "receipt_type": "lightyear-cloudbank-ms66-isolated-lane-recovery-execution",
                "source_recovery_state_sha256": state["content_sha256"],
                "recovery": recovery,
                "ms66_complete": False,
                "ms67_complete": False,
                "credentials_persisted": False,
                "raw_output_persisted": False,
            }, key, args.signer)
            _write(args.output, recovery_receipt)
            result = {"status": "passed" if recovery["status"] == "restored" else "failed",
                      "recovery": recovery, "output": str(args.output)}
        else:
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK,
                    "non-production-mutation-ack-required")
            require(bool(key), "ms66-evidence-key-required")
            receipt = execute_dual_lane(
                project_root=args.project_root.resolve(), source_root=args.source_root.resolve(),
                ms61=_load(args.ms61_receipt), ms64=_load(args.ms64_receipt),
                source_lock=_load(args.source_image_lock), target_lock=_load(args.target_image_lock),
                project=args.project, region=args.region, cluster=args.cluster,
                target_namespace=args.target_namespace, isolated_namespace=args.isolated_namespace,
                model_namespace=args.model_namespace, model_name=args.model_name,
                postgres_probe_image=args.postgresql_probe_image,
                output=args.output_root.resolve(), evidence_prefix=args.evidence_prefix,
                key=key, signer=args.signer, run_id=args.run_id,
                progress=lambda message: print("[ms66] " + message, flush=True),
            )
            result = {"status": "passed", "receipt": str(args.output_root /
                      "cloudbank-whole-application-equivalence.receipt.json"),
                      "content_sha256": receipt["content_sha256"]}
    except (JourneyFailure, ValueError) as exc:
        reason = str(exc)
        result = {"status": "failed", "reason": reason
                  if reason and len(reason) <= 2048 else "ms66-bounded-execution-failed"}
    finally:
        signal.signal(signal.SIGTERM, previous_term)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
