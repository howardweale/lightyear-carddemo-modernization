#!/usr/bin/env python3
"""Rotate, prove and restore the bounded CreditScore synthetic secret on GKE."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import tempfile
import uuid

from cloudbank_journeys import Heartbeat
from cloudbank_ms65_rehearsal import cluster_identity, evidence_key, load
from lightyear_data.cloudbank_edge_ai import validate_execution_receipt as validate_ms64
from lightyear_data.cloudbank_journeys import ACK, JourneyFailure, require
from lightyear_data.cloudbank_journeys_gke import GkeRuntime, command
from lightyear_data.cloudbank_platform_qualification import validate_profile
from lightyear_data.cloudbank_production_readiness import validate_image_lock
from lightyear_data.cloudbank_secret_rotation_gke import (
    ANNOTATION, EXTERNAL, GkeSecretBackend, Journal, SecretRotation, SERVICE, STATE_FILE,
    STATE_TYPE, hashed, utc, verified,
)
from lightyear_data.contracts import sign


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("action", choices=("preflight", "run", "recover", "verify"))
    for name in ("project", "region", "cluster", "namespace", "signer"):
        root.add_argument("--" + name, required=True)
    for name in ("image-lock", "ms64-receipt", "platform-profile", "output-root", "recovery-state", "observation"):
        root.add_argument("--" + name, type=Path)
    root.add_argument("--evidence-bucket", required=True)
    root.add_argument("--evidence-key-secret", default="cloudbank-ms67-evidence-key")
    return root


def safe_reason(exc):
    return str(exc) if isinstance(exc, JourneyFailure) else (
        "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "secret-rotation-input-or-runtime-error")


def current_recovery(args, key):
    require(args.recovery_state is not None, "secret-rotation-recovery-state-required")
    supplied = verified(load(args.recovery_state), key)
    uri = supplied.get("recovery_uri", "")
    require(uri.startswith(args.evidence_bucket.rstrip("/") + "/") and uri.endswith("/" + STATE_FILE),
            "secret-rotation-recovery-evidence-prefix-mismatch")
    generation = command(["gcloud", "storage", "objects", "describe", uri,
                          "--project", args.project, "--format=value(generation)"]).strip()
    require(generation.isdigit(), "secret-rotation-recovery-generation-invalid")
    # Always use the latest durable checkpoint, even if the operator's local
    # copy predates an upload or a disconnected process's final checkpoint.
    raw = command(["gcloud", "storage", "cat", uri + "#" + generation, "--project", args.project])
    state = verified(json.loads(raw), key)
    require(state.get("state_type") == STATE_TYPE and state.get("recovery_uri") == uri
            and state.get("run_id") == supplied.get("run_id")
            and state.get("context") == f"gke_{args.project}_{args.region}_{args.cluster}"
            and state.get("namespace") == args.namespace, "secret-rotation-recovery-context-mismatch")
    return state, generation


def verify_observation(value, key):
    verified(value, key)
    require(value.get("observation_type") == "lightyear-cloudbank-ms67-secret-rotation-observation"
            and value.get("status") == "passed-secret-rotation-and-restoration"
            and value.get("service") == SERVICE
            and value.get("recovery", {}).get("status") == "restored"
            and value["recovery"].get("temporary_version_disabled") is True
            and value["recovery"].get("original_values_restored") is True
            and value["recovery"].get("preexisting_versions_unchanged") is True
            and value["recovery"].get("errors") == []
            and value.get("credentials_persisted") is False and value.get("raw_output_persisted") is False
            and value.get("production_environment") is False and value.get("ms67_complete") is False
            and value.get("production_ready") is False, "secret-rotation-passing-observation-required")
    observations = value.get("observations", {})
    for name in ("baseline", "rotated", "restored"):
        row = observations.get(name, {})
        require(row.get("verified_replicas") == 2 and row.get("authenticated_contract_matches") is True
                and len(set(row.get("pod_uid_sha256", []))) == 2, "secret-rotation-two-replica-proof-required")
    require(observations["rotated"].get("different_from_prior") is True
            and set(observations["rotated"]["pod_uid_sha256"]).isdisjoint(observations["baseline"]["pod_uid_sha256"])
            and set(observations["restored"]["pod_uid_sha256"]).isdisjoint(observations["rotated"]["pod_uid_sha256"]),
            "secret-rotation-fresh-replica-proof-required")


def check_restored(engine):
    state, backend = engine.state, engine.b
    backend.guard(state)
    original = engine.original()
    engine.head()
    external = backend.r.get("externalsecret", EXTERNAL)
    field = external["spec"]["dataFrom"][0]["extract"]
    actual = {"version": field["version"]} if "version" in field else {}
    deploy = backend.r.deployment(SERVICE)
    require(actual == state["baseline"]["original_version_field"]
            and ANNOTATION not in deploy["spec"]["template"].get("metadata", {}).get("annotations", {}),
            "secret-rotation-restoration-policy-mismatch")
    backend.sync(state, original)
    backend.observe(state, original)
    temporary = state["versions"].get("rotated")
    require(not temporary or backend.version(temporary)["state"] == "DISABLED",
            "secret-rotation-temporary-version-still-enabled")
    lease = backend.lease()
    if lease and lease.get("spec", {}).get("holderIdentity") == state["run_id"]:
        backend.release(state)
        engine.save("lock-released")
    return {"status": "restored", "temporary_version_disabled": bool(temporary),
            "original_values_restored": True, "preexisting_versions_unchanged": True, "errors": []}


def main(argv=None):
    args = parser().parse_args(argv)
    heartbeat = Heartbeat()
    heartbeat.thread.start()
    previous_term = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    result, output, engine, runtime, key = {"status": "failed"}, None, None, None, ""
    try:
        require(all(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", value) for value in
                    (args.project, args.region, args.cluster, args.namespace)), "explicit-gcp-context-required")
        if args.action in {"run", "recover"}:
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
        require(args.evidence_bucket == f"gs://{args.project}-ms67-evidence/secret-rotation",
                "secret-rotation-project-private-evidence-prefix-required")
        require(bool(args.evidence_key_secret) and not args.evidence_key_secret.startswith("-"), "evidence-key-secret-required")
        key = evidence_key(args)
        if args.action == "verify":
            require(args.observation is not None, "secret-rotation-observation-required")
            verify_observation(load(args.observation), key)
            print(json.dumps({"status": "passed", "errors": []}))
            return 0
        run_id = "ms67-secret-" + uuid.uuid4().hex
        generation = "0"
        if args.action == "recover":
            state, generation = current_recovery(args, key)
            images = state["images"]
        else:
            require(all((args.image_lock, args.ms64_receipt, args.platform_profile)), "secret-rotation-bound-inputs-required")
            lock, ms64, profile = map(load, (args.image_lock, args.ms64_receipt, args.platform_profile))
            require(not validate_ms64(ms64, key, PROJECT_ROOT), "signed-current-ms64-receipt-required")
            require(not validate_image_lock(lock, ms64["content_sha256"]), "ms64-bound-image-lock-required")
            require(not validate_profile(profile, key), "signed-authorized-ms67-profile-required")
            images = {row["service"]: row["reference"] for row in lock["images"]}
        parent = Path.home() / "ms67-evidence"
        if args.output_root:
            output = args.output_root.resolve()
            require(not output.exists() and not output.is_relative_to(PROJECT_ROOT), "fresh-private-output-required")
            output.mkdir(parents=True, mode=0o700)
        else:
            parent.mkdir(parents=True, exist_ok=True)
            output = Path(tempfile.mkdtemp(prefix="ms67-secret-rotation.", dir=parent))
        evidence_uri = args.evidence_bucket + "/" + output.name + "/"
        print("MS67_SECRET_ROTATION_ROOT=" + str(output), flush=True)
        runtime = GkeRuntime(project=args.project, region=args.region, cluster=args.cluster, namespace=args.namespace,
                             images=images, run_id=state["run_id"] if args.action == "recover" else run_id,
                             output=output, progress=heartbeat.progress)
        backend = GkeSecretBackend(runtime)
        if args.action == "recover":
            backend.load_credit_credentials(state)
        else:
            require(profile["context"] == runtime.context and profile["region"] == args.region
                    and profile["namespace"] == args.namespace
                    and profile["provider"] == "google-gke-standard-regional"
                    and profile["cluster_uid_sha256"] == cluster_identity(args.project, args.region, args.cluster),
                    "secret-rotation-profile-cluster-mismatch")
            namespace_uid = runtime.get("namespace", args.namespace)["metadata"]["uid"]
            require(profile["namespace_uid_sha256"] == hashlib.sha256(namespace_uid.encode()).hexdigest(),
                    "secret-rotation-profile-namespace-mismatch")
            heartbeat.progress("Validating all eight images and secret syncs, then the CreditScore mapping")
            baseline, original = backend.preflight()
            state = {"schema_version": "1.0", "state_type": STATE_TYPE, "run_id": run_id,
                "context": runtime.context, "namespace": args.namespace, "images": images,
                "baseline": baseline, "versions": {}, "version_payloads": {}, "observations": {},
                "pending_add": None, "lease_uid": None, "cleanup_complete": False,
                "recovery_uri": evidence_uri + STATE_FILE, "executor_id": uuid.uuid4().hex,
                "bindings": {"ms64_receipt_sha256": ms64["content_sha256"], "image_lock_sha256": lock["content_sha256"],
                             "platform_profile_sha256": profile["content_sha256"]},
                "credentials_persisted": False, "raw_output_persisted": False, "production_environment": False}
        journal = Journal(output / STATE_FILE, state["recovery_uri"], args.project, key, args.signer, generation=generation)
        engine = SecretRotation(backend, journal, state)
        if args.action != "preflight":
            print("MS67_SECRET_ROTATION_RECOVERY_STATE=" + state["recovery_uri"], flush=True)
        if args.action == "preflight":
            observed = backend.observe(state, original)
            result = engine.observation("passed-secret-rotation-preflight", {"status": "not-required", "errors": []})
            result["observations"]["baseline"] = observed
        elif args.action == "recover":
            heartbeat.progress("Recovering the signed CreditScore rotation checkpoint")
            if state.get("cleanup_complete"):
                cleanup = check_restored(engine)
            elif state.get("phase") == "before-lock" and backend.lease() is None:
                cleanup = check_restored(engine)
                state["cleanup_complete"] = True
                engine.save("no-mutations-to-recover")
            else:
                lease = backend.lease()
                require(lease is not None and lease.get("spec", {}).get("holderIdentity") == state["run_id"],
                        "secret-rotation-recovery-lock-not-found")
                state["lease_uid"] = state["lease_uid"] or lease["metadata"]["uid"]
                state["prior_executor_id"] = lease["metadata"].get("annotations", {}).get("lightyear.ai/executor")
                state["executor_id"] = uuid.uuid4().hex
                engine.save("before-recovery-takeover")
                backend.takeover(state)
                engine.save("recovery-lock-acquired")
                cleanup = engine.restore()
            result = engine.observation("recovered-secret-rotation", cleanup)
        else:
            heartbeat.progress("Rotating CreditScore, verifying both replicas, then restoring original values")
            result = engine.run(original)
    except (Exception, KeyboardInterrupt) as exc:
        cleanup = {"status": "not-started", "errors": []}
        if engine and args.action != "preflight":
            try:
                if engine.state.get("cleanup_complete"):
                    cleanup = check_restored(engine)
                else:
                    engine.b.owned(engine.state)
                    heartbeat.progress("Restoring CreditScore after the interrupted drill")
                    cleanup = engine.restore()
            except (Exception, KeyboardInterrupt) as recovery_exc:
                cleanup = {"status": "recovery-required", "errors": [safe_reason(recovery_exc)]}
        result = {"status": "failed", "reason": safe_reason(exc), "recovery": cleanup,
                  "ms67_complete": False, "production_ready": False}
    finally:
        if runtime:
            for service in list(runtime.forwards):
                try:
                    runtime.close_forward(service)
                except Exception:
                    pass
            runtime.tokens.clear()
            runtime.credentials.clear()
        if output and key:
            try:
                filename = "secret-rotation.observation.json"
                if result.get("status") == "passed-secret-rotation-and-restoration":
                    verify_observation(sign(result, key, args.signer), key)
                observation = Journal(output / filename, args.evidence_bucket + "/" + output.name + "/" + filename,
                                      args.project, key, args.signer).write(result)
                if result.get("status") == "passed-secret-rotation-and-restoration":
                    verify_observation(observation, key)
                print("MS67_SECRET_ROTATION_EVIDENCE_READBACK=VERIFIED", flush=True)
            except Exception:
                result["status"] = "failed"
                result["reason"] = "secret-rotation-evidence-upload-readback-or-validation-failed"
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, previous_term)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"passed-secret-rotation-preflight", "passed-secret-rotation-and-restoration", "recovered-secret-rotation"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
