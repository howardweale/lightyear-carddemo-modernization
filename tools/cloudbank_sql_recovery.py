#!/usr/bin/env python3
"""Run or recover an isolated Cloud SQL backup/PITR drill in nonproduction."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import uuid

from cloudbank_journeys import Heartbeat, load, restore_state
from lightyear_data.cloudbank_edge_ai import validate_execution_receipt
from lightyear_data.cloudbank_journeys import ACK, OBSERVATION_TYPE, SCENARIOS, JourneyFailure, hashed, journey_contract, require
from lightyear_data.cloudbank_journeys_gke import GkeRuntime
from lightyear_data.cloudbank_production_readiness import validate_image_lock
from lightyear_data.cloudbank_sql_recovery import SqlRecovery, STATE_TYPE, invoke, verified, write_signed

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("action", choices=("run", "recover"))
    root.add_argument("--project", default=os.environ.get("GCP_PROJECT_ID", ""))
    root.add_argument("--region", default=os.environ.get("GCP_REGION", ""))
    root.add_argument("--cluster", default=os.environ.get("GKE_CLUSTER_NAME", ""))
    root.add_argument("--namespace", default=os.environ.get("KUBERNETES_NAMESPACE", "cloudbank-ms67"))
    root.add_argument("--source-instance", default=os.environ.get("CLOUD_SQL_INSTANCE", ""))
    root.add_argument("--image-lock", type=Path)
    root.add_argument("--ms64-receipt", type=Path)
    root.add_argument("--journeys", type=Path, help="Previously verified journeys.json")
    root.add_argument("--probe-image", default=os.environ.get("MS67_POSTGRESQL_PROBE_IMAGE"))
    root.add_argument("--recovery-root", type=Path, help="Original output directory, for recover only")
    root.add_argument("--evidence-bucket", required=True)
    root.add_argument("--signer", required=True)
    root.add_argument("--evidence-key-secret", default="cloudbank-ms67-evidence-key")
    return root


def upload(output: Path, bucket: str, project: str):
    files = sorted(output.glob("*.json"))
    sums = output / "SHA256SUMS"
    sums.write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  ./" + p.name + "\n" for p in files))
    destination = bucket.rstrip("/") + "/" + output.name + "/"
    for attempt in range(3):
        try:
            invoke(["gcloud", "storage", "cp", *map(str, files), str(sums), destination,
                    "--project", project], timeout=600)
            with tempfile.TemporaryDirectory(prefix="ms67-sql-readback-") as directory:
                for path in [*files, sums]:
                    copied = Path(directory) / path.name
                    invoke(["gcloud", "storage", "cp", destination + path.name, str(copied),
                            "--project", project], timeout=180)
                    require(copied.read_bytes() == path.read_bytes(), "evidence-readback-mismatch")
            print("MS67_SQL_RECOVERY_EVIDENCE_UPLOAD=PASSED", flush=True)
            print("MS67_SQL_RECOVERY_READBACK=VERIFIED", flush=True)
            return
        except JourneyFailure:
            if attempt == 2:
                raise
            time.sleep(20)


def main(argv=None):
    args = parser().parse_args(argv)
    heartbeat = Heartbeat()
    heartbeat.thread.start()
    prior_term = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    output, result, key = None, None, ""
    try:
        require(bool(args.project and args.region and args.cluster and args.source_instance), "explicit-gcp-context-required")
        require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
        require(args.evidence_bucket.startswith("gs://") and not any(c.isspace() for c in args.evidence_bucket), "private-evidence-prefix-required")
        key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", "")
        if not key:
            key = invoke(["gcloud", "secrets", "versions", "access", "latest", "--secret", args.evidence_key_secret,
                          "--project", args.project]).strip()
        require(bool(key.strip() and args.signer.strip()), "signing-key-and-signer-required")
        state = None
        if args.action == "recover":
            require(args.recovery_root is not None, "original-recovery-root-required")
            output = args.recovery_root.resolve()
            state = verified(load(output / "sql-recovery-state.json"), key)
            journey_state = verified(load(output / "recovery-state.json"), key)
            require(state.get("state_type") == STATE_TYPE and state.get("source") == args.source_instance
                    and state.get("project") == args.project and state.get("region") == args.region
                    and state.get("namespace") == args.namespace
                    and state.get("context") == f"gke_{args.project}_{args.region}_{args.cluster}", "recovery-environment-mismatch")
            images, run_id, probe_image = state["images"], state["run_id"], state["probe_image"]
        else:
            require(args.image_lock is not None and args.journeys is not None and bool(args.probe_image), "bound-inputs-and-probe-required")
            receipt = load(args.ms64_receipt or args.image_lock.parent / "cloudbank-edge-ai.receipt.json")
            require(not validate_execution_receipt(receipt, key, PROJECT_ROOT), "signed-current-ms64-receipt-required")
            lock = load(args.image_lock)
            require(not validate_image_lock(lock, receipt["content_sha256"]), "ms64-bound-image-lock-required")
            journeys = verified(load(args.journeys), key)
            binding = journeys.get("bindings", {})
            rows = journeys.get("scenarios", [])
            require(journeys.get("observation_type") == OBSERVATION_TYPE
                    and journeys.get("status") == "passed-shared-journeys"
                    and len(rows) == len(SCENARIOS)
                    and {r.get("id") for r in rows} == {identifier for identifier, _ in SCENARIOS}
                    and all(r.get("status") == "passed" and r.get("evidence_sha256") == hashed(r.get("evidence")) for r in rows)
                    and binding.get("journey_contract_sha256") == journey_contract()["content_sha256"]
                    and journeys.get("recovery", {}).get("status") == "restored"
                    and binding.get("ms64_receipt_sha256") == receipt["content_sha256"]
                    and binding.get("image_lock_sha256") == lock["content_sha256"], "passed-bound-journeys-required")
            images = {row["service"]: row["reference"] for row in lock["images"]}
            run_id, probe_image = "sql-recovery-" + uuid.uuid4().hex, args.probe_image
            parent = Path.home() / "ms67-evidence"
            parent.mkdir(parents=True, exist_ok=True)
            output = Path(tempfile.mkdtemp(prefix="ms67-sql-recovery.", dir=parent))
        require(not output.is_relative_to(PROJECT_ROOT), "private-output-outside-checkout-required")
        runtime = GkeRuntime(project=args.project, region=args.region, cluster=args.cluster, namespace=args.namespace,
            images=images, run_id=run_id, output=output, probe_image=probe_image, progress=heartbeat.progress,
            signing_key=key, signer=args.signer)
        environment = runtime.environment()
        drill = SqlRecovery(runtime, args.source_instance, key, args.signer, state=state)
        if args.action == "recover":
            require(state.get("environment") == environment, "recovery-namespace-identity-mismatch")
            restore_state(runtime, journey_state, key)
            try:
                drill.restore_apps()
            finally:
                drill.cleanup()
            result = {"status": "recovered", "ms65_complete": False, "ms66_complete": False, "ms67_complete": False}
            write_signed(output / "cleanup-result.json", result, key, args.signer)
        else:
            require(binding.get("environment") == environment, "journey-deployment-environment-mismatch")
            drill.state["environment"] = environment
            drill.state["journeys_content_sha256"] = journeys["content_sha256"]
            drill.save()
            runtime.recovery_checkpoint()
            result = drill.execute()
        heartbeat.progress("Uploading and independently reading back signed database recovery evidence")
        upload(output, args.evidence_bucket, args.project)
    except (Exception, KeyboardInterrupt) as exc:
        message = str(exc) if isinstance(exc, JourneyFailure) else "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "input-or-runtime-error"
        print("MS67_SQL_RECOVERY_ERROR=" + message, flush=True)
        if result:
            print("Signed drill result retained locally; upload or cleanup remains incomplete.", flush=True)
        return 1
    finally:
        if output:
            print("MS67_SQL_RECOVERY_ROOT=" + str(output), flush=True)
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, prior_term)
    print(json.dumps(result, indent=2, sort_keys=True))
    passed = result.get("status") in {"passed-isolated-database-recovery", "recovered"}
    print("MS67_ISOLATED_SQL_RECOVERY=" + ("PASSED" if passed else "FAILED"), flush=True)
    print("Database recovery drill only; full MS65/MS66/MS67 qualification remains open.", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
