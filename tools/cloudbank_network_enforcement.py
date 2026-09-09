#!/usr/bin/env python3
"""Execute, recover and independently verify the bounded MS67 network drill."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import uuid

from cloudbank_journeys import Heartbeat
from cloudbank_ms65_rehearsal import cluster_identity, evidence_key, load
from lightyear_data.cloudbank_edge_ai import validate_execution_receipt as validate_ms64
from lightyear_data.cloudbank_image_security import ImageJournal, save_observation
from lightyear_data.cloudbank_journeys import ACK, JourneyFailure, require
from lightyear_data.cloudbank_journeys_gke import GkeRuntime, command
from lightyear_data.cloudbank_network_enforcement import (
    Backend, INTENT, LABEL, LEASE, NetworkRun, OBSERVATION_FILE, STATE_FILE, STATE_TYPE,
    compiled_probe, verify_observation,
)
from lightyear_data.cloudbank_platform_qualification import validate_profile
from lightyear_data.cloudbank_production_readiness import validate_image_lock
from lightyear_data.contracts import content_hash, sign, verify_signature

ROOT = Path(__file__).resolve().parents[1]


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("action", choices=("run", "preflight", "recover", "verify"))
    for name in ("project", "region", "cluster", "namespace", "signer", "evidence-bucket"):
        root.add_argument("--" + name, required=True)
    for name in ("image-lock", "ms64-receipt", "platform-profile"):
        root.add_argument("--" + name, required=True, type=Path)
    for name in ("output-root", "observation", "recovery-state"):
        root.add_argument("--" + name, type=Path)
    root.add_argument("--source-instance", default="cloudbank-ms67-postgres")
    root.add_argument("--evidence-key-secret", default="cloudbank-ms67-evidence-key")
    root.add_argument("--original-process-stopped", action="store_true")
    return root


def verified_state(state, key, bindings, images, environment, profile):
    require(state.get("content_sha256") == content_hash(state) and verify_signature(state, key), "network-recovery-signature-invalid")
    run_id = state.get("run_id", "")
    require(state.get("state_type") == STATE_TYPE and re.fullmatch(r"ms67-network-[0-9a-f]{32}", run_id)
            and state.get("bindings") == bindings and state.get("images") == images
            and state.get("environment") == environment and state.get("credentials_persisted") is False
            and state.get("production_environment") is False, "network-recovery-identity-invalid")
    control, prefix = "ms67-net-" + run_id[-32:][:20], "ly-net-" + run_id[-32:][:12]
    resources = state.get("resources", [])
    require(isinstance(resources, list) and len(resources) <= 24, "network-recovery-resource-count-invalid")
    seen = set()
    for row in resources:
        obj = row["object"]
        kind, meta = obj["kind"], obj["metadata"]
        namespace, name = meta.get("namespace"), meta["name"]
        require(meta.get("labels", {}).get(LABEL) == run_id and meta.get("annotations", {}).get(INTENT)
                and (kind, namespace, name) not in seen, "network-recovery-ownership-invalid")
        seen.add((kind, namespace, name))
        if kind == "Namespace":
            require(namespace is None and name == control, "network-recovery-namespace-invalid")
        else:
            require(namespace in {environment["namespace"], profile["model_namespace"], control}, "network-recovery-scope-invalid")
            if kind == "Pod":
                require(name.startswith(prefix + "-") and obj["spec"]["containers"][0]["image"] == images["testrunner"],
                        "network-recovery-probe-invalid")
            else:
                require(kind in {"ConfigMap", "ServiceAccount", "NetworkPolicy"} and name == prefix
                        and (kind != "ServiceAccount" or namespace == control)
                        and (kind != "NetworkPolicy" or namespace == environment["namespace"]), "network-recovery-object-invalid")
    if state.get("lease_object"):
        lease = state["lease_object"]
        require(lease["kind"] == "Lease" and lease["metadata"]["name"] == LEASE
                and lease["metadata"]["namespace"] == environment["namespace"]
                and lease["spec"].get("holderIdentity") == run_id
                and lease["metadata"].get("labels", {}).get(LABEL) == run_id, "network-recovery-lock-invalid")


def reason(exc):
    return str(exc) if isinstance(exc, JourneyFailure) else (
        "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "network-input-or-runtime-error")


def error_type(exc):
    # Use fixed class names, never provider messages, exception arguments,
    # arbitrary subclass names, tracebacks or frame locals.
    for cls in (JourneyFailure, KeyboardInterrupt, AttributeError, KeyError,
                TypeError, ValueError, TimeoutError, OSError, RuntimeError):
        if isinstance(exc, cls):
            return cls.__name__
    return "Exception"


def failure_result(exc, engine, action):
    failed_phase = engine.s.get("phase") if engine else "before-run"
    recovery = {"status": "not-started", "errors": []}
    if engine and engine.s.get("lease_object") and action in {"run", "recover"}:
        try:
            recovery = engine.recover()
        except (Exception, KeyboardInterrupt) as cleanup:
            recovery = {"status": "recovery-required", "errors": [reason(cleanup)], "error_type": error_type(cleanup)}
    return {"status": "failed", "reason": reason(exc), "error_type": error_type(exc),
            "failed_phase": failed_phase, "recovery": recovery,
            "phase": engine.s.get("phase") if engine else "before-run",
            "failed_checks": engine.s.get("failed_checks", []) if engine else [],
            "resource_mismatches": engine.s.get("resource_mismatches", []) if engine else [],
            "ms67_complete": False, "production_ready": False}


def main(argv=None):
    args = parser().parse_args(argv)
    heartbeat, engine, output, key = Heartbeat(), None, None, None
    result = {"status": "failed", "ms67_complete": False, "production_ready": False}
    prior = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    heartbeat.thread.start()
    try:
        require(args.evidence_bucket == f"gs://{args.project}-ms67-evidence/network-enforcement", "network-private-evidence-prefix-required")
        require(re.fullmatch(r"[a-z][a-z0-9-]{0,62}", args.source_instance), "network-source-instance-invalid")
        if args.action in {"run", "recover"}:
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
        if args.action == "recover":
            require(args.original_process_stopped and args.recovery_state, "network-recovery-requires-original-process-stopped")
        key = evidence_key(args)
        lock, ms64, profile = map(load, (args.image_lock, args.ms64_receipt, args.platform_profile))
        require(not validate_ms64(ms64, key, ROOT) and not validate_image_lock(lock, ms64["content_sha256"])
                and not validate_profile(profile, key), "network-signed-inputs-invalid")
        artifact = compiled_probe(ROOT)
        images = {row["service"]: row["reference"] for row in lock["images"]}
        bindings = {"image_lock_sha256": lock["content_sha256"], "ms64_receipt_sha256": ms64["content_sha256"],
                    "platform_profile_sha256": profile["content_sha256"]}
        environment = {k: getattr(args, k) for k in ("project", "region", "cluster", "namespace")}
        if args.action == "verify":
            require(args.observation, "network-observation-required")
            verify_observation(load(args.observation), key, bindings, images, environment, artifact)
            print(json.dumps({"status": "passed", "errors": []}))
            return 0
        require(args.output_root, "network-fresh-output-root-required")
        output = args.output_root.resolve()
        require(not output.exists() and not output.is_relative_to(ROOT), "network-fresh-private-output-required")
        output.mkdir(mode=0o700, parents=True)
        run_id = "ms67-network-" + uuid.uuid4().hex
        runtime = GkeRuntime(**environment, images=images, run_id=run_id, output=output)
        environment = runtime.environment()
        namespace_uid = runtime.get("namespace", args.namespace)["metadata"]["uid"]
        require(profile["context"] == runtime.context and profile["namespace"] == args.namespace
                and profile["provider"] == "google-gke-standard-regional" and profile["region"] == args.region
                and profile["cluster_uid_sha256"] == cluster_identity(args.project, args.region, args.cluster)
                and profile["namespace_uid_sha256"] == hashlib.sha256(namespace_uid.encode()).hexdigest(),
                "network-profile-live-environment-mismatch")
        state = {"schema_version": "1.0", "state_type": STATE_TYPE, "run_id": run_id,
                 "environment": environment, "bindings": bindings, "images": images, "source_instance": args.source_instance,
                 "recovery_uri": args.evidence_bucket + "/" + run_id + "/" + STATE_FILE,
                 "resources": [], "lease_uid": None, "cleanup_complete": False, "phase": "validating",
                 "credentials_persisted": False, "raw_output_persisted": False, "production_environment": False}
        generation = "0"
        if args.action == "recover":
            local = load(args.recovery_state)
            verified_state(local, key, bindings, images, environment, profile)
            uri = args.evidence_bucket + "/" + local["run_id"] + "/" + STATE_FILE
            require(local.get("recovery_uri") == uri, "network-recovery-uri-invalid")
            generation = command(["gcloud", "storage", "objects", "describe", uri, "--project", args.project, "--format=value(generation)"]).strip()
            require(re.fullmatch(r"[1-9][0-9]*", generation), "network-recovery-generation-invalid")
            state = json.loads(command(["gcloud", "storage", "cat", uri + "#" + generation, "--project", args.project]))
            verified_state(state, key, bindings, images, environment, profile)
            require(state.get("run_id") == local["run_id"] and state.get("recovery_uri") == uri, "network-latest-checkpoint-mismatch")
            state = {k: v for k, v in state.items() if k not in {"content_sha256", "signature"}}
        journal = ImageJournal(output / STATE_FILE, state["recovery_uri"], args.project, key, args.signer, generation=generation)
        engine = NetworkRun(Backend(runtime), journal, state, profile, artifact, heartbeat.progress)
        print("MS67_NETWORK_ROOT=" + str(output), flush=True)
        print("MS67_NETWORK_RECOVERY_STATE=" + state["recovery_uri"], flush=True)
        if args.action == "preflight":
            engine.preflight()
            result = {**result, "status": "passed-network-preflight", "application_mutations": 0}
            save_observation(output / "network-enforcement.preflight.json", {**result, "baseline": state["baseline"]}, key, args.signer)
        elif args.action == "recover":
            result = {**result, "status": "recovered-network-probes", "recovery": engine.recover()}
            require(result["recovery"]["status"] == "restored", "network-recovery-incomplete")
        else:
            result = engine.run()
            verify_observation(sign(result, key, args.signer), key, bindings, images, environment, artifact)
            prefix = args.evidence_bucket + "/" + state["run_id"] + "/"
            saved = ImageJournal(output / OBSERVATION_FILE, prefix + OBSERVATION_FILE, args.project, key, args.signer).write(result)
            verify_observation(saved, key, bindings, images, environment, artifact)
            print("MS67_NETWORK_EVIDENCE_READBACK=VERIFIED", flush=True)
            print("MS67_NETWORK_OBSERVATION=" + prefix + OBSERVATION_FILE, flush=True)
        print(json.dumps({k: v for k, v in result.items() if k not in {"baseline", "final", "cases", "checks", "images"}}, indent=2, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        result = failure_result(exc, engine, args.action)
        if output and output.is_dir() and key:
            save_observation(output / "network-enforcement.result.json", result, key, args.signer)
        print(json.dumps(result, indent=2))
        return 1
    finally:
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, prior)


if __name__ == "__main__":
    raise SystemExit(main())
