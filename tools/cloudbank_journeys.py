#!/usr/bin/env python3
"""Run shared journeys on an explicitly selected nonproduction GKE target."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
import time
import uuid

from lightyear_data.cloudbank_edge_ai import validate_execution_receipt
from lightyear_data.cloudbank_production_readiness import validate_image_lock
from lightyear_data.cloudbank_journeys import ACK, JourneyFailure, execute_journeys, require
from lightyear_data.cloudbank_journeys_gke import GkeRuntime, command
from lightyear_data.contracts import sign, verify_signature

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("action", choices=("preflight", "run", "recover"))
    root.add_argument("--project", default=os.environ.get("GCP_PROJECT_ID", ""))
    root.add_argument("--region", default=os.environ.get("GCP_REGION", ""))
    root.add_argument("--cluster", default=os.environ.get("GKE_CLUSTER_NAME", ""))
    root.add_argument("--namespace", default=os.environ.get("KUBERNETES_NAMESPACE", "cloudbank-ms67"))
    root.add_argument("--image-lock", type=Path)
    root.add_argument("--ms64-receipt", type=Path)
    root.add_argument("--probe-image", default=os.environ.get("MS67_POSTGRESQL_PROBE_IMAGE"))
    root.add_argument("--recovery-state", type=Path)
    root.add_argument("--output-root", type=Path)
    root.add_argument("--evidence-bucket", help="Private gs:// bucket or prefix; uploads bounded evidence on failure too")
    root.add_argument("--signer", required=True)
    root.add_argument("--evidence-key-secret", default="cloudbank-ms67-evidence-key")
    return root


def load(path: Path):
    require(path.stat().st_size <= 4 * 1024 * 1024, "input-file-too-large")
    value = json.loads(path.read_text())
    require(isinstance(value, dict), "input-object-required")
    return value


def write(path: Path, payload: dict):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def restore_state(runtime: GkeRuntime, state: dict, key: str):
    require(verify_signature(state, key), "recovery-state-signature-invalid")
    require(state.get("state_type") == "lightyear-cloudbank-journey-recovery"
            and state.get("context") == runtime.context and state.get("namespace") == runtime.namespace
            and state.get("images") == runtime.images and state.get("run_id") == runtime.run_id
            and state.get("probe_name") == runtime.probe_name, "recovery-state-identity-invalid")
    original, stopped = state.get("original_deployments"), state.get("stopped_services")
    require(isinstance(original, dict) and set(original) <= set(runtime.images)
            and all(isinstance(v, dict) and isinstance(v.get("uid"), str) and v.get("replicas") == 2
                    for v in original.values()) and isinstance(stopped, list)
            and all(s in original for s in stopped), "recovery-state-deployments-invalid")
    runtime.original = original
    # Validate all recorded owners/images before accepting mutation intent.
    for service in original:
        runtime.deployment(service)
    runtime.stopped = set(stopped)
    runtime.probe_uid = state.get("probe_uid")
    runtime.checks_delivery = state.get("checks_delivery")


class Heartbeat:
    def __init__(self):
        self.phase = "Validating inputs"
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def progress(self, message):
        self.phase = message
        print("[journeys] " + message, flush=True)

    def loop(self):
        while not self.done.wait(20):
            print(time.strftime("%H:%M:%S UTC", time.gmtime()) + " | " + self.phase, flush=True)


def main(argv=None):
    args = parser().parse_args(argv)
    runtime = None
    output = None
    key = ""
    upload_failed = False
    result = {"status": "failed", "ms65_complete": False, "ms66_complete": False, "ms67_complete": False}
    heartbeat = Heartbeat()
    heartbeat.thread.start()
    previous_term = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        require(bool(args.project and args.region and args.cluster), "explicit-gcp-context-required")
        if args.action in {"run", "recover"}:
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
        if args.action == "run":
            require(bool(args.probe_image), "approved-postgresql-probe-image-required")
        key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", "")
        if not key:
            require(bool(args.evidence_key_secret) and not args.evidence_key_secret.startswith("-"), "key-secret-required")
            key = command(["gcloud", "secrets", "versions", "access", "latest", "--secret", args.evidence_key_secret,
                           "--project", args.project]).strip()
        require(bool(key and args.signer.strip()), "signing-key-required")
        state = None
        if args.action == "recover":
            require(args.recovery_state is not None, "recovery-state-required")
            state = load(args.recovery_state)
            require(verify_signature(state, key), "recovery-state-signature-invalid")
            images, run_id = state["images"], state["run_id"]
            bindings = {}
        else:
            require(args.image_lock is not None, "image-lock-required")
            receipt = load(args.ms64_receipt or args.image_lock.parent / "cloudbank-edge-ai.receipt.json")
            require(not validate_execution_receipt(receipt, key, PROJECT_ROOT), "signed-current-ms64-receipt-required")
            image_lock = load(args.image_lock)
            require(not validate_image_lock(image_lock, receipt["content_sha256"]), "ms64-bound-image-lock-required")
            images = {row["service"]: row["reference"] for row in image_lock["images"]}
            run_id = "journeys-" + uuid.uuid4().hex
            bindings = {"ms64_receipt_sha256": receipt["content_sha256"],
                        "image_lock_sha256": image_lock["content_sha256"], "lane": "gke-postgresql-target"}
        output = args.output_root
        if output:
            output = output.resolve()
            require(not output.exists(), "fresh-output-directory-required")
            require(not output.is_relative_to(PROJECT_ROOT), "evidence-output-must-be-outside-checkout")
            output.mkdir(parents=True, mode=0o700)
        else:
            parent = Path.home() / "ms67-evidence"
            parent.mkdir(parents=True, exist_ok=True)
            output = Path(tempfile.mkdtemp(prefix="ms67-journeys.", dir=parent))
        runtime = GkeRuntime(project=args.project, region=args.region, cluster=args.cluster,
            namespace=args.namespace, images=images, run_id=run_id, output=output,
            probe_image=args.probe_image, progress=heartbeat.progress, signing_key=key, signer=args.signer)
        bindings["environment"] = runtime.environment()
        if args.action == "recover":
            restore_state(runtime, state, key)
            result = {"status": "recovered", "recovery": runtime.close(), "run_id": run_id}
            require(result["recovery"]["status"] == "restored", "runtime-restoration-failed")
        else:
            heartbeat.progress("Checking eight running image identities and HTTP readiness")
            ready = runtime.ready()
            heartbeat.progress("Checking all five OAuth roles")
            authorization = runtime.authorization_preflight()
            result = {"observation_type": "lightyear-cloudbank-journey-preflight", "run_id": run_id,
                "bindings": bindings, "services": ready, "authorization": authorization,
                "status": "preflight-passed" if all(r["status"] == "passed" for r in authorization.values()) else "failed",
                "ms65_complete": False, "ms66_complete": False, "ms67_complete": False}
            if args.action == "run" and result["status"] == "preflight-passed":
                heartbeat.progress("Starting read-only PostgreSQL queue probe")
                runtime.create_probe()
                result = execute_journeys(runtime, bindings, key, args.signer, run_id=run_id,
                    progress=heartbeat.progress, checkpoint=lambda value: write(output / "journeys.json", value))
    except (Exception, KeyboardInterrupt) as exc:
        result = {**result, "status": "failed", "reason": str(exc) if isinstance(exc, JourneyFailure)
                  else "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "operator-input-or-runtime-error"}
    finally:
        if runtime:
            try:
                recovery = runtime.close()
                result["recovery"] = recovery
                if recovery["status"] != "restored":
                    result["status"] = "failed"
            except Exception:
                result.update(status="failed", recovery={"status": "failed", "reason": "runtime-restoration-failed"})
        if output and key:
            result = sign(result, key, args.signer)
            write(output / "journeys.json", result)
            files = sorted(output.glob("*.json"))
            (output / "SHA256SUMS").write_text("".join(
                hashlib.sha256(path.read_bytes()).hexdigest() + "  ./" + path.name + "\n" for path in files))
            if args.evidence_bucket:
                heartbeat.progress("Saving bounded journey evidence to GCS")
                try:
                    require(args.evidence_bucket.startswith("gs://") and not any(c.isspace() for c in args.evidence_bucket),
                            "evidence-bucket-invalid")
                    command(["gcloud", "storage", "cp", *[str(p) for p in files], str(output / "SHA256SUMS"),
                        args.evidence_bucket.rstrip("/") + "/" + output.name + "/", "--project", args.project], timeout=180)
                    print("MS67_JOURNEYS_EVIDENCE_UPLOAD=PASSED", flush=True)
                except Exception:
                    print("MS67_JOURNEYS_EVIDENCE_UPLOAD=FAILED; local evidence retained", flush=True)
                    upload_failed = True
            print("MS67_JOURNEYS_ROOT=" + str(output), flush=True)
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, previous_term)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not upload_failed and result["status"] in {"preflight-passed", "passed-shared-journeys", "recovered"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
