#!/usr/bin/env python3
"""Admit a fully evidenced AlloyDB platform; never infer completion from MS71."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]
import ms67_final_controls
import ms67_final_images
import cloudbank_secret_rotation
from lightyear_data import cloudbank_alert_drill, cloudbank_log_correlation, cloudbank_runtime_identity
from lightyear_data import cloudbank_network_enforcement, cloudbank_sustained_load
from lightyear_data.cloudbank_alloydb_recovery import verify_recovery, APPLICATION_SNAPSHOT_SQL
from lightyear_data.cloudbank_alloydb_ha import verify_ha
from lightyear_data.cloudbank_ms67_drills import verify_observation as verify_drills
from lightyear_data.cloudbank_platform_qualification import SCENARIO_IDS, platform_contract, validate_profile
from lightyear_data.cloudbank_ms71 import verify_receipt as verify_ms71
from lightyear_data.cloudbank_journeys import require, hashed
from lightyear_data.cloudbank_journeys_gke import command
from lightyear_data.cloudbank_managed_target import validate_profile as validate_managed_profile
from lightyear_data.cloudbank_secret_rotation_gke import Journal
from lightyear_data.cloudbank_sql_recovery import verified
from lightyear_data.contracts import sign, content_hash

TYPE = "lightyear-alloydb-nonproduction-platform-qualification"
PHASES = {"current-controls", "runtime-identity", "secret-rotation", "log-correlation", "alert-drill",
          "network-enforcement", "sustained-load", "image-security", "database-recovery", "ha", "drills"}
SCENARIOS = ["signed-alloydb-deployment-contract-admitted", "signed-ms71-alloydb-business-equivalence-admitted",
             *SCENARIO_IDS[2:]]
SCENARIOS[6] = "alloydb-deployment-materialization-observed"
SCENARIOS[22] = "managed-alloydb-backup-created-and-metadata-verified"
SCENARIOS.append("regional-alloydb-primary-failover-with-acknowledged-data")


def assemble(context, ms71, phases, boundaries, key):
    verified(context, key)
    require(context.get("context_type") == "lightyear-alloydb-platform-campaign"
            and context.get("production_environment") is False and not validate_profile(context["profile"], key),
            "alloydb-platform-authorized-context-required")
    validate_managed_profile(context["managed_profile"])
    require(context["managed_profile"]["provider"] == "alloydb-postgresql", "alloydb-platform-provider-required")
    verify_ms71(ms71, key, ROOT)
    require(ms71["content_sha256"] == context["ms71_receipt_sha256"], "alloydb-platform-ms71-binding-invalid")
    comparison = next((c for c in ms71["comparisons"] if c["content_sha256"] == context["alloydb_comparison_sha256"]), None)
    require(comparison is not None and comparison["profile"] == context["managed_profile"]
            and comparison["after"]["database"] == context["managed_target"]["database"],
            "alloydb-platform-business-comparison-invalid")
    require(set(phases) == PHASES, "alloydb-platform-all-operational-phases-required")
    for value in phases.values():
        verified(value, key)
    images, env, profile, bindings = (context[k] for k in ("images", "environment", "profile", "bindings"))
    required_boundaries = {"secret-rotation", "log-correlation", "alert-drill", "network-enforcement", "sustained-load"}
    require(set(boundaries) == required_boundaries, "alloydb-platform-managed-boundaries-required")
    for phase, boundary in boundaries.items():
        verified(boundary, key)
        require(boundary.get("record_type") == "lightyear-alloydb-control-managed-boundary"
                and boundary.get("phase") == phase and boundary.get("context_sha256") == context["content_sha256"]
                and boundary.get("control_observation_sha256") == phases[phase]["content_sha256"],
                "alloydb-platform-control-boundary-invalid")
        for side in ("before", "after"):
            target = boundary[side]
            require(target.get("content_sha256") == content_hash(target)
                    and target.get("database") == context["managed_target"]["database"]
                    and target.get("environment") == env and target.get("images_sha256") == hashed(images)
                    and target.get("profile_sha256") == context["managed_profile"]["content_sha256"],
                    "alloydb-platform-control-target-drift")
    ms67_final_controls.verify_result(phases["current-controls"], context, key)
    cloudbank_runtime_identity.verify_observation(phases["runtime-identity"], key, bindings, images, env)
    cloudbank_secret_rotation.verify_observation(phases["secret-rotation"], key)
    cloudbank_log_correlation.verify_observation(phases["log-correlation"], key)
    cloudbank_alert_drill.verify_observation(phases["alert-drill"], key)
    for phase in ("secret-rotation", "log-correlation", "alert-drill"):
        require(phases[phase].get("bindings") == bindings and phases[phase].get("environment") == env,
                "alloydb-platform-phase-context-mismatch-" + phase)
    network_bindings = {**bindings, "managed_target_profile_sha256": context["managed_profile"]["content_sha256"]}
    cloudbank_network_enforcement.verify_observation(phases["network-enforcement"], key, network_bindings,
        images, env, cloudbank_network_enforcement.compiled_probe(ROOT))
    load_bindings = {**bindings, "ms66_receipt_sha256": comparison["comparison"]["content_sha256"],
                     "journeys_sha256": comparison["target_journey"]["content_sha256"]}
    cloudbank_sustained_load.verify_observation(phases["sustained-load"], key, bindings=load_bindings,
                                               images=images, environment=env, profile=profile, root=ROOT)
    security = phases["image-security"]
    require(security.get("status") == "passed" and security.get("images") == images
            and security.get("context_sha256") == context["content_sha256"], "alloydb-platform-retained-image-context-invalid")
    retained = security["retained_evidence"]
    candidates = ms67_final_images.verify_result(retained, {**{k: retained[k] for k in ("run_id", "controller_commit", "bindings")},
                                                           "images": images}, key)
    verify_recovery(phases["database-recovery"], key, context["managed_profile"], images, env)
    verify_ha(phases["ha"], key, context["managed_profile"], images, env)
    drill_bindings = {**network_bindings, "candidate_image_lock_sha256": retained["candidate_lock"]["content_sha256"],
                      "snapshot_query_sha256": hashed(APPLICATION_SNAPSHOT_SQL)}
    verify_drills(phases["drills"], key, drill_bindings, images, candidates, env)
    current = phases["current-controls"]
    sources = [context, comparison, current, current, current, current, current, current, current,
        current, current, current, current, phases["secret-rotation"], current, phases["log-correlation"],
        phases["alert-drill"], phases["sustained-load"], security, security, current,
        phases["network-enforcement"], phases["database-recovery"], phases["database-recovery"],
        phases["drills"], phases["drills"], phases["drills"], phases["drills"], phases["ha"]]
    return {"schema_version": "1.0", "receipt_type": TYPE, "status": "passed-alloydb-nonproduction-platform-qualification",
        "campaign_id": context["run_id"], "context": context, "ms71_receipt": ms71, "phases": phases,
        "managed_boundaries": boundaries, "platform_contract": platform_contract(),
        "scenarios": [{"id": name, "status": "passed", "evidence_sha256": proof["content_sha256"]}
                      for name, proof in zip(SCENARIOS, sources, strict=True)],
        "scenario_count": len(SCENARIOS), "services": list(images), "environment": env,
        "managed_database": context["managed_target"]["database"], "alloydb_platform_qualified": True,
        "production_ready": False, "production_deployed": False, "customer_certification_complete": False,
        "synthetic_data_only": True, "unplanned_region_failure_qualified": False,
        "image_security_scope": "retained original signed signature/provenance/scan evidence for identical immutable digests",
        "observability_scope": "current-pod GKE CPU metrics and correlated readiness-request logs/traces",
        "availability_scope": "controlled evacuation, paced by service where recorded, and primary failover; sampled availability"}


def verify_receipt(receipt, key):
    verified(receipt, key)
    expected = assemble(receipt["context"], receipt["ms71_receipt"], receipt["phases"], receipt["managed_boundaries"], key)
    require({k: v for k, v in receipt.items() if k not in {"signature", "content_sha256"}} == expected,
            "alloydb-platform-receipt-reconstruction-mismatch")
    return receipt


def export_bundle(inputs_path, receipt_path, output, key):
    """Copy original signed bytes only after complete admission verifies.

    This is a local export. Phase controllers performed the cloud readbacks;
    export does not claim to have repeated those reads or publish a website.
    """
    inputs_path, receipt_path, output = map(Path, (inputs_path, receipt_path, output))
    receipt_raw = receipt_path.read_bytes()
    receipt = verify_receipt(json.loads(receipt_raw), key)
    require(not output.exists(), "alloydb-platform-fresh-export-required")
    inputs = json.loads(inputs_path.read_bytes())
    base = inputs_path.resolve().parent
    require(set(inputs.get("phases", {})) == PHASES
            and set(inputs.get("managed_boundaries", {})) == set(receipt["managed_boundaries"]),
            "alloydb-platform-export-inputs-incomplete")
    sources = {
        "campaign-context.json": (inputs["context"], receipt["context"]),
        "ms71-business-equivalence.receipt.json": (inputs["ms71_receipt"], receipt["ms71_receipt"]),
        **{phase + ".json": (path, receipt["phases"][phase]) for phase, path in inputs["phases"].items()},
        **{phase + ".managed-boundary.json": (path, receipt["managed_boundaries"][phase])
           for phase, path in inputs["managed_boundaries"].items()},
    }
    originals = {"alloydb-platform.receipt.json": receipt_raw}
    for name, (path, expected) in sources.items():
        raw = (base / path).read_bytes()
        require(json.loads(raw) == expected, "alloydb-platform-export-source-drift")
        originals[name] = raw
    # All verification precedes directory creation, avoiding a misleading
    # partial export when a required phase is absent or has changed.
    manifest = sign({"schema_version": "1.0", "record_type": "lightyear-alloydb-platform-publication-export",
        "campaign_id": receipt["campaign_id"], "exported_at": datetime.now(timezone.utc).isoformat(),
        "receipt_file": "alloydb-platform.receipt.json", "receipt_content_sha256": receipt["content_sha256"],
        "operator_signatures_verified": True, "complete_gate_reconstructed": True,
        "cloud_readback_repeated_at_export": False, "original_bytes_preserved": True,
        "files": [{"name": name, "size_bytes": len(raw), "file_sha256": hashlib.sha256(raw).hexdigest(),
                   "content_sha256": json.loads(raw)["content_sha256"]}
                  for name, raw in sorted(originals.items())]}, key, receipt["context"]["signer"])
    output.mkdir(parents=True)
    for name, raw in originals.items():
        (output / name).write_bytes(raw)
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (output / "publication-export.json").write_bytes(raw)
    return {"directory": str(output.resolve()), "file_count": len(originals),
            "export_file_sha256": hashlib.sha256(raw).hexdigest(),
            "receipt_content_sha256": receipt["content_sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("admit", "verify", "export"))
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-uri")
    args = parser.parse_args(argv)
    key = os.environ.get("LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY", "")
    require(bool(key), "alloydb-platform-signing-key-required")
    load = lambda p: json.loads(Path(p).read_bytes())
    if args.action == "verify":
        verify_receipt(load(args.receipt), key)
    elif args.action == "export":
        require(args.inputs and args.receipt and args.output, "alloydb-platform-export-paths-required")
        print(json.dumps(export_bundle(args.inputs, args.receipt, args.output, key), indent=2))
    else:
        inputs = load(args.inputs)
        base = args.inputs.resolve().parent
        local = lambda p: load(base / p)
        context, ms71 = local(inputs["context"]), local(inputs["ms71_receipt"])
        phases = {k: local(v) for k, v in inputs["phases"].items()}
        boundaries = {k: local(v) for k, v in inputs["managed_boundaries"].items()}
        value = assemble(context, ms71, phases, boundaries, key)
        require(args.output and not args.output.exists() and args.evidence_uri.startswith(
            f'gs://{context["project"]}-ms67-evidence/alloydb-platform/{context["run_id"]}/'), "alloydb-platform-fresh-durable-output-required")
        receipt = Journal(args.output, args.evidence_uri, context["project"], key, context["signer"]).write(value)
        verify_receipt(receipt, key)
    print("ALLOYDB_PLATFORM_QUALIFIED=true; PRODUCTION_READY=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
