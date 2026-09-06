#!/usr/bin/env python3
"""Preflight, execute, or recover one nonproduction Cloud SQL HA failover drill."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile
import uuid

from cloudbank_journeys import Heartbeat, load, restore_state
from cloudbank_sql_recovery import load_bound_inputs, upload
from lightyear_data.cloudbank_journeys import ACK, require
from lightyear_data.cloudbank_sql_ha import EVIDENCE_FILES, HaRuntime, SqlHa, reason
from lightyear_data.cloudbank_sql_recovery import invoke, verified, write_signed

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def executor_digests():
    paths = ("tools/cloudbank_sql_ha.py", "tools/cloudbank_sql_recovery.py", "tools/cloudbank_journeys.py",
             "src/lightyear_data/cloudbank_sql_ha.py", "src/lightyear_data/cloudbank_sql_recovery.py",
             "src/lightyear_data/cloudbank_journeys.py", "src/lightyear_data/cloudbank_journeys_gke.py")
    return {name: hashlib.sha256((PROJECT_ROOT / name).read_bytes()).hexdigest() for name in paths}


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("action", choices=("preflight", "run", "recover"))
    for flag, variable, default in (("project", "GCP_PROJECT_ID", ""), ("region", "GCP_REGION", ""),
            ("cluster", "GKE_CLUSTER_NAME", ""), ("namespace", "KUBERNETES_NAMESPACE", "cloudbank-ms67"),
            ("source-instance", "CLOUD_SQL_INSTANCE", "")):
        root.add_argument("--" + flag, default=os.environ.get(variable, default))
    root.add_argument("--image-lock", type=Path)
    root.add_argument("--ms64-receipt", type=Path)
    root.add_argument("--journeys", type=Path)
    root.add_argument("--probe-image", default=os.environ.get("MS67_POSTGRESQL_PROBE_IMAGE"))
    root.add_argument("--recovery-root", type=Path)
    root.add_argument("--evidence-bucket", required=True)
    root.add_argument("--signer", required=True)
    root.add_argument("--evidence-key-secret", default="cloudbank-ms67-evidence-key")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    heartbeat = Heartbeat()
    heartbeat.thread.start()
    prior_term = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    output, result = None, None
    try:
        require(bool(args.project and args.region and args.cluster and args.source_instance), "explicit-gcp-context-required")
        if args.action != "preflight":
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
        require(args.evidence_bucket.startswith("gs://") and not any(c.isspace() for c in args.evidence_bucket),
                "private-evidence-prefix-required")
        key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", "")
        if not key:
            key = invoke(["gcloud", "secrets", "versions", "access", "latest", "--secret", args.evidence_key_secret,
                          "--project", args.project]).strip()
        require(bool(key.strip() and args.signer.strip()), "signing-key-and-signer-required")
        state = None
        if args.action == "recover":
            require(args.recovery_root is not None, "original-recovery-root-required")
            output = args.recovery_root.resolve()
            state = verified(load(output / "sql-ha-state.json"), key)
            journey_state = verified(load(output / "recovery-state.json"), key)
            require(journey_state.get("stopped_services") == [] and journey_state.get("checks_delivery") is None,
                    "ha-recovery-must-not-contain-app-mutations")
            images, run_id, probe_image = state["images"], state["run_id"], state["probe_image"]
        else:
            require(args.recovery_root is None, "use-recover-for-existing-evidence")
            receipt, lock, journeys, images, binding = load_bound_inputs(args, key)
            run_id, probe_image = "sql-ha-" + uuid.uuid4().hex, args.probe_image
            parent = Path.home() / "ms67-evidence"
            parent.mkdir(parents=True, exist_ok=True)
            output = Path(tempfile.mkdtemp(prefix="ms67-sql-ha.", dir=parent))
        require(not output.is_relative_to(PROJECT_ROOT), "private-output-outside-checkout-required")
        runtime = HaRuntime(project=args.project, region=args.region, cluster=args.cluster, namespace=args.namespace,
            images=images, run_id=run_id, output=output, probe_image=probe_image, progress=heartbeat.progress,
            signing_key=key, signer=args.signer)
        drill = SqlHa(runtime, args.source_instance, key, args.signer, state=state)
        environment = runtime.environment()
        if args.action == "recover":
            require(state.get("bindings", {}).get("environment") == environment, "recovery-namespace-identity-mismatch")
            restore_state(runtime, journey_state, key)
            recovery = drill.cleanup(observe_operation=True)
            result = {"observation_type": "lightyear-cloudbank-sql-ha-cleanup", "run_id": run_id,
                "status": "recovered" if recovery["status"] == "restored" else "failed", "recovery": recovery,
                "executor_digests": executor_digests(),
                "original_drill_result_unchanged": True, "ms65_complete": False, "ms66_complete": False, "ms67_complete": False}
            write_signed(output / "ha-cleanup.json", result, key, args.signer)
        else:
            require(binding.get("environment") == environment, "journey-deployment-environment-mismatch")
            drill.state["bindings"] = {"environment": environment, "ms64_receipt_sha256": receipt["content_sha256"],
                "image_lock_sha256": lock["content_sha256"], "journeys_content_sha256": journeys["content_sha256"],
                "executor_digests": executor_digests()}
            drill.save()
            runtime.recovery_checkpoint()
            result = drill.execute(preflight_only=args.action == "preflight")
        heartbeat.progress("Uploading and independently reading back signed HA evidence")
        upload(output, args.evidence_bucket, args.project, marker="MS67_SQL_HA", file_names=EVIDENCE_FILES)
    except (Exception, KeyboardInterrupt) as exc:
        print("MS67_SQL_HA_ERROR=" + reason(exc), flush=True)
        if result:
            print("Signed result retained locally; evidence upload or recovery remains incomplete.", flush=True)
        return 1
    finally:
        if output:
            print("MS67_SQL_HA_ROOT=" + str(output), flush=True)
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, prior_term)
    print(json.dumps(result, indent=2, sort_keys=True))
    passed = result.get("status") in {"preflight-passed", "passed-cloud-sql-ha-failover", "recovered"}
    print("MS67_SQL_HA_" + args.action.upper() + "=" + ("PASSED" if passed else "FAILED"), flush=True)
    print("Controlled Cloud SQL HA drill only; PITR timing and full MS65/MS66/MS67 qualification remain open.", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
