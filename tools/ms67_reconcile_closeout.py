#!/usr/bin/env python3
"""Reconcile existing MS67 evidence; optionally resume only a missing MS65 receipt.

The default mode reads local evidence and the existing evidence bucket. It never
starts a load, SQL recovery, deployment, or drill. --resume-ms65 can invoke the
already reviewed MS65 continuation after the inventory is saved.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cloudbank_sql_recovery import load_bound_inputs
from ms67_accept_sql_recovery import ACCOUNT, BUCKET, IMAGE_BUILD, LOAD_RUN, PROJECT
from lightyear_data import cloudbank_platform_qualification as platform
from lightyear_data import cloudbank_production_readiness as ms65
from lightyear_data import cloudbank_whole_application_equivalence as ms66
from lightyear_data import cloudbank_sustained_load as sustained
from lightyear_data.cloudbank_ms65_rehearsal_gke import validate_database_recovery
from lightyear_data.cloudbank_journeys import JourneyFailure, require, hashed
from lightyear_data.cloudbank_sql_recovery import invoke, verified
from lightyear_data.contracts import content_hash, seal

LOAD_SHA = "f23c637611400f8ec9acebc49c3de6ddbcd1ec6d03c9ac3637ce8f837aa34fbf"
SQL_SOURCE = "96e8efcffb192bcad2c6d53c9d54b475908d10c67cb4c3a192c2ca12ccf1161d"
MAX_BYTES = 8 * 1024 * 1024
MAX_LOCAL = 5000
PREFIX = "lightyear-cloudbank-ms67-"
GROUPS = {
    "ms65": ("MS65 receipt and deployment", [0, 6]),
    "operations": ("Rotation, metrics, logs/traces and alert recovery", [13, 14, 15, 16]),
    "security": ("Image, manifest, runtime and network security", [18, 19, 20, 21]),
    "resilience": ("Node and failure-domain recovery", [24]),
    "rolling": ("Eight-service rolling deployment", [25]),
    "cutover": ("Canary, 18 journeys, rollback and recovery", [26, 27]),
}
TYPES = {
    ms65.RECEIPT_TYPE: "ms65",
    ms66.RECEIPT_TYPE: "ms66",
    sustained.OBSERVATION_TYPE: "load",
    "lightyear-cloudbank-isolated-sql-recovery": "sql",
    PREFIX + "secret-rotation-observation": "operations",
    PREFIX + "alert-drill-observation": "operations",
    PREFIX + "log-correlation-observation": "operations",
    PREFIX + "image-security-observation": "security",
    PREFIX + "runtime-identity-observation": "security",
    PREFIX + "network-enforcement-observation": "security",
}
SAFE_TEXT = re.compile(r"^[a-zA-Z0-9_.:/-]{1,180}$")


def safe_text(value):
    return value if isinstance(value, str) and SAFE_TEXT.fullmatch(value) else None


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def cloud(*args):
    # Keep all cloud writes, IAM changes and arbitrary CLI actions out of the reader.
    allowed = (args == ("storage", "ls", "--recursive", BUCKET)
               or (len(args) == 3 and args[:2] == ("storage", "cat") and valid_uri(args[2]))
               or args == ("secrets", "versions", "list", "cloudbank-ms67-evidence-key", "--format=json")
               or args == ("secrets", "versions", "access", "1", "--secret=cloudbank-ms67-evidence-key"))
    require(allowed, "closeout-read-only-cloud-command-required")
    return invoke(["gcloud", "--project=" + PROJECT, "--account=" + ACCOUNT, *args],
                  sensitive=args[:3] == ("secrets", "versions", "access"))


def valid_uri(uri):
    return (isinstance(uri, str) and uri.startswith(BUCKET + "/") and uri.endswith(".json")
            and not any(c in uri for c in "\r\n*?[]") and "/../" not in uri)


def candidate_name(name):
    base = name.rsplit("/", 1)[-1].lower()
    return (base.endswith(".json")
            and not any(part in base for part in ("raw", "credential", "payload", "diagnostic", "recovery-state"))
            and any(part in base for part in (
                "observation", "receipt", "recovery", "resilien", "disruption", "rolling", "rollout",
                "cutover", "rollback", "rotation", "alert", "correlation", "identity", "enforcement",
                "security", "image-build", "operations", "metrics", "profile", "journeys", "ms65", "ms66")))


def decode(raw):
    require(len(raw) <= MAX_BYTES, "closeout-json-size-limit")
    value = json.loads(raw)
    return value if isinstance(value, dict) else None


def read_local(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_BYTES,
            "closeout-bounded-regular-file-required")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    return decode(raw), digest(raw)


def local_paths(root):
    paths, gaps = [], []
    def failed(_error):
        gaps.append("local-directory-unreadable")
    for directory, names, files in os.walk(root, followlinks=False, onerror=failed):
        here = Path(directory)
        names[:] = sorted(n for n in names if not n.startswith(".")
                          and n not in {"controller", "node_modules", "target", "upstream", "source", "ms67-closeout"}
                          and not (here / n).is_symlink() and not (here / n / ".git").exists())
        for name in sorted(files):
            if candidate_name(name):
                path = here / name
                if path.is_symlink():
                    gaps.append("local-symlink-skipped")
                    continue
                paths.append(path)
                if len(paths) >= MAX_LOCAL:
                    gaps.append("local-candidate-limit-reached")
                    return paths, gaps
    return paths, gaps


def family(value):
    kind = value.get("receipt_type") or value.get("observation_type")
    if not isinstance(kind, str):
        return []
    if kind in TYPES:
        return [TYPES[kind]]
    if isinstance(kind, str) and "closeout" not in kind:
        found = [g for field, g in (("resilience", "resilience"), ("rolling_deployments", "rolling"),
                                   ("cutover_rollback", "cutover")) if field in value]
        # These are candidates for review, not inferred platform passes.
        if kind == "lightyear-cloudbank-ms67-platform-observation":
            found += ["ms65", "operations", "security"]
        if kind == platform.RECEIPT_TYPE:
            found += list(GROUPS)
        if not found:
            found = [group for words, group in ((("resilien", "node-disruption", "failure-domain"), "resilience"),
                                               (("rolling", "rollout"), "rolling"),
                                               (("cutover", "rollback"), "cutover"))
                     if any(word in kind for word in words)]
        if not found and any(w in kind for w in ("rotation", "metrics", "telemetry", "operations")):
            found = ["operations"]
        if not found and any(w in kind for w in ("image-build", "image-security", "runtime-policy", "manifest-scan")):
            found = ["security"]
        return sorted(set(found))
    return []


def context_match(value, context):
    kind = value.get("receipt_type") or value.get("observation_type")
    bindings = value.get("bindings") or {}
    if kind == ms65.RECEIPT_TYPE:
        return (value.get("source_ms64_receipt_sha256") == context["bindings"]["ms64_receipt_sha256"]
                and value.get("image_lock_sha256") == context["bindings"]["image_lock_sha256"]
                and value.get("cluster_identity_sha256") == context["profile"]["cluster_uid_sha256"]
                and value.get("environment_sha256") == context["ms65_environment_sha256"]
                and {r["service"]: r["image"] for r in value.get("rehearsal", {}).get("service_rollouts", [])}
                    == context["images"])
    if kind == ms66.RECEIPT_TYPE:
        return (value.get("source_ms64_receipt_sha256") == context["bindings"]["ms64_receipt_sha256"]
                and value.get("postgresql_image_lock_sha256") == context["bindings"]["image_lock_sha256"]
                and value.get("postgresql_journey_sha256") == context["journeys_sha256"])
    if kind == "lightyear-cloudbank-isolated-sql-recovery":
        return (bindings.get("images_sha256") == hashed(context["images"])
                and bindings.get("environment") == context["environment"]
                and bindings.get("journeys_content_sha256") == context["journeys_sha256"])
    return (bindings == context["bindings"] and value.get("environment") == context["environment"]
            and ("images" not in value or value["images"] == context["images"]))


def verify_contract(value, key, context):
    kind = value.get("receipt_type") or value.get("observation_type")
    if kind == ms65.RECEIPT_TYPE:
        require(not ms65.validate_execution_receipt(value, key, ROOT), "ms65-contract-rejected")
    elif kind == ms66.RECEIPT_TYPE:
        require(not ms66.validate_execution_receipt(value, key, ROOT), "ms66-contract-rejected")
    elif kind == sustained.OBSERVATION_TYPE:
        sustained.verify_observation(value, key, bindings=context["bindings"], images=context["images"],
                                     environment=context["environment"], profile=context["profile"], root=ROOT)
    elif kind == "lightyear-cloudbank-isolated-sql-recovery":
        validate_database_recovery(value, key, images=context["images"],
                                   environment=context["environment"], journeys_sha256=context["journeys_sha256"])
    elif kind == PREFIX + "alert-drill-observation":
        from lightyear_data.cloudbank_alert_drill import verify_observation
        verify_observation(value, key)
    elif kind == PREFIX + "log-correlation-observation":
        from lightyear_data.cloudbank_log_correlation import verify_observation
        verify_observation(value, key)
    elif kind == PREFIX + "runtime-identity-observation":
        from lightyear_data.cloudbank_runtime_identity import verify_observation
        verify_observation(value, key, context["bindings"], context["images"], context["environment"])
    elif kind == PREFIX + "network-enforcement-observation":
        from lightyear_data.cloudbank_network_enforcement import verify_observation
        artifact, _ = read_local(ROOT / "factory/cloudbank/platform-qualification/gke/network-probe/compiled.json")
        verify_observation(value, key, context["bindings"], context["images"], context["environment"], artifact)
    else:
        # In particular, unsigned Cloud Build image results need their separate
        # provenance/checksum chain. A self-reported status or HMAC alone is not it.
        return False
    return True


def inspect(value, key, context, locator, file_sha):
    groups = family(value)
    if not groups:
        return None
    result = {"groups": groups, "locator": locator, "file_sha256": file_sha,
              "evidence_type": safe_text(value.get("receipt_type") or value.get("observation_type")),
              "reported_status": safe_text(value.get("status")), "run_id": safe_text(value.get("run_id")),
              "verification": "unsigned-or-invalid", "matching_context": False}
    try:
        verified(value, key)
    except Exception:
        return result
    result["content_sha256"] = value["content_sha256"]
    result["verification"] = "signature-only"
    try:
        result["matching_context"] = context_match(value, context)
        if result["matching_context"]:
            if verify_contract(value, key, context):
                result["verification"] = "contract-verified-current-context"
            else:
                result["verification"] = "matching-context-needs-contract-review"
        elif value.get("receipt_type") in (ms65.RECEIPT_TYPE, ms66.RECEIPT_TYPE):
            if verify_contract(value, key, context):
                result["verification"] = "historical-milestone-pass"
    except Exception:
        result["verification"] = "contract-review-required"
    return result


def anchors(root, documents, key):
    execution = root / ("load-fix-run-" + IMAGE_BUILD)
    refresh = execution / "qualification-refresh" / ("from-" + LOAD_RUN)
    state = verified(read_local(refresh / "refresh-state.json")[0], key)
    require(state.get("state_type") == "lightyear-ms67-recovery-ms65-refresh"
            and state.get("passing_load_sha256") == LOAD_SHA, "closeout-refresh-identity-mismatch")
    bundle = execution / "regional-load/retry-4f7ccc6c-347d-4d78-a1dc-aede161165eb/bundle"
    args = argparse.Namespace(image_lock=bundle / "image-lock.json", ms64_receipt=bundle / "ms64-receipt.json",
                              journeys=bundle / "journeys.json", probe_image=state["inputs"]["probe_image"])
    receipt, lock, journeys, images, binding = load_bound_inputs(args, key)
    loads = [v for v, _locator, _sha in documents if v.get("observation_type") == sustained.OBSERVATION_TYPE
             and v.get("run_id") == LOAD_RUN and v.get("content_sha256") == LOAD_SHA]
    require(bool(loads), "closeout-recorded-passing-load-not-located")
    load = verified(loads[0], key)
    profiles = [v for v, _locator, _sha in documents
                if v.get("profile_type") == "lightyear-cloudbank-ms67-platform-profile"
                and v.get("content_sha256") == load.get("bindings", {}).get("platform_profile_sha256")]
    require(bool(profiles) and not platform.validate_profile(profiles[0], key),
            "closeout-matching-profile-not-located")
    context = {"images": images, "environment": binding["environment"], "profile": profiles[0],
               "journeys_sha256": journeys["content_sha256"],
               "ms65_environment_sha256": state["inputs"]["ms65_environment_sha256"],
               "bindings": {"image_lock_sha256": lock["content_sha256"],
                            "ms64_receipt_sha256": receipt["content_sha256"],
                            "platform_profile_sha256": profiles[0]["content_sha256"]}}
    require(all(context["environment"].get(k) == v for k, v in
                {"project": PROJECT, "region": "us-west1", "cluster": "cloudbank-ms67", "namespace": "cloudbank-ms67"}.items()),
            "closeout-nonproduction-scope-mismatch")
    verify_contract(load, key, context)
    sql_path = refresh / ("sql-reassessment-630-" + SQL_SOURCE) / "database-recovery.json"
    sql = verified(read_local(sql_path)[0], key)
    require(sql.get("reassessment", {}).get("source_observation", {}).get("content_sha256") == SQL_SOURCE,
            "closeout-accepted-sql-source-mismatch")
    verify_contract(sql, key, context)
    retained = {"load": {"run_id": LOAD_RUN, "content_sha256": LOAD_SHA, "status": "verified"},
                "sql": {"content_sha256": sql["content_sha256"], "status": "verified-under-approved-630-policy"}}
    return context, retained


def read_remote(uri):
    try:
        raw = cloud("storage", "cat", uri).encode()
        return decode(raw), uri, digest(raw), None
    except JourneyFailure as error:
        return None, uri, None, safe_text(str(error)) or "cloud-candidate-read-rejected"
    except Exception:
        return None, uri, None, "cloud-candidate-unreadable-or-invalid"


def build_report(records, retained, gaps, local_count, remote_count):
    rows = []
    for group, (title, indexes) in GROUPS.items():
        selected = list({(r.get("content_sha256", r["file_sha256"]), r["verification"]): r
                         for r in records if group in r["groups"]}.values())
        rows.append({"group": group, "title": title,
                     "scenario_ids": [platform.SCENARIO_IDS[i] for i in indexes],
                     "candidates": len(selected),
                     "contract_verified_current_context": sum(r["verification"] == "contract-verified-current-context" for r in selected),
                     "historical_milestone_passes": sum(r["verification"] == "historical-milestone-pass" for r in selected),
                     "status": "evidence-review-required" if selected else "not-located-in-completed-reads"})
    return seal({"schema_version": "1.0", "observation_type": "lightyear-ms67-closeout-reconciliation",
                 "collected_at": datetime.now(timezone.utc).isoformat(),
                 "scope": "read-only-reconciliation-before-any-optional-ms65-execution",
                 "status": "inventory-collected" if not gaps else "inventory-incomplete",
                 "retained": retained, "groups": rows, "records": records, "gaps": sorted(set(gaps)),
                 "coverage": {"local_candidates": local_count, "cloud_candidates": remote_count},
                 "qualification_evidence": False, "ms67_complete": False, "cloud_mutations": 0,
                 "load_attempts_started": 0, "sql_recovery_runs_started": 0, "credentials_persisted": False,
                 "limitations": ["Candidate counts do not establish complete scenario coverage.",
                                "Current-context means the recorded release, not a fresh live-cluster check.",
                                "Cloud Build image evidence needs its own verified provenance/checksum chain.",
                                "Missing files or unsupported contracts require review, not automatic reruns."]})


def should_resume(report):
    require(report["status"] == "inventory-collected", "complete-inventory-required-before-ms65-resume")
    require(not any(r["evidence_type"] == ms65.RECEIPT_TYPE
                    and r["verification"] not in {"contract-verified-current-context", "historical-milestone-pass"}
                    for r in report["records"]), "existing-ms65-evidence-needs-review-before-resume")
    return not any(r["evidence_type"] == ms65.RECEIPT_TYPE
                   and r["verification"] == "contract-verified-current-context" for r in report["records"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=Path.home() / "ms67-evidence")
    parser.add_argument("--max-cloud-candidates", type=int, default=300)
    parser.add_argument("--resume-ms65", action="store_true",
                        help="After reconciliation, resume the reviewed MS65 helper only if its matching receipt is absent.")
    args = parser.parse_args(argv)
    require(1 <= args.max_cloud_candidates <= 2000, "closeout-cloud-limit-out-of-range")
    root = args.evidence_root.resolve()
    require(root.is_dir(), "closeout-existing-evidence-root-required")
    os.umask(0o077)
    print("MS67_CLOSEOUT_RECONCILIATION=READ_ONLY", flush=True)
    versions = json.loads(cloud("secrets", "versions", "list", "cloudbank-ms67-evidence-key", "--format=json"))
    require([r["name"] for r in versions if r.get("state") == "ENABLED"] ==
            ["projects/233419964177/secrets/cloudbank-ms67-evidence-key/versions/1"],
            "evidence-version-1-must-be-sole-enabled-version")
    key = cloud("secrets", "versions", "access", "1", "--secret=cloudbank-ms67-evidence-key").strip()
    require(bool(key), "evidence-key-required")
    paths, gaps = local_paths(root)
    documents, failed_reads = [], []
    for path in paths:
        try:
            value, sha = read_local(path)
            if value is not None:
                documents.append((value, str(path), sha))
        except Exception:
            gaps.append("local-candidate-unreadable-or-invalid")
            failed_reads.append({"locator": str(path), "reason": "local-candidate-unreadable-or-invalid"})
    print("MS67_CLOSEOUT_PHASE=verify retained load and accepted SQL", flush=True)
    context, retained = anchors(root, documents, key)
    print("MS67_CLOSEOUT_RETAINED=LOAD_AND_SQL_VERIFIED", flush=True)
    records = []
    for value, locator, sha in documents:
        row = inspect(value, key, context, locator, sha)
        if row:
            records.append(row)
    print("MS67_CLOSEOUT_PHASE=locate existing cloud evidence", flush=True)
    uris = []
    try:
        listing = cloud("storage", "ls", "--recursive", BUCKET)
        uris = sorted({line.strip() for line in listing.splitlines()
                       if valid_uri(line.strip()) and candidate_name(line.strip())})
        if len(uris) > args.max_cloud_candidates:
            gaps.append("cloud-candidate-limit-reached")
        with ThreadPoolExecutor(max_workers=4) as pool:
            for index, (value, uri, sha, error) in enumerate(pool.map(read_remote, uris[:args.max_cloud_candidates]), 1):
                if error:
                    gaps.append("cloud-candidate-unreadable-or-invalid")
                    failed_reads.append({"locator": uri, "reason": error})
                elif value is not None:
                    row = inspect(value, key, context, uri, sha)
                    if row:
                        records.append(row)
                if index % 20 == 0:
                    print("MS67_CLOSEOUT_CLOUD_READ=" + str(index) + "/" + str(min(len(uris), args.max_cloud_candidates)), flush=True)
    except Exception:
        gaps.append("cloud-listing-or-read-incomplete")
    # Keep every locator, but count each identical signed payload only once per
    # group in the compact summary. Full records preserve readback provenance.
    report = build_report(records, retained, gaps, len(paths), len(uris))
    report = seal({**report, "failed_reads": failed_reads})
    output = root / "ms67-closeout" / ("reconcile-" + uuid.uuid4().hex)
    output.mkdir(parents=True, mode=0o700)
    destination = output / "closeout-reconciliation.json"
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("MS67_CLOSEOUT_REPORT=" + str(destination), flush=True)
    print(json.dumps({k: report[k] for k in ("status", "retained", "groups", "gaps", "failed_reads", "ms67_complete")}, indent=2), flush=True)
    if args.resume_ms65:
        if should_resume(report):
            print("MS67_CLOSEOUT_NEXT=resume missing current-build MS65 receipt", flush=True)
            return subprocess.run([sys.executable, str(ROOT / "tools/ms67_resume_ms65.py"),
                                   "--evidence-root", str(root)], check=False).returncode
        print("MS67_CLOSEOUT_MS65=REUSED_VERIFIED_CURRENT_RECEIPT", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("MS67_CLOSEOUT_INTERRUPTED=Saved evidence is preserved", file=sys.stderr)
        sys.exit(130)
    except JourneyFailure as error:
        print("MS67_CLOSEOUT_ERROR=" + str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("MS67_CLOSEOUT_ERROR=Unexpected input or local error; no automatic retry", file=sys.stderr)
        sys.exit(1)
