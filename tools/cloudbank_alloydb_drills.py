#!/usr/bin/env python3
"""Collect bound AlloyDB current controls, image security, failover or GKE drills."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]
from cloudbank_journeys import Heartbeat
from lightyear_data.cloudbank_journeys import ACK, require, hashed
from lightyear_data.cloudbank_journeys_gke import command
from lightyear_data.cloudbank_managed_target import ManagedGkeRuntime, observe_target
from lightyear_data.cloudbank_ms71 import verify_receipt
from lightyear_data.cloudbank_sql_recovery import verified
from lightyear_data.cloudbank_secret_rotation_gke import Journal
from lightyear_data.cloudbank_alloydb_recovery import APPLICATION_SNAPSHOT_SQL
from lightyear_data.cloudbank_alloydb_ha import AlloyHa, AlloyHaRuntime, verify_ha
from lightyear_data.cloudbank_ms67_drills import verify_continuation, verify_observation as verify_drills
from lightyear_data.cloudbank_alloydb_drills import AlloyDrills
from lightyear_data.cloudbank_operator_session import operator_session
import ms67_final_controls
import ms67_final_images


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("current-controls", "image-security", "ha", "drills"))
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--ms71-receipt", type=Path, required=True)
    parser.add_argument("--output-parent", type=Path, required=True)
    parser.add_argument("--resume-state", type=Path)
    parser.add_argument("--original-process-stopped", action="store_true")
    args = parser.parse_args(argv)
    require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
    context = json.loads(args.context.read_bytes())
    project = context["project"]
    key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY") or command([
        "gcloud", "--quiet", "--project=" + project, "secrets", "versions", "access", "latest",
        "--secret=cloudbank-ms67-evidence-key"]).strip()
    verified(context, key)
    require(context.get("context_type") == "lightyear-alloydb-platform-campaign"
            and context.get("production_environment") is False
            and context["managed_profile"]["provider"] == "alloydb-postgresql"
            and context["profile"]["mutating_drills_authorized"] is True, "authorized-alloydb-context-required")
    receipt = json.loads(args.ms71_receipt.read_bytes())
    verify_receipt(receipt, key, ROOT)
    require(receipt["content_sha256"] == context["ms71_receipt_sha256"]
            and any(c["content_sha256"] == context["alloydb_comparison_sha256"]
                    and c["profile"] == context["managed_profile"] for c in receipt["comparisons"]),
            "accepted-alloydb-comparison-required")
    require(not command(["git", "status", "--porcelain"]).strip(), "committed-clean-controller-required")
    commit = command(["git", "rev-parse", "HEAD"]).strip()
    resume = None
    if args.resume_state:
        require(args.phase == "drills" and args.original_process_stopped, "stopped-drill-controller-required")
        resume = verified(json.loads(args.resume_state.read_bytes()), key)
        require(re.fullmatch(r"ms67-final-[0-9a-f]{32}", resume.get("run_id", "")), "original-drill-run-required")
    run_id = resume["run_id"] if resume else (
        "ms67-final-" + uuid.uuid4().hex if args.phase == "drills" else "alloydb-" + args.phase + "-" + uuid.uuid4().hex[:16])
    directory_id = "alloydb-drill-continuation-" + uuid.uuid4().hex[:16] if resume else run_id
    output = args.output_parent.resolve() / directory_id
    require(not output.is_relative_to(ROOT), "private-evidence-outside-checkout-required")
    output.mkdir(parents=True)
    prefix = f'gs://{project}-ms67-evidence/alloydb-platform/{context["run_id"]}/{directory_id}'
    signer = context["signer"]
    heartbeat = Heartbeat()
    heartbeat.thread.start()
    prior = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    runtime = (AlloyHaRuntime if args.phase == "ha" else ManagedGkeRuntime)(
        **{k: context[k] for k in ("project", "region", "cluster", "namespace")}, images=context["images"],
        run_id=run_id, output=output, probe_image=context["probe_image"], signing_key=key, signer=signer, progress=heartbeat.progress)
    try:
        managed = observe_target(runtime, context["managed_profile"], command)
        require(managed["database"] == context["managed_target"]["database"]
                and runtime.environment() == context["environment"], "managed-platform-identity-drift")
        Journal(output / "intent.json", prefix + "/intent.json", project, key, signer).write({
            "phase": args.phase, "run_id": run_id, "controller_commit": commit, "context_sha256": context["content_sha256"],
            "resumed_from_state_sha256": resume["content_sha256"] if resume else None,
            "managed_target": managed, "alloydb_platform_qualified": False})
        print("ALLOYDB_EXTENDED=" + args.phase + "; OUTPUT=" + str(output), flush=True)
        if args.phase in {"drills", "image-security"}:
            retained = json.loads((ROOT / "docs/receipts/ms67-final-635689566db6425aadf6fb1fc6cf3de7/receipts/phase-candidates.json").read_bytes())
            candidates = ms67_final_images.verify_result(retained,
                {**{k: retained[k] for k in ("run_id", "controller_commit", "bindings")}, "images": context["images"]}, key)
        if args.phase == "image-security":
            value = {"record_type": "lightyear-alloydb-retained-immutable-image-security", "status": "passed",
                "images": context["images"], "context_sha256": context["content_sha256"], "retained_evidence": retained,
                "scope": "original verified signature, provenance and scan for exactly identical immutable images; scan not repeated",
                "alloydb_platform_qualified": False}
        elif args.phase == "current-controls":
            value = ms67_final_controls.observe(runtime, context, key, signer)
            ms67_final_controls.verify_result(value, context, key)
        elif args.phase == "ha":
            drill = AlloyHa(runtime, context["managed_profile"], key, signer, prefix)
            drill.state.update(bindings=context["bindings"], controller_commit=commit, context_sha256=context["content_sha256"])
            value = drill.execute()
        else:
            bindings = {**context["bindings"], "candidate_image_lock_sha256": retained["candidate_lock"]["content_sha256"],
                "managed_target_profile_sha256": context["managed_profile"]["content_sha256"],
                "snapshot_query_sha256": hashed(APPLICATION_SNAPSHOT_SQL)}
            if resume:
                verify_continuation(resume, key, bindings, context["images"], candidates, context["environment"],
                                    readiness_timeout=True)
                Journal(output / "prior-state.json", prefix + "/prior-state.json", project, key, signer).write(resume)
            drill = AlloyDrills(runtime, candidates, bindings, key, signer,
                               f"gs://{project}-ms67-evidence/final-drills/{run_id}", state=resume)
            if resume:
                drill.s.setdefault("controller_provenance", []).append({"controller_commit": commit,
                    "previous_state_sha256": resume["content_sha256"], "original_process_stopped": True})
            value = drill.run()
        value = Journal(output / (args.phase + ".json"), prefix + "/" + args.phase + ".json", project, key, signer).write(value)
        if args.phase == "ha":
            verify_ha(value, key, context["managed_profile"], context["images"], context["environment"])
        if args.phase == "drills":
            verify_drills(value, key, bindings, context["images"], candidates, context["environment"])
        print(json.dumps({"phase": args.phase, "status": value["status"], "uri": prefix + "/" + args.phase + ".json",
                          "content_sha256": value["content_sha256"]}), flush=True)
        return 0
    finally:
        for service in list(runtime.forwards):
            runtime.close_forward(service)
        heartbeat.done.set()
        heartbeat.thread.join(timeout=1)
        signal.signal(signal.SIGTERM, prior)


if __name__ == "__main__":
    with operator_session():
        raise SystemExit(main())
