#!/usr/bin/env python3
"""Execute or recover the durable MS65 GKE deployment rehearsal."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import tempfile
import time
import uuid

from cloudbank_journeys import Heartbeat
from lightyear_data.cloudbank_edge_ai import validate_execution_receipt as validate_ms64_receipt
from lightyear_data.cloudbank_journeys import ACK, JourneyFailure, require
from lightyear_data.cloudbank_journeys_gke import GkeRuntime, command
from lightyear_data.cloudbank_ms65_rehearsal_gke import (
    CANARY_NAME,
    CANARY_SERVICE,
    DurableJournal,
    Ms65GkeRehearsal,
    STATE_TYPE,
    build_observation,
    validate_database_recovery,
    validate_shared_journeys,
    verified,
)
from lightyear_data.cloudbank_production_readiness import (
    RECEIPT_NAME,
    cutover_contract,
    execute_rehearsal,
    render_deployment_bundle,
    validate_artifacts,
    validate_edge_source,
    validate_environment,
    validate_execution_receipt,
    validate_image_lock,
)
from lightyear_data.contracts import sign


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("action", choices=("run", "recover"))
    root.add_argument("--project", default=os.environ.get("GCP_PROJECT_ID", ""))
    root.add_argument("--region", default=os.environ.get("GCP_REGION", ""))
    root.add_argument("--cluster", default=os.environ.get("GKE_CLUSTER_NAME", ""))
    root.add_argument("--namespace", default=os.environ.get("GKE_NAMESPACE", "cloudbank-ms67"))
    root.add_argument("--source-root", type=Path)
    root.add_argument("--image-lock", type=Path)
    root.add_argument("--ms64-receipt", type=Path)
    root.add_argument("--environment", type=Path)
    root.add_argument("--journeys", type=Path)
    root.add_argument("--database-recovery", type=Path)
    root.add_argument("--recovery-state", type=Path)
    root.add_argument("--output-root", type=Path)
    root.add_argument("--evidence-bucket", required=True)
    root.add_argument("--signer", required=True)
    root.add_argument("--evidence-key-secret", default="cloudbank-ms67-evidence-key")
    root.add_argument("--run-id")
    return root


def load(path: Path) -> dict:
    require(path.is_file() and path.stat().st_size <= 4 * 1024 * 1024, "bounded-input-file-required")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise JourneyFailure("input-json-invalid") from None
    require(isinstance(value, dict), "input-json-object-required")
    return value


def write_signed(path: Path, value: dict, key: str, signer: str) -> None:
    payload = sign(value, key, signer)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def upload(output: Path, bucket: str, project: str) -> None:
    files = sorted(output.glob("*.json"))
    require(bool(files), "ms65-evidence-files-required")
    sums = output / "SHA256SUMS"
    sums.write_text("".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  ./" + path.name + "\n"
                            for path in files))
    destination = bucket.rstrip("/") + "/" + output.name + "/"
    for attempt in range(3):
        try:
            command(["gcloud", "storage", "cp", *map(str, files), str(sums), destination,
                     "--project", project], timeout=600)
            with tempfile.TemporaryDirectory(prefix="ms65-readback-") as directory:
                for path in [*files, sums]:
                    copied = Path(directory) / path.name
                    command(["gcloud", "storage", "cp", destination + path.name, str(copied),
                             "--project", project], timeout=180)
                    require(copied.read_bytes() == path.read_bytes(), "ms65-evidence-readback-mismatch")
            print("MS65_REHEARSAL_EVIDENCE_UPLOAD=PASSED", flush=True)
            print("MS65_REHEARSAL_READBACK=VERIFIED", flush=True)
            return
        except JourneyFailure:
            if attempt == 2:
                raise
            time.sleep(20)


def output_root(candidate: Path | None, run_id: str) -> Path:
    if candidate:
        result = candidate.resolve()
        require(not result.exists(), "fresh-output-directory-required")
        result.mkdir(parents=True, mode=0o700)
        return result
    parent = Path.home() / "ms67-evidence"
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="ms65-rehearsal.", dir=parent))


def cluster_identity(project: str, region: str, cluster: str) -> str:
    raw = command([
        "gcloud", "container", "clusters", "describe", cluster,
        "--region", region, "--project", project,
        "--format=json(name,location,selfLink,endpoint,currentMasterVersion)",
    ]).rstrip("\n")
    return hashlib.sha256(raw.encode()).hexdigest()


def evidence_key(args) -> str:
    key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", "")
    if not key:
        key = command(["gcloud", "secrets", "versions", "access", "latest",
                       "--secret", args.evidence_key_secret, "--project", args.project]).strip()
    require(bool(key and args.signer.strip()), "signing-key-and-signer-required")
    return key


def ready_without_forwards(runtime: GkeRuntime) -> dict:
    try:
        return runtime.ready()
    finally:
        for service in list(runtime.forwards):
            try:
                runtime.close_forward(service)
            except Exception:
                pass


def clear_runtime_credentials(runtime: GkeRuntime) -> None:
    runtime.tokens.clear()
    runtime.credentials.clear()
    runtime.owner = ""


def recover(args, key: str, output: Path, heartbeat: Heartbeat) -> dict:
    require(args.recovery_state is not None, "recovery-state-required")
    state = verified(load(args.recovery_state), key, "ms65-recovery-state-signature-invalid")
    require(state.get("state_type") == STATE_TYPE
            and state.get("context") == f"gke_{args.project}_{args.region}_{args.cluster}"
            and state.get("namespace") == args.namespace, "ms65-recovery-environment-mismatch")
    runtime = GkeRuntime(project=args.project, region=args.region, cluster=args.cluster,
                         namespace=args.namespace, images=state["images"], run_id=state["run_id"],
                         output=output, progress=heartbeat.progress, signing_key=key, signer=args.signer)
    destination = args.evidence_bucket.rstrip("/") + "/" + output.name + "/ms65-recovery-state.json"
    journal = DurableJournal(output / "ms65-recovery-state.json", key, args.signer, destination,
                             project=args.project)
    # Environment, bundle and manifest are unused by cleanup; retain explicit
    # constructor inputs rather than weakening the run-time class invariants.
    rehearsal = Ms65GkeRehearsal(runtime, {}, {}, "", key, args.signer, journal)
    required_states = cutover_contract()["required_state_sequence"]
    observed_states = state.get("cutover_states") or []
    require(
        state.get("service") == CANARY_SERVICE
        and state.get("canary_name") == CANARY_NAME
        and state.get("canary_label") == rehearsal.canary_label
        and state.get("original_selector") in (None, {"app.kubernetes.io/name": CANARY_SERVICE})
        and isinstance(observed_states, list)
        and observed_states == required_states[:len(observed_states)],
        "ms65-recovery-state-contract-invalid",
    )
    rehearsal.state = state
    heartbeat.progress("Restoring the saved service selector and removing the owned canary")
    cleanup = rehearsal.cleanup()
    require(cleanup["status"] == "restored", "ms65-recovery-failed")
    ready_without_forwards(runtime)
    rehearsal.save("recovery-verified")
    write_signed(output / "ms65-cleanup.json", {
        "schema_version": "1.0", "status": "restored", "source_state_sha256": state["content_sha256"],
        "cleanup": cleanup, "ms65_complete": False, "ms66_complete": False, "ms67_complete": False,
    }, key, args.signer)
    return {"status": "recovered", "cleanup": cleanup}


def execute(args, key: str, output: Path, heartbeat: Heartbeat) -> dict:
    required = (args.source_root, args.image_lock, args.ms64_receipt, args.environment,
                args.journeys, args.database_recovery)
    require(all(item is not None for item in required), "ms65-run-inputs-required")
    source_root = args.source_root.resolve()
    require(source_root.is_dir(), "pinned-source-root-required")
    require(not source_root.is_relative_to(PROJECT_ROOT), "source-root-outside-controller-required")
    require(not validate_artifacts(PROJECT_ROOT), "ms65-controller-artifacts-invalid")
    require(not validate_edge_source(source_root), "pinned-cloudbank-source-invalid")
    ms64, lock, environment, journeys, database = map(load, (
        args.ms64_receipt, args.image_lock, args.environment, args.journeys, args.database_recovery,
    ))
    require(not validate_ms64_receipt(ms64, key, PROJECT_ROOT), "signed-current-ms64-receipt-required")
    require(not validate_image_lock(lock, ms64["content_sha256"]), "ms64-bound-image-lock-required")
    require(not validate_environment(environment), "valid-ms65-environment-required")
    require(environment["namespace"] == args.namespace
            and environment["cluster_identity_sha256"] == cluster_identity(args.project, args.region, args.cluster),
            "ms65-live-environment-binding-invalid")
    images = {row["service"]: row["reference"] for row in lock["images"]}
    run_id = args.run_id or "ms65-" + uuid.uuid4().hex
    runtime = GkeRuntime(project=args.project, region=args.region, cluster=args.cluster,
                         namespace=args.namespace, images=images, run_id=run_id, output=output,
                         progress=heartbeat.progress, signing_key=key, signer=args.signer)
    live_environment = runtime.environment()
    journey_summary = validate_shared_journeys(
        journeys, key, ms64_sha256=ms64["content_sha256"],
        image_lock_sha256=lock["content_sha256"], environment=live_environment,
    )
    backup_restore = validate_database_recovery(
        database, key, images=images, environment=live_environment,
        journeys_sha256=journeys["content_sha256"],
    )
    manifest, bundle = render_deployment_bundle(lock, environment, ms64["content_sha256"])
    destination = args.evidence_bucket.rstrip("/") + "/" + output.name + "/ms65-recovery-state.json"
    journal = DurableJournal(output / "ms65-recovery-state.json", key, args.signer, destination,
                             project=args.project)
    rehearsal = Ms65GkeRehearsal(runtime, environment, bundle, manifest, key, args.signer, journal)
    cleanup = {"status": "not-required", "errors": []}
    try:
        rehearsal.save("admitted")
        heartbeat.progress("Checking all five current OAuth role bindings before mutation")
        authorization = runtime.authorization_preflight()
        require(all(row.get("status") == "passed" for row in authorization.values())
                and len(authorization) == 5, "ms65-authorization-preflight-failed")
        heartbeat.progress("Validating the live MS65 deployment controls and eight locked rollouts")
        controls, rollouts = rehearsal.inspect_controls(ms64["content_sha256"], lock["content_sha256"])
        rehearsal.save("backup-verified")
        heartbeat.progress("Creating an isolated CreditScore canary from the locked image")
        canary = rehearsal.create_canary()
        rehearsal.save("smoke-passed")
        heartbeat.progress("Switching CreditScore service traffic to the isolated canary")
        traffic = rehearsal.switch_to_canary()
        business = {"authorization": authorization, "credit_contract": rehearsal.credit_check()}
        rehearsal.save("business-checks-passed")
        heartbeat.progress("Measuring the 60-second, 100-request business SLO window")
        slo = rehearsal.measure_slo()
        heartbeat.progress("Rolling service traffic back to the original two replicas")
        rollback = rehearsal.rollback()
        cleanup = rehearsal.cleanup()
        require(cleanup["status"] == "restored", "ms65-runtime-restoration-failed")
        ready_without_forwards(runtime)
        clear_runtime_credentials(runtime)
        rehearsal.save("recovered")
        observation, details = build_observation(
            ms64_sha256=ms64["content_sha256"], image_lock_sha256=lock["content_sha256"],
            environment=environment, bundle=bundle, control_details=controls, rollouts=rollouts,
            journeys=journey_summary, backup_restore=backup_restore, canary=canary,
            traffic=traffic, business=business, rollback=rollback, slo=slo,
            cutover_states=rehearsal.state["cutover_states"], key=key, signer=args.signer,
        )
        (output / "ms65-rehearsal.observation.json").write_text(
            json.dumps(observation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (output / "ms65-rehearsal.details.json").write_text(
            json.dumps(details, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        heartbeat.progress("Admitting the signed live observation into the MS65 contract")
        admission = output.parent / (output.name + "-admission")
        receipt = execute_rehearsal(
            PROJECT_ROOT, source_root, ms64, lock, environment, observation,
            admission, key, args.signer, run_id,
        )
        require(not validate_execution_receipt(receipt, key, PROJECT_ROOT), "ms65-receipt-verification-failed")
        shutil.copy2(admission / RECEIPT_NAME, output / RECEIPT_NAME)
        return {"status": "passed-ms65-rehearsal", "run_id": run_id,
                "receipt": receipt["content_sha256"], "observation": observation["content_sha256"],
                "cleanup": cleanup}
    except BaseException:
        cleanup = rehearsal.cleanup()
        clear_runtime_credentials(runtime)
        raise


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    heartbeat = Heartbeat()
    heartbeat.thread.start()
    prior_term = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    output = None
    result = {"status": "failed"}
    key = ""
    try:
        require(bool(args.project and args.region and args.cluster and args.namespace), "explicit-gcp-context-required")
        require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
        require(args.evidence_bucket.startswith("gs://") and not any(char.isspace() for char in args.evidence_bucket),
                "private-evidence-prefix-required")
        key = evidence_key(args)
        run_id = args.run_id or ("recover-" + uuid.uuid4().hex if args.action == "recover" else "ms65-" + uuid.uuid4().hex)
        output = output_root(args.output_root, run_id)
        require(not output.is_relative_to(PROJECT_ROOT), "private-output-outside-checkout-required")
        result = recover(args, key, output, heartbeat) if args.action == "recover" else execute(args, key, output, heartbeat)
    except (Exception, KeyboardInterrupt) as exc:
        reason = str(exc) if isinstance(exc, JourneyFailure) else (
            "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "input-or-runtime-error")
        result = {"status": "failed", "reason": reason,
                  "ms65_complete": False, "ms66_complete": False, "ms67_complete": False}
        if output and key:
            write_signed(output / "ms65-rehearsal.failure.json", result, key, args.signer)
    finally:
        if output and key:
            try:
                heartbeat.progress("Uploading and independently reading back bounded MS65 evidence")
                upload(output, args.evidence_bucket, args.project)
            except Exception:
                result["status"] = "failed"
                result["reason"] = "ms65-evidence-upload-or-readback-failed"
            print("MS65_REHEARSAL_ROOT=" + str(output), flush=True)
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, prior_term)
    print(json.dumps(result, indent=2, sort_keys=True))
    passed = result.get("status") in {"passed-ms65-rehearsal", "recovered"}
    marker = "MS65_REHEARSAL_RECOVERY" if args.action == "recover" else "MS65_REHEARSAL_RUN"
    print(marker + "=" + ("PASSED" if passed else "FAILED"), flush=True)
    print("MS65 rehearsal only; MS66 and MS67 remain open.", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
