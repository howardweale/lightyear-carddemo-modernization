#!/usr/bin/env python3
"""Run and verify CloudBank's two managed PostgreSQL target comparisons."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import signal
import uuid

from lightyear_data.cloudbank_journeys import ACK, require, JourneyFailure, hashed
from lightyear_data.cloudbank_journeys_gke import command
from lightyear_data.cloudbank_edge_ai import validate_edge_source
from lightyear_data.cloudbank_managed_target import ManagedGkeRuntime, PROVIDERS, observe_target, validate_profile, resolve_database
from lightyear_data.cloudbank_ms66_dual_lane import image_rows, validate_recovery_state
from lightyear_data.cloudbank_ms66_dual_lane_gke import execute_dual_lane
from lightyear_data.cloudbank_ms71 import (
    COMPARISON_FILE, RECEIPT_FILE, admit, verify_receipt, validate_comparison, signed,
)
from lightyear_data.cloudbank_production_readiness import render_deployment_bundle
from lightyear_data.contracts import seal

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    require(path.is_file() and path.stat().st_size <= 4 * 1024 * 1024, "ms71-input-file-invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "ms71-input-object-required")
    return value


def write(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    profile = commands.add_parser("seal-profile", help="Validate and seal an operator-authored target profile")
    profile.add_argument("input", type=Path)
    profile.add_argument("output", type=Path)
    provision = commands.add_parser("provision", help="Create the private nonproduction AlloyDB primary asynchronously")
    provision.add_argument("--profile", type=Path, required=True)
    provision.add_argument("--network", required=True)
    provision.add_argument("--admin-secret", required=True)
    provision.add_argument("--cpu-count", type=int, choices=(2, 4), default=2)
    provision.add_argument("--execute", action="store_true", required=True)
    deploy = commands.add_parser("deploy-target", help="Copy the bound synthetic deployment to a fresh AlloyDB namespace")
    deploy.add_argument("--source-profile", type=Path, required=True)
    deploy.add_argument("--target-profile", type=Path, required=True)
    deploy.add_argument("--target-image-lock", type=Path, required=True)
    deploy.add_argument("--admin-secret", required=True)
    deploy.add_argument("--probe-image", required=True)
    deploy.add_argument("--output-root", type=Path, required=True)
    deploy.add_argument("--execute", action="store_true", required=True)
    deploy.add_argument("--resume", action="store_true")
    render = commands.add_parser("render", help="Render the existing eight-service bundle for a managed target")
    render.add_argument("--profile", type=Path, required=True)
    render.add_argument("--environment", type=Path, required=True)
    render.add_argument("--target-image-lock", type=Path, required=True)
    render.add_argument("--ms64-receipt", type=Path, required=True)
    render.add_argument("--output-root", type=Path, required=True)
    for name in ("preflight", "run"):
        sub = commands.add_parser(name)
        sub.add_argument("--inputs", type=Path, required=True)
        if name == "run":
            sub.add_argument("--campaign-id", required=True)
            sub.add_argument("--output-root", type=Path, required=True)
            sub.add_argument("--evidence-prefix", required=True)
            sub.add_argument("--signer", required=True)
            sub.add_argument("--execute", action="store_true", required=True)
            sub.add_argument("--resume", action="store_true", help="Retain verified comparisons for exactly the same inputs")
    verify = commands.add_parser("verify")
    verify.add_argument("receipt", type=Path)
    return root


def inputs(path: Path):
    config = load(path)
    require(set(config) == {"source_root", "ms61_receipt", "ms64_receipt", "source_image_lock",
        "target_image_lock", "target_profiles", "model_namespace", "model_name", "postgresql_probe_image"},
        "ms71-campaign-inputs-invalid")
    base = path.resolve().parent
    def local(value):
        return (base / value).resolve()
    loaded = {name: load(local(config[name])) for name in (
        "ms61_receipt", "ms64_receipt", "source_image_lock", "target_image_lock")}
    require(isinstance(config["target_profiles"], list) and len(config["target_profiles"]) == 2,
            "ms71-two-target-profiles-required")
    profiles = [load(local(p)) for p in config["target_profiles"]]
    for profile in profiles:
        validate_profile(profile)
    require({p["provider"] for p in profiles} == set(PROVIDERS), "ms71-both-target-providers-required")
    profiles.sort(key=lambda p: PROVIDERS.index(p["provider"]))
    require(profiles[0]["databases"] == profiles[1]["databases"] and
            profiles[0]["database_version"] == profiles[1]["database_version"], "ms71-target-database-contract-drift")
    return config, loaded, profiles, local(config["source_root"])


def preflight(config, loaded, profiles, source):
    require(not validate_edge_source(source), "ms71-pinned-source-bytes-invalid")
    images = image_rows(loaded["target_image_lock"])
    observations = []
    for p in profiles:
        runtime = ManagedGkeRuntime(**{k: p[k] for k in ("project", "region", "cluster", "namespace")},
            images=images, run_id="ms71-preflight", output=Path("."))
        observations.append(observe_target(runtime, p, command))
    require(observations[0]["database"]["address"] != observations[1]["database"]["address"]
            and observations[0]["environment"]["namespace_uid_sha256"] !=
                observations[1]["environment"]["namespace_uid_sha256"], "ms71-target-isolation-invalid")
    return observations


def run_campaign(args, key):
    config, loaded, profiles, source = inputs(args.inputs)
    require(bool(key) and bool(args.signer.strip()), "ms71-signing-identity-required")
    require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
    # A source lock is bound to a committed controller, not an uncommitted work tree.
    state = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True)
    require(not state.stdout.strip(), "ms71-committed-clean-controller-required")
    controller_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True).stdout.strip()
    observations = preflight(config, loaded, profiles, source)
    output = args.output_root.resolve()
    require(not output.is_relative_to(ROOT) and not output.is_relative_to(source), "ms71-evidence-outside-source-required")
    require(args.resume or not output.exists(), "ms71-fresh-output-or-resume-required")
    output.mkdir(parents=True, exist_ok=args.resume)
    require_recovered_attempts(output, key)
    comparisons = []
    for index, profile in enumerate(profiles):
        suffix = "sql" if index == 0 else "alloydb"
        marker = output / (suffix + "-completed.json")
        if args.resume and marker.exists():
            retained = load(marker)
            value = retained["comparison"]
            validate_comparison(value, key, ROOT)
            require(value["campaign_id"] == args.campaign_id
                    and value["profile"] == profile and value["after"] == observations[index]
                    and value["controller_commit"] == controller_commit
                    and value["comparison"]["source_ms61_receipt_sha256"] == loaded["ms61_receipt"]["content_sha256"]
                    and value["comparison"]["source_ms64_receipt_sha256"] == loaded["ms64_receipt"]["content_sha256"]
                    and value["comparison"]["oracle_source_image_lock_sha256"] == loaded["source_image_lock"]["content_sha256"]
                    and value["comparison"]["postgresql_image_lock_sha256"] == loaded["target_image_lock"]["content_sha256"],
                    "ms71-resume-input-drift")
            require(retained["uri"].startswith(args.evidence_prefix.rstrip("/") + "/"), "ms71-resume-prefix-drift")
            remote = json.loads(command(["gcloud", "--quiet", "--project=" + profile["project"],
                "storage", "cat", retained["uri"]], timeout=180))
            require(remote == value, "ms71-resume-readback-mismatch")
            comparisons.append(value)
            print("MS71_RETAINED=" + profile["provider"], flush=True)
            continue
        attempt = suffix + "-" + uuid.uuid4().hex[:8]
        run_id = "ms66-ms71-" + hashed(args.campaign_id + "/" + attempt)[:24]
        lane_output = output / attempt
        prefix = args.evidence_prefix.rstrip("/") + "/" + attempt
        print("MS71_PHASE=" + profile["provider"], flush=True)
        execute_dual_lane(project_root=ROOT, source_root=source,
            ms61=loaded["ms61_receipt"], ms64=loaded["ms64_receipt"],
            source_lock=loaded["source_image_lock"], target_lock=loaded["target_image_lock"],
            project=profile["project"], region=profile["region"], cluster=profile["cluster"],
            target_namespace=profile["namespace"], isolated_namespace=run_id + "-oracle",
            model_namespace=config["model_namespace"], model_name=config["model_name"],
            postgres_probe_image=config["postgresql_probe_image"], output=lane_output,
            evidence_prefix=prefix,
            key=key, signer=args.signer, run_id=run_id, managed_target=profile, campaign_id=args.campaign_id,
            progress=lambda message: print(message, flush=True))
        value = load(lane_output / COMPARISON_FILE)
        validate_comparison(value, key, ROOT)
        remote = json.loads(command(["gcloud", "--quiet", "--project=" + profile["project"], "storage", "cat",
            prefix + "/" + COMPARISON_FILE], timeout=180))
        require(remote == value, "ms71-comparison-readback-mismatch")
        write(marker, {"comparison": value, "uri": prefix + "/" + COMPARISON_FILE})
        comparisons.append(value)
    receipt = admit(comparisons, key, args.signer, ROOT)
    receipt_path = output / RECEIPT_FILE
    if receipt_path.exists():
        require(args.resume and load(receipt_path) == receipt, "ms71-existing-receipt-drift")
    else:
        write(receipt_path, receipt)
    uri = args.evidence_prefix.rstrip("/") + "/" + RECEIPT_FILE
    command(["gcloud", "--quiet", "--project=" + profiles[0]["project"], "storage", "cp",
             str(receipt_path), uri], timeout=180)
    readback = json.loads(command(["gcloud", "--quiet", "--project=" + profiles[0]["project"],
                                  "storage", "cat", uri], timeout=180))
    verify_receipt(readback, key, ROOT)
    require(readback == receipt, "ms71-receipt-readback-mismatch")
    return {"status": "passed", "MS71_COMPLETE": True, "receipt": str(receipt_path), "uri": uri}


def require_recovered_attempts(output: Path, key: str):
    """A new attempt cannot conceal an interrupted Oracle lane or target mutation."""
    for attempt in output.iterdir():
        if not attempt.is_dir() or not attempt.name.startswith(("sql-", "alloydb-")):
            continue
        oracle_path = attempt / "recovery-state.json"
        if oracle_path.exists():
            state = load(oracle_path)
            require(not validate_recovery_state(state, key), "ms71-prior-oracle-recovery-invalid")
            require(state["cleanup_required"] is False, "ms71-prior-oracle-recovery-required")
        for path in (attempt / "postgresql-recovery-state.json", attempt / "postgres-runtime" / "recovery-state.json"):
            if path.exists():
                state = load(path)
                signed(state, key)
                require(state.get("state_type") == "lightyear-cloudbank-journey-recovery"
                        and state.get("stopped_services") == [] and state.get("probe_uid") is None
                        and state.get("checks_delivery") is None, "ms71-prior-target-recovery-required")


def interrupt(signum, frame):
    raise KeyboardInterrupt


def main(argv=None):
    args = parser().parse_args(argv)
    signal.signal(signal.SIGTERM, interrupt)
    key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", "")
    try:
        if args.command == "seal-profile":
            profile = seal(load(args.input))
            validate_profile(profile)
            write(args.output, profile)
            result = {"status": "valid-profile", "MS71_COMPLETE": False}
        elif args.command == "provision":
            from lightyear_data.cloudbank_alloydb_provision import provision
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
            result = provision(load(args.profile), network=args.network, admin_secret=args.admin_secret,
                               cpu_count=args.cpu_count, command=command)
        elif args.command == "deploy-target":
            from lightyear_data.cloudbank_alloydb_deploy import deploy
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
            result = deploy(load(args.source_profile), load(args.target_profile), load(args.target_image_lock),
                admin_secret=args.admin_secret, output=args.output_root, command=command, probe_image=args.probe_image,
                resume=args.resume, progress=lambda message: print(message, flush=True))
        elif args.command == "render":
            profile = load(args.profile)
            database = resolve_database(profile, command)
            env = load(args.environment)
            require(env["namespace"] == profile["namespace"], "ms71-render-namespace-mismatch")
            env = seal({**env, "database_egress_cidr": database["address"] + "/32"})
            manifest, bundle = render_deployment_bundle(load(args.target_image_lock), env,
                                                        load(args.ms64_receipt)["content_sha256"])
            args.output_root.mkdir(parents=True, exist_ok=False)
            (args.output_root / "cloudbank.yaml").write_text(manifest, encoding="utf-8")
            write(args.output_root / "bundle.json", bundle)
            write(args.output_root / "environment.json", env)
            write(args.output_root / "managed-database.json", database)
            result = {"status": "rendered", "MS71_COMPLETE": False}
        elif args.command == "preflight":
            config, loaded, profiles, source = inputs(args.inputs)
            preflight(config, loaded, profiles, source)
            result = {"status": "preflight-passed", "MS71_COMPLETE": False}
        elif args.command == "verify":
            verify_receipt(load(args.receipt), key, ROOT)
            result = {"status": "verified", "MS71_COMPLETE": True}
        else:
            result = run_campaign(args, key)
    except (JourneyFailure, ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        # CLI diagnostics contain bounded codes, never cloud command output or secret values.
        import re
        reason = str(exc)
        result = {"status": "failed", "MS71_COMPLETE": False,
                  "reason": reason if re.fullmatch(r"[a-z0-9-]{1,150}", reason) else "ms71-input-or-execution-failed"}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
