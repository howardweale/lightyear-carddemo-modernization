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


def signed_observation(output, phase, key):
    # Collectors also write unsigned display summaries. Only their canonical
    # observation file is an admission input; never infer one from its status.
    proof = verified(json.loads((output / (phase + ".observation.json")).read_bytes()), key)
    require(proof.get("observation_type") and proof.get("status", "").startswith("passed"),
            "passing-control-observation-required")
    return proof


def completed_log_inputs(output, context, key):
    from lightyear_data.cloudbank_log_correlation import verify_observation, STATE_FILE, STATE_TYPE
    intent = verified(json.loads(output.with_name(output.name + "-intent.json").read_bytes()), key)
    proof = signed_observation(output, "log-correlation", key)
    verify_observation(proof, key)
    state = verified(json.loads((output / STATE_FILE).read_bytes()), key)
    require(intent.get("record_type") == "lightyear-alloydb-platform-control-intent"
            and intent.get("phase") == "log-correlation" and intent.get("action") == "run"
            and intent.get("context_sha256") == context["content_sha256"]
            and intent.get("output_root") == str(output), "logging-completion-intent-invalid")
    require(state.get("state_type") == STATE_TYPE and state.get("cleanup_complete") is True
            and state.get("phase") == "installed-and-verified" and state.get("run_id") == proof["run_id"],
            "logging-completion-verified-released-state-required")
    require(all(state.get(k) == proof[k] == context[k] for k in ("environment", "images", "bindings")),
            "logging-completion-context-drift")
    return intent, proof, state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=MODULES)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--ms71-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--recovery-state", type=Path)
    parser.add_argument("--original-process-stopped", action="store_true")
    parser.add_argument("--complete-log-boundary", action="store_true",
                        help="Bind an already signed, released logging run after wrapper assembly failure")
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
    if args.complete_log_boundary:
        require(args.phase == "log-correlation" and not args.recovery_state and args.original_process_stopped
                and output.is_dir() and not output.is_relative_to(ROOT)
                and not (output / "managed-boundary.json").exists(), "logging-completion-fresh-boundary-required")
        intent, proof, state = completed_log_inputs(output, context, key)
        uri = f'gs://{project}-ms67-evidence/log-correlation/observations/{proof["run_id"]}/log-correlation.observation.json'
        require(verified(json.loads(command(["gcloud", "storage", "cat", uri, "--project", project])), key) == proof,
                "logging-completion-original-observation-readback-mismatch")
        require(verified(json.loads(command(["gcloud", "storage", "cat", state["recovery_uri"], "--project", project])), key) == state,
                "logging-completion-released-state-readback-mismatch")
        runtime = ManagedGkeRuntime(**{k: context[k] for k in ("project", "region", "cluster", "namespace")},
            images=context["images"], run_id=proof["run_id"], output=output, probe_image=context["probe_image"])
        after = observe_target(runtime, context["managed_profile"], command)
        before = intent["managed_before"]
        require(all(target["database"] == context["managed_target"]["database"]
                    and target["environment"] == context["environment"] for target in (before, after)),
                "logging-completion-target-drift")
        Journal(output / "managed-boundary.json",
            f'gs://{project}-ms67-evidence/alloydb-platform/{context["run_id"]}/log-boundary-completion-{proof["run_id"]}/managed-boundary.json',
            project, key, context["signer"]).write({"record_type": "lightyear-alloydb-control-managed-boundary",
                "phase": "log-correlation", "controller_commit": command(["git", "rev-parse", "HEAD"]).strip(),
                "collection_controller_commit": intent["controller_commit"], "collection_intent_sha256": intent["content_sha256"],
                "completion_scope": "original signed observation and released state read back; fresh target observation; no collector rerun",
                "control_observation_sha256": proof["content_sha256"], "context_sha256": context["content_sha256"],
                "before": before, "after": after, "alloydb_platform_qualified": False})
        print("ALLOYDB_LOG_BOUNDARY_COMPLETED; ORIGINAL_OBSERVATION_UNCHANGED")
        return 0
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
            proof = signed_observation(output, args.phase, key)
            Journal(output / "managed-boundary.json", prefix + "/managed-boundary.json", project, key,
                    context["signer"]).write({"record_type": "lightyear-alloydb-control-managed-boundary",
                "phase": args.phase, "controller_commit": commit, "control_observation_sha256": proof["content_sha256"],
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
