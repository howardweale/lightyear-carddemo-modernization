#!/usr/bin/env python3
"""Roll out bounded request logging, then verify GKE log/trace correlation."""
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
from lightyear_data.cloudbank_edge_ai import validate_execution_receipt as validate_ms64
from lightyear_data.cloudbank_journeys import ACK, JourneyFailure, SERVICES, hashed, require
from lightyear_data.cloudbank_journeys_gke import GkeRuntime, command
from lightyear_data.cloudbank_log_correlation import (
    LoggingRollout, Telemetry, STATE_TYPE, STATE_FILE, OBSERVATION_FILE, LEASE, MANAGER,
    configuration, instrument_bundle, stamp, verify_observation,
)
from lightyear_data.cloudbank_platform_qualification import validate_profile
from lightyear_data.cloudbank_production_readiness import validate_image_lock
from lightyear_data.cloudbank_secret_rotation_gke import Journal
from lightyear_data.contracts import content_hash, sign, verify_signature

ROOT = Path(__file__).resolve().parents[1]


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("action", choices=("preflight", "run", "recover", "verify", "render"))
    for name in ("project", "namespace"):
        root.add_argument("--" + name, required=True)
    for name in ("region", "cluster", "signer", "evidence-bucket"):
        root.add_argument("--" + name)
    for name in ("image-lock", "ms64-receipt", "platform-profile", "output-root", "recovery-state", "observation", "bundle", "output"):
        root.add_argument("--" + name, type=Path)
    root.add_argument("--evidence-key-secret", default="cloudbank-ms67-evidence-key")
    root.add_argument("--original-process-stopped", action="store_true")
    return root


def reason(exc):
    return str(exc) if isinstance(exc, JourneyFailure) else (
        "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "logging-input-or-runtime-error")


def validate_checkpoint(state, args, key):
    require(state.get("content_sha256") == content_hash(state) and verify_signature(state, key), "logging-checkpoint-signature-invalid")
    require(state.get("state_type") == STATE_TYPE and state.get("production_environment") is False
            and state.get("credentials_persisted") is False and state.get("raw_output_persisted") is False,
            "logging-checkpoint-type-invalid")
    require(all(state.get("environment", {}).get(k) == getattr(args, k) for k in ("project", "region", "cluster", "namespace"))
            and state.get("configuration_sha256") == hashlib.sha256(configuration(args.project).encode()).hexdigest(),
            "logging-checkpoint-context-or-configuration-mismatch")
    require(state.get("recovery_uri") == args.evidence_bucket + "/" + state["run_id"] + "/" + STATE_FILE
            and set(state.get("images", {})) == set(SERVICES) and set(state.get("baseline", {})) == set(SERVICES),
            "logging-checkpoint-bindings-invalid")
    return state


def main(argv=None):
    args = parser().parse_args(argv)
    if args.action == "render":
        require(args.bundle and args.output, "logging-render-input-and-output-required")
        args.output.write_text(json.dumps(instrument_bundle(load(args.bundle), args.project, args.namespace), indent=2) + "\n", encoding="utf-8")
        return 0
    heartbeat = Heartbeat()
    heartbeat.thread.start()
    prior_signal = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    runtime, engine, output, key = None, None, None, ""
    result = {"status": "failed", "service_correlation_qualified": False, "ms67_complete": False, "production_ready": False}
    try:
        require(all(getattr(args, k) for k in ("region", "cluster", "signer")), "logging-explicit-context-required")
        require(args.evidence_bucket == f"gs://{args.project}-ms67-evidence/log-correlation", "logging-private-evidence-prefix-required")
        if args.action in {"run", "recover"}:
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
        key = evidence_key(args)
        if args.action == "verify":
            require(args.observation is not None, "logging-observation-required")
            value = load(args.observation)
            verify_observation(value, key)
            require(all(value["environment"][k] == getattr(args, k) for k in ("project", "region", "cluster", "namespace")),
                    "logging-observation-context-mismatch")
            require(args.image_lock and args.ms64_receipt and args.platform_profile, "logging-bound-inputs-required")
            lock, ms64, profile = map(load, (args.image_lock, args.ms64_receipt, args.platform_profile))
            require(not validate_ms64(ms64, key, ROOT) and not validate_image_lock(lock, ms64["content_sha256"])
                    and not validate_profile(profile, key), "logging-verification-inputs-invalid")
            require(value["bindings"] == {"image_lock_sha256": lock["content_sha256"],
                    "ms64_receipt_sha256": ms64["content_sha256"], "platform_profile_sha256": profile["content_sha256"]}
                    and value["images"] == {row["service"]: row["reference"] for row in lock["images"]},
                    "logging-verification-input-bindings-mismatch")
            print(json.dumps({"status": "passed", "errors": []}))
            return 0
        generation = "0"
        if args.action == "recover":
            require(args.original_process_stopped and args.recovery_state, "logging-stopped-original-and-checkpoint-required")
            supplied = validate_checkpoint(load(args.recovery_state), args, key)
            uri = supplied["recovery_uri"]
            generation = command(["gcloud", "storage", "objects", "describe", uri, "--project", args.project,
                                  "--format=value(generation)"]).strip()
            require(generation.isdigit(), "logging-checkpoint-generation-invalid")
            state = validate_checkpoint(json.loads(command(["gcloud", "storage", "cat", uri + "#" + generation,
                                                          "--project", args.project])), args, key)
            require(state["run_id"] == supplied["run_id"], "logging-checkpoint-run-mismatch")
            require(not state.get("cleanup_complete"), "logging-operation-already-complete")
            images = state["images"]
            run_id = state["run_id"]
        else:
            require(args.image_lock and args.ms64_receipt and args.platform_profile, "logging-bound-inputs-required")
            lock, ms64, profile = map(load, (args.image_lock, args.ms64_receipt, args.platform_profile))
            require(not validate_ms64(ms64, key, ROOT), "signed-current-ms64-receipt-required")
            require(not validate_image_lock(lock, ms64["content_sha256"]), "ms64-bound-image-lock-required")
            require(not validate_profile(profile, key), "signed-authorized-ms67-profile-required")
            images = {row["service"]: row["reference"] for row in lock["images"]}
            run_id = "ms67-logs-" + uuid.uuid4().hex
        if args.output_root:
            output = args.output_root.resolve()
            require(not output.exists() and not output.is_relative_to(ROOT), "logging-fresh-private-output-required")
            output.mkdir(parents=True, mode=0o700)
        else:
            parent = Path.home() / "ms67-evidence"
            parent.mkdir(parents=True, exist_ok=True)
            output = Path(tempfile.mkdtemp(prefix="ms67-log-correlation.", dir=parent))
        print("MS67_LOG_CORRELATION_ROOT=" + str(output), flush=True)
        runtime = GkeRuntime(project=args.project, region=args.region, cluster=args.cluster, namespace=args.namespace,
                             images=images, run_id=run_id, output=output, progress=heartbeat.progress)
        heartbeat.progress("Checking the signed inputs and live non-production environment")
        environment = runtime.environment()
        live_cluster = cluster_identity(args.project, args.region, args.cluster)
        if args.action == "recover":
            require(environment == state["environment"] and live_cluster == state["cluster_identity_sha256"],
                    "logging-recovery-live-environment-mismatch")
        else:
            namespace_uid = runtime.get("namespace", args.namespace)["metadata"]["uid"]
            require(profile["context"] == runtime.context and profile["namespace"] == args.namespace
                    and profile["region"] == args.region and profile["provider"] == "google-gke-standard-regional"
                    and profile["cluster_uid_sha256"] == live_cluster
                    and profile["namespace_uid_sha256"] == hashlib.sha256(namespace_uid.encode()).hexdigest()
                    and environment["namespace_uid_sha256"] == hashed(namespace_uid), "logging-profile-live-environment-mismatch")
            state = {"schema_version": "1.0", "state_type": STATE_TYPE, "run_id": run_id,
                     "environment": environment, "cluster_identity_sha256": live_cluster, "images": images,
                     "bindings": {"image_lock_sha256": lock["content_sha256"], "ms64_receipt_sha256": ms64["content_sha256"],
                                  "platform_profile_sha256": profile["content_sha256"]},
                     "configuration_sha256": hashlib.sha256(configuration(args.project).encode()).hexdigest(),
                     "recovery_uri": args.evidence_bucket + "/" + run_id + "/" + STATE_FILE,
                     "executor_id": uuid.uuid4().hex, "lease_uid": None, "cleanup_complete": False,
                     "credentials_persisted": False, "raw_output_persisted": False, "production_environment": False,
                     "phase": "validated", "updated_at": stamp()}
        journal = Journal(output / STATE_FILE, state["recovery_uri"], args.project, key, args.signer, generation=generation)
        engine = LoggingRollout(runtime, journal, state, heartbeat.progress)
        if args.action == "recover":
            # Check and fence the previous executor before restoring. A released
            # lease with this checkpoint can occur if the final write was lost.
            lease = engine.optional("lease", LEASE)
            if lease is None and state["phase"] == "before-lock" and state.get("lease_uid") is None:
                engine.save("restored")
                state["cleanup_complete"] = True
                engine.save("restored")
                recovery = {"status": "restored", "errors": []}
            else:
                require(lease and lease["metadata"].get("annotations", {}).get("lightyear.ai/recovery-state") == state["recovery_uri"]
                        and lease["metadata"].get("labels", {}).get("app.kubernetes.io/managed-by") == MANAGER
                        and lease["metadata"].get("annotations", {}).get("lightyear.ai/executor") in
                        {state["executor_id"], state.get("prior_executor_id")}
                        and lease.get("spec", {}).get("holderIdentity") in {state["run_id"], ""}
                        and state.get("lease_uid") in {None, lease["metadata"]["uid"]}, "logging-recovery-lease-mismatch")
                state.update(prior_executor_id=lease["metadata"]["annotations"]["lightyear.ai/executor"], executor_id=uuid.uuid4().hex,
                             lease_uid=lease["metadata"]["uid"])
                engine.save("before-recovery-takeover")
                engine.patch("lease", lease, [{"op": "add", "path": "/metadata/annotations/lightyear.ai~1executor", "value": state["executor_id"]},
                                               {"op": "add", "path": "/spec/holderIdentity", "value": state["run_id"]}])
                recovery = engine.recover()
            result.update(status="recovered-request-logging" if recovery["status"] == "restored" else "failed", recovery=recovery)
        else:
            engine.preflight()
            if args.action == "preflight":
                result.update(status="passed-request-logging-preflight", services=list(SERVICES), application_mutations=0)
            else:
                # Exercise both read APIs before any deployment change.
                telemetry = Telemetry(args.project)
                now = stamp()
                telemetry.trace(hashed(run_id)[:32])
                telemetry.logs(environment, hashed(run_id)[:32], now, now)
                print("MS67_LOG_CORRELATION_RECOVERY_STATE=" + state["recovery_uri"], flush=True)
                engine.install()
                observation = engine.observe(telemetry)
                verify_observation(sign(observation, key, args.signer), key)
                engine.save("before-release-installed")
                engine.release()
                state["cleanup_complete"] = True
                engine.save("installed-and-verified")
                uri = args.evidence_bucket + "/observations/" + run_id + "/" + OBSERVATION_FILE
                saved = Journal(output / OBSERVATION_FILE, uri, args.project, key, args.signer).write(observation)
                verify_observation(saved, key)
                print("MS67_LOG_CORRELATION_EVIDENCE_READBACK=VERIFIED", flush=True)
                print("MS67_LOG_CORRELATION_OBSERVATION=" + uri, flush=True)
                result = observation
    except (Exception, KeyboardInterrupt) as exc:
        recovery = {"status": "not-started", "errors": []}
        if engine and args.action in {"run", "recover"} and engine.s.get("phase") not in {"validated", "installed-and-verified", "before-release-installed", "restored"}:
            try:
                recovery = engine.recover()
            except (Exception, KeyboardInterrupt) as cleanup_exc:
                recovery = {"status": "recovery-required", "errors": [reason(cleanup_exc)]}
        elif engine and engine.s.get("phase") in {"installed-and-verified", "before-release-installed"}:
            recovery = {"status": "configuration-retained", "errors": []}
        result.update(status="failed", reason=reason(exc), recovery=recovery)
    finally:
        if runtime:
            for service in list(runtime.forwards):
                runtime.close_forward(service)
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, prior_signal)
    if output:
        (output / "log-correlation.result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"passed-request-logging-preflight", "passed-service-log-trace-correlation", "recovered-request-logging"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
