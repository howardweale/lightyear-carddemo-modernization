#!/usr/bin/env python3
"""Run existing operational collectors against a signed AlloyDB campaign context."""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]
from lightyear_data.cloudbank_journeys import ACK, require
from lightyear_data.cloudbank_journeys_gke import command
from lightyear_data.cloudbank_managed_target import ManagedGkeRuntime, observe_target, validate_profile
from lightyear_data.cloudbank_ms71 import verify_receipt
from lightyear_data.cloudbank_secret_rotation_gke import Journal
from lightyear_data.cloudbank_sql_recovery import verified
from lightyear_data.cloudbank_operator_session import operator_session

MODULES = {p: "cloudbank_" + p.replace("-", "_") for p in (
    "secret-rotation", "log-correlation", "alert-drill", "network-enforcement", "runtime-identity", "sustained-load")}
RETAINED = ROOT / "docs/receipts/ms67-final-635689566db6425aadf6fb1fc6cf3de7/receipts"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=MODULES)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--ms71-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--recovery-state", type=Path)
    parser.add_argument("--original-process-stopped", action="store_true")
    args = parser.parse_args(argv)
    require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
    context = json.loads(args.context.read_bytes())
    project = context["project"]
    key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY") or command([
        "gcloud", "--quiet", "--project=" + project, "secrets", "versions", "access", "latest",
        "--secret=cloudbank-ms67-evidence-key"]).strip()
    verified(context, key)
    validate_profile(context["managed_profile"])
    require(context.get("context_type") == "lightyear-alloydb-platform-campaign"
            and context.get("production_environment") is False
            and context["managed_profile"]["provider"] == "alloydb-postgresql"
            and context["profile"]["mutating_drills_authorized"] is True, "authorized-alloydb-context-required")
    ms71 = json.loads(args.ms71_receipt.read_bytes())
    verify_receipt(ms71, key, ROOT)
    require(ms71["content_sha256"] == context["ms71_receipt_sha256"]
            and any(c["content_sha256"] == context["alloydb_comparison_sha256"]
                    and c["profile"] == context["managed_profile"] for c in ms71["comparisons"]),
            "accepted-alloydb-comparison-required")
    profile_root = args.context.resolve().parent
    require(verified(json.loads((profile_root / "platform-profile.json").read_bytes()), key) == context["profile"]
            and json.loads((profile_root / "alloydb-profile.json").read_bytes()) == context["managed_profile"],
            "alloydb-control-profile-files-differ-from-context")
    action = "recover" if args.recovery_state else "run"
    require(not command(["git", "status", "--porcelain"]).strip(), "committed-clean-controller-required")
    if action == "recover":
        require(args.original_process_stopped, "original-executor-must-be-stopped-before-recovery")
    output = args.output_root.resolve()
    require(not output.exists() and not output.is_relative_to(ROOT), "fresh-private-evidence-root-required")
    commit = command(["git", "rev-parse", "HEAD"]).strip()
    run_id = args.phase + "-" + uuid.uuid4().hex[:16]
    runtime = ManagedGkeRuntime(**{k: context[k] for k in ("project", "region", "cluster", "namespace")},
        images=context["images"], run_id=run_id, output=output, probe_image=context["probe_image"])
    before = observe_target(runtime, context["managed_profile"], command)
    require(before["database"] == context["managed_target"]["database"]
            and before["environment"] == context["environment"], "alloydb-control-target-drift")
    prefix = f'gs://{project}-ms67-evidence/alloydb-platform/{context["run_id"]}/{run_id}'
    # The underlying collector requires the directory to be absent on admission.
    output.parent.mkdir(parents=True, exist_ok=True)
    Journal(output.with_name(output.name + "-intent.json"), prefix + "/intent.json", project, key,
            context["signer"]).write({"record_type": "lightyear-alloydb-platform-control-intent",
        "phase": args.phase, "action": action, "controller_commit": commit,
        "context_sha256": context["content_sha256"], "managed_before": before,
        "output_root": str(output), "alloydb_platform_qualified": False})
    cli = [action]
    for field in ("project", "region", "cluster", "namespace", "signer"):
        cli += ["--" + field, context[field]]
    cli += ["--evidence-bucket", f"gs://{project}-ms67-evidence/" + args.phase,
        "--image-lock", str(RETAINED / "retained-image-lock.json"),
        "--ms64-receipt", str(RETAINED / "retained-ms64-receipt.json"),
        "--platform-profile", str(profile_root / "platform-profile.json"), "--output-root", str(output)]
    if args.phase == "secret-rotation":
        cli += ["--provider-secret", "cloudbank-ms71-alloydb-creditscore"]
    if args.phase == "network-enforcement":
        cli += ["--managed-target-profile", str(profile_root / "alloydb-profile.json")]
    if args.phase == "sustained-load":
        cli += ["--ms66-receipt", str(profile_root / "alloydb-ms66.receipt.json"),
                "--journeys", str(profile_root / "alloydb-journeys.json")]
    if action == "recover":
        cli += ["--recovery-state", str(args.recovery_state)]
        if args.phase in {"alert-drill", "network-enforcement"}:
            cli += ["--original-process-stopped"]
    prior_key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY")
    os.environ["LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"] = key
    try:
        code = importlib.import_module(MODULES[args.phase]).main(cli)
        if code == 0 and action == "run":
            after = observe_target(runtime, context["managed_profile"], command)
            require(after["database"] == before["database"] and after["environment"] == before["environment"],
                    "alloydb-control-final-target-drift")
            proofs = set()
            for path in output.glob("*.json"):
                proof = json.loads(path.read_bytes())
                if proof.get("observation_type") and proof.get("status", "").startswith("passed"):
                    proofs.add(verified(proof, key)["content_sha256"])
            require(len(proofs) == 1, "unique-passing-control-observation-required")
            Journal(output / "managed-boundary.json", prefix + "/managed-boundary.json", project, key,
                    context["signer"]).write({"record_type": "lightyear-alloydb-control-managed-boundary",
                "phase": args.phase, "controller_commit": commit, "control_observation_sha256": proofs.pop(),
                "context_sha256": context["content_sha256"], "before": before, "after": after,
                "alloydb_platform_qualified": False})
        return code
    finally:
        if prior_key is None:
            os.environ.pop("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", None)
        else:
            os.environ["LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"] = prior_key


if __name__ == "__main__":
    with operator_session():
        raise SystemExit(main())
