#!/usr/bin/env python3
"""Render or sequentially enforce explicit MS67 application UID/GID 65532."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import uuid

from cloudbank_journeys import Heartbeat
from cloudbank_ms65_rehearsal import cluster_identity, evidence_key, load
from lightyear_data.cloudbank_edge_ai import validate_execution_receipt as validate_ms64
from lightyear_data.cloudbank_image_security import ImageJournal, save_observation
from lightyear_data.cloudbank_journeys import ACK, JourneyFailure, hashed, require
from lightyear_data.cloudbank_journeys_gke import GkeRuntime
from lightyear_data.cloudbank_platform_qualification import validate_profile
from lightyear_data.cloudbank_production_readiness import validate_image_lock
from lightyear_data.cloudbank_runtime_identity import (
    IdentityRollout, OBSERVATION_FILE, STATE_FILE, instrument_bundle, verify_observation,
)
from lightyear_data.contracts import sign

ROOT = Path(__file__).resolve().parents[1]


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("action", choices=("render", "preflight", "run", "verify"))
    root.add_argument("--namespace", required=True)
    for name in ("project", "region", "cluster", "signer", "evidence-bucket"):
        root.add_argument("--" + name)
    for name in ("bundle", "output", "image-lock", "ms64-receipt", "platform-profile", "output-root", "observation"):
        root.add_argument("--" + name, type=Path)
    root.add_argument("--evidence-key-secret", default="cloudbank-ms67-evidence-key")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    heartbeat, runtime, output, key, state = Heartbeat(), None, None, None, None
    prior = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    heartbeat.thread.start()
    try:
        if args.action == "render":
            require(args.bundle and args.output, "runtime-identity-render-input-and-output-required")
            args.output.write_text(json.dumps(instrument_bundle(load(args.bundle), args.namespace), indent=2) + "\n", encoding="utf-8")
            return 0
        require(all(getattr(args, k) for k in ("project", "region", "cluster", "signer", "image_lock", "ms64_receipt", "platform_profile")),
                "runtime-identity-explicit-context-and-bound-inputs-required")
        require(args.evidence_bucket == f"gs://{args.project}-ms67-evidence/runtime-identity", "runtime-identity-private-evidence-prefix-required")
        if args.action == "run":
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
        key = evidence_key(args)
        lock, ms64, profile = map(load, (args.image_lock, args.ms64_receipt, args.platform_profile))
        require(not validate_ms64(ms64, key, ROOT) and not validate_image_lock(lock, ms64["content_sha256"])
                and not validate_profile(profile, key), "runtime-identity-signed-inputs-invalid")
        images = {row["service"]: row["reference"] for row in lock["images"]}
        bindings = {"image_lock_sha256": lock["content_sha256"], "ms64_receipt_sha256": ms64["content_sha256"],
                    "platform_profile_sha256": profile["content_sha256"]}
        environment = {k: getattr(args, k) for k in ("project", "region", "cluster", "namespace")}
        if args.action == "verify":
            require(args.observation, "runtime-identity-observation-required")
            verify_observation(load(args.observation), key, bindings, images, environment)
            print(json.dumps({"status": "passed", "errors": []}))
            return 0
        require(args.output_root, "runtime-identity-fresh-output-required")
        candidate = args.output_root.resolve()
        require(not candidate.exists() and not candidate.is_relative_to(ROOT), "runtime-identity-fresh-private-output-required")
        candidate.mkdir(parents=True, mode=0o700)
        output = candidate
        run_id = "ms67-identity-" + uuid.uuid4().hex
        print("MS67_RUNTIME_IDENTITY_ROOT=" + str(output), flush=True)
        runtime = GkeRuntime(**environment, images=images, run_id=run_id, output=output, progress=heartbeat.progress)
        environment = runtime.environment()
        namespace_uid = runtime.get("namespace", args.namespace)["metadata"]["uid"]
        require(profile["context"] == runtime.context and profile["namespace"] == args.namespace
                and profile["region"] == args.region and profile["provider"] == "google-gke-standard-regional"
                and profile["cluster_uid_sha256"] == cluster_identity(args.project, args.region, args.cluster)
                and profile["namespace_uid_sha256"] == hashlib.sha256(namespace_uid.encode()).hexdigest()
                and environment["namespace_uid_sha256"] == hashed(namespace_uid), "runtime-identity-profile-live-environment-mismatch")
        prefix = args.evidence_bucket + "/" + run_id + "/"
        state = {"schema_version": "1.0", "state_type": "lightyear-cloudbank-ms67-runtime-identity-state",
                 "run_id": run_id, "environment": environment, "bindings": bindings, "images": images,
                 "phase": "validating", "credentials_persisted": False, "raw_output_persisted": False,
                 "production_environment": False, "ms67_complete": False, "production_ready": False}
        journal = ImageJournal(output / STATE_FILE, prefix + STATE_FILE, args.project, key, args.signer)
        engine = IdentityRollout(runtime, journal, state, heartbeat.progress)
        if args.action == "preflight":
            engine.preflight()
            result = {**state, "status": "passed-runtime-identity-preflight", "application_mutations": 0}
            save_observation(output / "runtime-identity.preflight.json", result, key, args.signer)
        else:
            print("MS67_RUNTIME_IDENTITY_STATE=" + prefix + STATE_FILE, flush=True)
            result = engine.run()
            verify_observation(sign(result, key, args.signer), key, bindings, images, environment)
            saved = ImageJournal(output / OBSERVATION_FILE, prefix + OBSERVATION_FILE, args.project, key, args.signer).write(result)
            verify_observation(saved, key, bindings, images, environment)
            print("MS67_RUNTIME_IDENTITY_EVIDENCE_READBACK=VERIFIED", flush=True)
            print("MS67_RUNTIME_IDENTITY_OBSERVATION=" + prefix + OBSERVATION_FILE, flush=True)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        reason = str(exc) if isinstance(exc, JourneyFailure) else (
            "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "runtime-identity-input-or-runtime-error")
        result = {"status": "failed", "reason": reason, "phase": state.get("phase") if state else "before-run",
                  "verified_services": sorted(state.get("services", {})) if state else [],
                  "configuration_retained": True, "ms67_complete": False, "production_ready": False}
        if output and output.is_dir() and key:
            save_observation(output / "runtime-identity.result.json", result, key, args.signer)
        print(json.dumps(result, indent=2))
        return 1
    finally:
        if runtime:
            for service in list(runtime.forwards):
                runtime.close_forward(service)
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, prior)


if __name__ == "__main__":
    raise SystemExit(main())
