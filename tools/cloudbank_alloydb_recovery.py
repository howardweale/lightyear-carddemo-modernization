#!/usr/bin/env python3
"""Run or verify the explicitly bound nonproduction AlloyDB recovery drill."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cloudbank_journeys import Heartbeat
from lightyear_data.cloudbank_alloydb_recovery import AlloyRecovery, verify_recovery
from lightyear_data.cloudbank_journeys import ACK, require
from lightyear_data.cloudbank_journeys_gke import command
from lightyear_data.cloudbank_managed_target import ManagedGkeRuntime
from lightyear_data.cloudbank_ms71 import verify_receipt
from lightyear_data.cloudbank_secret_rotation_gke import Journal
from lightyear_data.cloudbank_sql_recovery import verified


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "verify"))
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--ms71-receipt", required=True, type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--observation", type=Path)
    args = parser.parse_args(argv)
    context = json.loads(args.context.read_bytes())
    key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY") or command([
        "gcloud", "--quiet", "--project=" + context["project"], "secrets", "versions", "access", "latest",
        "--secret=cloudbank-ms67-evidence-key"]).strip()
    verified(context, key)
    require(context.get("context_type") == "lightyear-alloydb-platform-campaign"
            and context.get("production_environment") is False
            and context["profile"]["mutating_drills_authorized"] is True, "authorized-alloydb-context-required")
    receipt = json.loads(args.ms71_receipt.read_bytes())
    verify_receipt(receipt, key, ROOT)
    require(receipt["content_sha256"] == context["ms71_receipt_sha256"]
            and any(c["content_sha256"] == context["alloydb_comparison_sha256"]
                    and c["profile"] == context["managed_profile"] for c in receipt["comparisons"]),
            "alloydb-accepted-comparison-binding-required")
    if args.action == "verify":
        value = json.loads(args.observation.read_bytes())
        verify_recovery(value, key, context["managed_profile"], context["images"], context["environment"])
        print("ALLOYDB_RECOVERY=VERIFIED")
        return 0
    require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
    require(not command(["git", "status", "--porcelain"]).strip(), "committed-clean-controller-required")
    commit = command(["git", "rev-parse", "HEAD"]).strip()
    require(args.output_root is not None, "fresh-evidence-root-required")
    output = args.output_root.resolve()
    require(not output.exists() and not output.is_relative_to(ROOT), "fresh-private-evidence-outside-checkout-required")
    output.mkdir(parents=True)
    run_id = "alloydb-recovery-" + uuid.uuid4().hex[:24]
    prefix = f'gs://{context["project"]}-ms67-evidence/alloydb-platform/{context["run_id"]}/{run_id}'
    heartbeat = Heartbeat()
    heartbeat.thread.start()
    prior = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        runtime = ManagedGkeRuntime(**{k: context[k] for k in ("project", "region", "cluster", "namespace")},
            images=context["images"], run_id=run_id, output=output, probe_image=context["probe_image"],
            signing_key=key, signer=context["signer"], progress=heartbeat.progress)
        require(runtime.environment() == context["environment"], "alloydb-live-namespace-drift")
        drill = AlloyRecovery(runtime, context["managed_profile"], key, context["signer"], prefix)
        drill.state.update(controller_commit=commit, context_sha256=context["content_sha256"])
        drill.save()
        runtime.recovery_checkpoint()
        print("ALLOYDB_RECOVERY_ROOT=" + str(output), flush=True)
        value = drill.execute()
        value = Journal(output / "alloydb-recovery.observation.json", prefix + "/alloydb-recovery.observation.json",
            context["project"], key, context["signer"]).write(value)
        print(json.dumps({k: value.get(k) for k in ("status", "reason", "pitr", "backup_restore", "recovery")}, indent=2), flush=True)
        verify_recovery(value, key, context["managed_profile"], context["images"], context["environment"])
        print("ALLOYDB_RECOVERY=VERIFIED; URI=" + prefix + "/alloydb-recovery.observation.json")
        return 0
    finally:
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, prior)


if __name__ == "__main__":
    raise SystemExit(main())
