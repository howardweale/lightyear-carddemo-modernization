#!/usr/bin/env python3
"""Observe and clean up one synthetic Monitoring incident in the MS67 project."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile
import uuid

from cloudbank_journeys import Heartbeat
from cloudbank_ms65_rehearsal import cluster_identity, evidence_key, load
from lightyear_data.cloudbank_alert_drill import (
    AlertDrill, IDENTITY_PATTERN, Monitoring, OBSERVATION_FILE, STATE_FILE, STATE_TYPE,
    matches, stamp, validate_state, verify_observation,
)
from lightyear_data.cloudbank_edge_ai import validate_execution_receipt as validate_ms64
from lightyear_data.cloudbank_journeys import ACK, JourneyFailure, SERVICES, require
from lightyear_data.cloudbank_journeys_gke import GkeRuntime, command
from lightyear_data.cloudbank_platform_qualification import validate_profile
from lightyear_data.cloudbank_production_readiness import validate_image_lock
from lightyear_data.cloudbank_secret_rotation_gke import Journal, hashed
from lightyear_data.contracts import sign


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("action", choices=("preflight", "run", "recover", "verify"))
    for name in ("project", "region", "cluster", "namespace", "signer", "evidence-bucket"):
        root.add_argument("--" + name, required=True)
    for name in ("image-lock", "ms64-receipt", "platform-profile", "output-root", "recovery-state", "observation"):
        root.add_argument("--" + name, type=Path)
    root.add_argument("--evidence-key-secret", default="cloudbank-ms67-evidence-key")
    root.add_argument("--original-process-stopped", action="store_true",
                      help="Required for recovery after the original executor has stopped.")
    return root


def safe_reason(exc):
    return str(exc) if isinstance(exc, JourneyFailure) else (
        "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "alert-input-or-runtime-error")


def current_recovery(args, key, number):
    require(args.original_process_stopped and args.recovery_state is not None,
            "alert-recovery-requires-stopped-original-process-and-checkpoint")
    context = {k: getattr(args, k) for k in ("project", "region", "cluster", "namespace", "evidence_bucket")}
    supplied = validate_state(load(args.recovery_state), key, project_number=number, **context)
    uri = supplied["recovery_uri"]
    generation = command(["gcloud", "storage", "objects", "describe", uri,
                          "--project", args.project, "--format=value(generation)"]).strip()
    require(generation.isdigit(), "alert-recovery-generation-invalid")
    raw = command(["gcloud", "storage", "cat", uri + "#" + generation, "--project", args.project])
    state = validate_state(json.loads(raw), key, project_number=number, **context)
    require(state["recovery_uri"] == uri and state["run_id"] == supplied["run_id"], "alert-recovery-run-mismatch")
    return state, generation


def initial_state(args, key, number, output, progress):
    require(all((args.image_lock, args.ms64_receipt, args.platform_profile)), "alert-bound-inputs-required")
    lock, ms64, profile = map(load, (args.image_lock, args.ms64_receipt, args.platform_profile))
    require(not validate_ms64(ms64, key, PROJECT_ROOT), "signed-current-ms64-receipt-required")
    require(not validate_image_lock(lock, ms64["content_sha256"]), "ms64-bound-image-lock-required")
    require(not validate_profile(profile, key), "signed-authorized-ms67-profile-required")
    run_id = "ms67-alert-" + uuid.uuid4().hex
    images = {row["service"]: row["reference"] for row in lock["images"]}
    runtime = GkeRuntime(project=args.project, region=args.region, cluster=args.cluster, namespace=args.namespace,
                         images=images, run_id=run_id, output=output, progress=progress)
    require(profile["context"] == runtime.context and profile["region"] == args.region
            and profile["namespace"] == args.namespace and profile["provider"] == "google-gke-standard-regional"
            and profile["cluster_uid_sha256"] == cluster_identity(args.project, args.region, args.cluster),
            "alert-profile-cluster-mismatch")
    namespace_uid = runtime.get("namespace", args.namespace)["metadata"]["uid"]
    require(profile["namespace_uid_sha256"] == hashlib.sha256(namespace_uid.encode()).hexdigest(),
            "alert-profile-namespace-mismatch")
    progress("Checking the bound non-production environment and eight running images")
    environment = runtime.environment()
    require(environment["namespace_uid_sha256"] == hashed(namespace_uid), "alert-namespace-changed-during-preflight")
    for service in SERVICES:
        runtime.service_ready(service)
    return {"schema_version": "1.0", "state_type": STATE_TYPE, "run_id": run_id,
            "project_number": number, "context": runtime.context, "environment": environment,
            "bindings": {"ms64_receipt_sha256": ms64["content_sha256"], "image_lock_sha256": lock["content_sha256"],
                         "platform_profile_sha256": profile["content_sha256"]},
            "recovery_uri": args.evidence_bucket + "/" + run_id + "/" + STATE_FILE,
            "descriptor_phase": "not-started", "policy_phase": "not-started", "policy_name": None,
            "observations": {}, "cleanup_complete": False, "phase": "validated", "updated_at": stamp(),
            "credentials_persisted": False, "raw_output_persisted": False, "production_environment": False}


def main(argv=None):
    args = parser().parse_args(argv)
    heartbeat = Heartbeat()
    heartbeat.thread.start()
    previous_term = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    engine, output, key = None, None, ""
    result = {"status": "failed", "ms67_complete": False, "production_ready": False}
    try:
        require(all(matches(IDENTITY_PATTERN, getattr(args, k)) for k in
                    ("project", "region", "cluster", "namespace")), "explicit-gcp-context-required")
        require(args.evidence_bucket == f"gs://{args.project}-ms67-evidence/alert-drill",
                "alert-project-private-evidence-prefix-required")
        require(matches(r"[A-Za-z0-9_-]{1,255}", args.evidence_key_secret), "evidence-key-secret-required")
        if args.action in {"run", "recover"}:
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
        key = evidence_key(args)
        if args.action == "verify":
            require(args.observation is not None, "alert-observation-required")
            observation = load(args.observation)
            verify_observation(observation, key)
            require(all(observation["environment"][k] == getattr(args, k) for k in
                        ("project", "region", "cluster", "namespace")), "alert-observation-context-mismatch")
            print(json.dumps({"status": "passed", "errors": []}))
            return 0
        number = command(["gcloud", "projects", "describe", args.project, "--format=value(projectNumber)"]).strip()
        api = Monitoring(args.project, number)
        generation = "0"
        if args.action == "recover":
            state, generation = current_recovery(args, key, number)
        if args.output_root:
            candidate = args.output_root.resolve()
            require(not candidate.exists() and not candidate.is_relative_to(PROJECT_ROOT), "fresh-private-output-required")
            candidate.mkdir(parents=True, mode=0o700)
            output = candidate
        else:
            parent = Path.home() / "ms67-evidence"
            parent.mkdir(parents=True, exist_ok=True)
            output = Path(tempfile.mkdtemp(prefix="ms67-alert-drill.", dir=parent))
        print("MS67_ALERT_ROOT=" + str(output), flush=True)
        if args.action != "recover":
            state = initial_state(args, key, number, output, heartbeat.progress)
        journal = Journal(output / STATE_FILE, state["recovery_uri"], args.project, key, args.signer, generation=generation)
        engine = AlertDrill(api, journal, state, progress=heartbeat.progress)
        if args.action == "preflight":
            engine.fresh()
            result = engine.observation("passed-alert-preflight", {"status": "not-required", "errors": []})
        else:
            print("MS67_ALERT_RECOVERY_STATE=" + state["recovery_uri"], flush=True)
            engine.save("before-" + args.action)
            if args.action == "recover":
                heartbeat.progress("Removing only the resources owned by the interrupted alert drill")
                result = engine.observation("recovered-alert-drill", engine.cleanup())
            else:
                result = engine.run()
    except (Exception, KeyboardInterrupt) as exc:
        cleanup = {"status": "not-started", "errors": []}
        if engine and args.action in {"run", "recover"}:
            try:
                heartbeat.progress("Cleaning up the interrupted alert drill")
                cleanup = engine.cleanup()
            except (Exception, KeyboardInterrupt) as recovery_exc:
                cleanup = {"status": "recovery-required", "errors": [safe_reason(recovery_exc)]}
        result = (engine.observation("failed", cleanup) if engine else result)
        result.update(status="failed", reason=safe_reason(exc), recovery=cleanup)
    finally:
        if output and key:
            try:
                if result.get("status") == "passed-synthetic-alert-and-recovery":
                    verify_observation(sign(result, key, args.signer), key)
                # Recovery writes a new observation; it does not overwrite an earlier pass.
                uri = args.evidence_bucket + "/observations/" + output.name + "/" + OBSERVATION_FILE
                observation = Journal(output / OBSERVATION_FILE, uri, args.project, key, args.signer).write(result)
                if result.get("status") == "passed-synthetic-alert-and-recovery":
                    verify_observation(observation, key)
                print("MS67_ALERT_OBSERVATION=" + uri, flush=True)
                print("MS67_ALERT_EVIDENCE_READBACK=VERIFIED", flush=True)
            except Exception:
                result.update(status="failed", reason="alert-evidence-upload-readback-or-validation-failed")
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, previous_term)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"passed-alert-preflight", "passed-synthetic-alert-and-recovery", "recovered-alert-drill"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
