#!/usr/bin/env python3
"""Verify and scan the eight MS67 image digests without changing workloads."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import signal
import tempfile
import uuid

from cloudbank_journeys import Heartbeat
from cloudbank_ms65_rehearsal import cluster_identity, evidence_key, load
from lightyear_data.cloudbank_edge_ai import validate_execution_receipt as validate_ms64
from lightyear_data.cloudbank_image_security import (
    CheckpointFailure, ImageJournal, ImageScanner, OBSERVATION_TYPE, OBSERVATION_FILE, PASS,
    save_observation, signing_public_key, stamp, verify_checkpoint, verify_observation,
)
from lightyear_data.cloudbank_journeys import JourneyFailure, SERVICES, hashed, require
from lightyear_data.cloudbank_journeys_gke import GkeRuntime
from lightyear_data.cloudbank_platform_qualification import validate_profile
from lightyear_data.cloudbank_production_readiness import validate_image_lock
from lightyear_data.contracts import sign


ROOT = Path(__file__).resolve().parents[1]


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=("run", "finalize", "verify"))
    for field in ("project", "region", "cluster", "namespace", "signer", "evidence-bucket", "build-source-commit"):
        result.add_argument("--" + field, required=True)
    for field in ("image-lock", "ms64-receipt", "platform-profile"):
        result.add_argument("--" + field, type=Path, required=True)
    for field in ("output-root", "observation"):
        result.add_argument("--" + field, type=Path)
    result.add_argument("--evidence-key-secret", default="cloudbank-ms67-evidence-key")
    result.add_argument("--artifact-repository", default="cloudbank-ms67")
    return result


def live_snapshot(runtime):
    live, specs = {}, {}
    for service in SERVICES:
        live[service] = runtime.service_ready(service)
        deployment = runtime.deployment(service)
        specs[service] = hashed({"uid": deployment["metadata"]["uid"], "spec": deployment["spec"]})
    return live, specs


def main(argv=None):
    args = parser().parse_args(argv)
    heartbeat = Heartbeat()
    heartbeat.thread.start()
    previous = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    observation = {"schema_version": "1.0", "observation_type": OBSERVATION_TYPE, "status": "failed",
                   "application_mutations": 0, "credentials_persisted": False, "raw_output_persisted": False,
                   "production_environment": False, "ms67_complete": False, "production_ready": False}
    journal, output, key, uri, phase = None, None, "", None, "input-validation"
    try:
        require(args.evidence_bucket == f"gs://{args.project}-ms67-evidence/image-security",
                "image-security-private-evidence-prefix-required")
        require(re.fullmatch(r"[0-9a-f]{40}", args.build_source_commit), "image-security-full-source-commit-required")
        key = evidence_key(args)
        lock, ms64, profile = map(load, (args.image_lock, args.ms64_receipt, args.platform_profile))
        require(not validate_ms64(ms64, key, ROOT), "image-security-current-signed-ms64-required")
        require(not validate_image_lock(lock, ms64["content_sha256"]), "image-security-bound-image-lock-required")
        require(not validate_profile(profile, key), "image-security-signed-platform-profile-required")
        images = {row["service"]: row["reference"] for row in lock["images"]}
        registry = f"{args.region}-docker.pkg.dev/{args.project}/{args.artifact_repository}/"
        require(all(re.fullmatch(re.escape(registry + service) + r"@sha256:[0-9a-f]{64}", images[service])
                    for service in SERVICES), "image-security-current-project-registry-required")
        bindings = {"image_lock_sha256": lock["content_sha256"], "ms64_receipt_sha256": ms64["content_sha256"],
                    "platform_profile_sha256": profile["content_sha256"]}
        explicit_environment = {k: getattr(args, k) for k in ("project", "region", "cluster", "namespace")}
        if args.action == "verify":
            require(args.observation is not None, "image-security-observation-required")
            verify_observation(load(args.observation), key, images, bindings, args.build_source_commit, explicit_environment, profile)
            print(json.dumps({"status": "passed", "errors": []}))
            return 0
        prior = None
        if args.action == "finalize":
            phase = "checkpoint-validation"
            require(args.observation is not None, "image-security-observation-required")
            prior = load(args.observation)
            verify_checkpoint(prior, key, images, bindings, args.build_source_commit,
                              explicit_environment, profile, at=stamp())
        run_id = "ms67-images-" + uuid.uuid4().hex
        output = args.output_root or Path.home() / "ms67-evidence" / run_id
        output = output.resolve()
        require(not output.exists() and not output.is_relative_to(ROOT), "image-security-fresh-private-output-required")
        output.mkdir(parents=True, mode=0o700)
        print("MS67_IMAGE_SECURITY_ROOT=" + str(output), flush=True)
        uri = args.evidence_bucket + "/" + run_id + "/" + OBSERVATION_FILE
        observation.update(run_id=run_id, started_at=stamp(), images=images, bindings=bindings,
                           source_commit=args.build_source_commit, services=[], live={}, status="in-progress")
        if prior is not None:
            observation.update({k: copy.deepcopy(prior[k]) for k in (
                "started_at", "services", "tools", "verification_key", "deployment_specs_before")})
            observation.update(scan_checkpoint=prior, finalization_started_at=stamp(),
                               live={"before": copy.deepcopy(prior["live"]["before"])})
        runtime = GkeRuntime(project=args.project, region=args.region, cluster=args.cluster,
                             namespace=args.namespace, images=images, run_id=run_id, output=output)
        phase = "live-input-validation"
        heartbeat.progress("Checking the current signed inputs, namespace and eight deployed image identities")
        environment = runtime.environment()
        cluster = cluster_identity(args.project, args.region, args.cluster)
        ns_uid = runtime.get("namespace", args.namespace)["metadata"]["uid"]
        require(profile["context"] == runtime.context and profile["namespace"] == args.namespace
                and profile["region"] == args.region and profile["provider"] == "google-gke-standard-regional"
                and profile["cluster_uid_sha256"] == cluster
                and profile["namespace_uid_sha256"] == hashlib.sha256(ns_uid.encode()).hexdigest(),
                "image-security-profile-live-environment-mismatch")
        observation.update(environment=environment, cluster_identity_sha256=cluster,
                           profile_namespace_uid_sha256=hashlib.sha256(ns_uid.encode()).hexdigest())
        journal = ImageJournal(output / OBSERVATION_FILE, uri, args.project, key, args.signer)
        if prior is not None:
            require(environment == prior["environment"], "image-security-checkpoint-live-environment-mismatch")
            phase = "finalization-key-check"
            heartbeat.progress("Validating the complete signed scan checkpoint and current image signing key")
            _, observation["finalization_key"] = signing_public_key(args.project, args.region)
            require(observation["finalization_key"] == prior["verification_key"],
                    "image-security-checkpoint-signing-key-changed")
        else:
            observation["live"]["before"], observation["deployment_specs_before"] = live_snapshot(runtime)
            phase = "initial-evidence-checkpoint"
            journal.write(observation)
            # Raw scanner data and temporary public/config/cache files never enter the evidence bundle.
            with tempfile.TemporaryDirectory(prefix="ms67-image-scanner-") as workspace:
                scanner = ImageScanner(args.project, args.region, Path(workspace))
                phase = "tools-and-public-key"
                heartbeat.progress("Checking Cosign, Trivy and the configured KMS image signing public key")
                observation["tools"], observation["verification_key"] = scanner.prepare()
                phase = "tools-evidence-checkpoint"
                journal.write(observation)
                for index, service in enumerate(SERVICES, 1):
                    row = {"service": service, "image": images[service], "status": "in-progress"}
                    observation["services"].append(row)
                    for operation in ("signature", "provenance", "scan"):
                        phase = service + "-" + operation
                        heartbeat.progress(f"Image {index}/8: {service}, {operation}")
                        if operation == "signature":
                            row[operation] = scanner.signature(row["image"])
                        elif operation == "provenance":
                            row[operation] = scanner.provenance(row["image"], service, args.build_source_commit)
                        else:
                            row[operation] = scanner.scan(row["image"])
                        phase += "-checkpoint"
                        journal.write(observation)
                    row["status"] = "findings" if row["scan"]["high"] or row["scan"]["critical"] else "passed"
                    print(f"MS67_IMAGE={service} HIGH={row['scan']['high']} CRITICAL={row['scan']['critical']}", flush=True)
                    phase = service + "-checkpoint"
                    journal.write(observation)
        phase = "final-live-binding-check"
        heartbeat.progress("Rechecking the deployed image identities and saving the signed result")
        observation["live"]["after"], observation["deployment_specs_after"] = live_snapshot(runtime)
        require(runtime.environment() == environment and cluster_identity(args.project, args.region, args.cluster) == cluster
                and observation["deployment_specs_before"] == observation["deployment_specs_after"],
                "image-security-live-environment-or-deployment-drift")
        observation["finished_at"] = stamp()
        require(all(row["status"] == "passed" for row in observation["services"]),
                "image-security-high-or-critical-findings")
        observation["status"] = PASS
        verify_observation(sign(observation, key, args.signer), key, images, bindings,
                           args.build_source_commit, explicit_environment, profile)
        phase = "final-evidence-checkpoint"
        observation = journal.write(observation)
        print("MS67_IMAGE_SECURITY_EVIDENCE_READBACK=VERIFIED", flush=True)
        print("MS67_IMAGE_SECURITY_OBSERVATION=" + uri, flush=True)
    except (Exception, KeyboardInterrupt) as exc:
        reason = str(exc) if isinstance(exc, JourneyFailure) else (
            "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "image-security-input-or-runtime-error")
        observation.update(status="failed", reason=reason, failed_phase=phase, finished_at=stamp())
        if output and key:
            # An ambiguous checkpoint must not be overwritten with a new payload.
            # The signed local failure remains available for bounded finalization.
            if isinstance(exc, CheckpointFailure):
                observation["evidence_upload"] = "unconfirmed"
            elif journal:
                try:
                    observation = journal.write(observation)
                    print("MS67_IMAGE_SECURITY_EVIDENCE_READBACK=VERIFIED", flush=True)
                except Exception:
                    observation["evidence_upload"] = "unconfirmed"
            observation = save_observation(output / OBSERVATION_FILE, observation, key, args.signer)
    finally:
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, previous)
    print(json.dumps(observation, indent=2, sort_keys=True))
    return 0 if observation.get("status") == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
